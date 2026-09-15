"""交付统计看板 —— 聚合查询引擎（模块4）。

设计原则：
  * 纯查询、无副作用（不写任何业务表；本文件不含 commit/write）
  * 所有图表数据来自两块真实来源：
      1. 交付月报 Sheet（dr_sheet_row 表，JSON 行）—— 交付过程维度
      2. 确收差异分析（revenue.db 的 budget_exec / plan_draft）—— 金额维度
  * 下钻穿透 drill_down() 返回明细行，供前端点击图表后查询

真实列名说明（202608 实测，非猜测）：
  「签约」sheet 可用分组列：
      '项目经理所属部门'                     部门维度（南/北区客户服务部、大客户服务部）
      '履约项统计状态（即，财报-交付/确收状态）'  交付状态（1：正常交付 … 9：已结项）
      '项目验收状态（即，财报-验收状态）'        验收状态（未验收/正常验收/验收异常）
      '合同归档年度' / '合同归档日期'           时间维度
  「异常项目」sheet 无「异常类型」列，实际类型信息由
      '项目验收状态'（未验收/正常验收/验收异常）+ '状态'（已完成/营销处置中/…）组合表达。
      因此 compute_exception_dist 以「状态 × 验收状态」组合作为异常类型分组，
      并额外提供按 '项目经理团队' 的分组。
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from bdms.core import db as _db
from bdms.core.paths import DATA_DIR, DB_PATH

# ─── 常量 ───

# 交付月报 Sheet 名（与 delivery_report/engine.py SHEETS 保持一致）
SHEET_SIGN = "签约"
SHEET_POC = "POC&提前实施"
SHEET_EXCEPTION = "异常项目"
SHEET_REVENUE_HANDOVER = "确收交接"
SHEET_ACCEPTANCE_HANDOVER = "验收交接"

# 签约 sheet 关键列
COL_DEPT = "项目经理所属部门"
COL_DELIVERY_STATUS = "履约项统计状态（即，财报-交付/确收状态）"
COL_ACCEPT_STATUS = "项目验收状态（即，财报-验收状态）"
COL_STAT_STATUS = "项目统计状态"          # 实测 202608 基本为空，保留兼容
COL_ARCHIVE_YEAR = "合同归档年度"
COL_ARCHIVE_DATE = "合同归档日期"
COL_PROJECT = "所属项目"
COL_CONTRACT_NO = "销售合同编号"

# 异常项目 sheet 关键列
COL_EXC_STATUS = "状态"
COL_EXC_ACCEPT = "项目验收状态"
COL_EXC_TEAM = "项目经理团队"

# 交付状态白名单（对齐 83 列中的 1..9 状态列）
DELIVERY_STATUSES = [
    "1：正常交付", "2：应交未交", "3：交付异常",
    "4：正常验收", "5：应验未验", "6：验收异常",
    "7：正常服务", "8：应结未结", "9：已结项",
]
# 异常交付状态（用于 KPI 异常项目数）
ABNORMAL_DELIVERY_STATUSES = {"2：应交未交", "3：交付异常", "5：应验未验", "6：验收异常"}

MONTHS_2026 = [f"2026{m:02d}" for m in range(1, 13)]


def _to_float(v: Any) -> float:
    """容错转 float（空串/None/文本 → 0）。"""
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class DashboardEngine:
    """看板聚合查询引擎（无状态）。"""

    def __init__(self, db_path: Optional[Path] = None,
                 revenue_db_path: Optional[Path] = None):
        # 月报库（bdms.db）
        self.db_path = Path(db_path) if db_path else DB_PATH
        # 确收库（revenue.db）— 与月报库分离
        self.revenue_db_path = (
            Path(revenue_db_path) if revenue_db_path else (DATA_DIR / "revenue.db")
        )

    # ═══════ 内部工具 ═══════

    def _load_sheet(self, month: str, sheet: str) -> list[dict]:
        """读取某月某 sheet 的 JSON 行（只读）。"""
        conn = _db.get_connection(self.db_path)
        try:
            _cols, rows = _db.load_sheet_rows(conn, month, sheet, prefix="dr")
            return rows
        finally:
            conn.close()

    def _revenue_conn(self):
        """打开确收库（只读连接）。"""
        import sqlite3
        if not self.revenue_db_path.exists():
            return None
        conn = sqlite3.connect(str(self.revenue_db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _month_col(month: str, kind: str) -> str:
        """把 202608 → m202608 / a202608。"""
        return f"{kind}{month}"

    # ═══════ 1. KPI 核心指标 ═══════

    def compute_kpis(self, month: str) -> dict:
        """核心指标卡数据。

        Returns: {
          "month": "202608",
          "contract_amount": 合同总额（budget_exec.perf_amount 合计）,
          "plan_revenue": 计划确收（m{month}）,
          "actual_revenue": 实际确收（a{month}）,
          "completion_rate": 完成率 = actual/plan,
          "delivery_project_count": 交付项目数（签约 sheet 去重项目数）,
          "exception_project_count": 异常项目数,
          "by_category": {新签/递延: {...}}
        }
        """
        plan_col, act_col = self._month_col(month, "m"), self._month_col(month, "a")

        contract_amount = plan_revenue = actual_revenue = 0.0
        by_category: dict[str, dict] = {}

        conn = self._revenue_conn()
        if conn is not None:
            try:
                has = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_exec'"
                ).fetchone()
                if has:
                    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_exec)")}
                    if {plan_col, act_col} <= cols:
                        total = conn.execute(
                            f"""SELECT COALESCE(SUM(CAST(perf_amount AS REAL)),0) amt,
                                       COALESCE(SUM(CAST({plan_col} AS REAL)),0) plan,
                                       COALESCE(SUM(CAST({act_col} AS REAL)),0) actual
                                FROM budget_exec"""
                        ).fetchone()
                        contract_amount = float(total["amt"] or 0)
                        plan_revenue = float(total["plan"] or 0)
                        actual_revenue = float(total["actual"] or 0)
                        for r in conn.execute(
                            f"""SELECT category,
                                       COALESCE(SUM(CAST(perf_amount AS REAL)),0) amt,
                                       COALESCE(SUM(CAST({plan_col} AS REAL)),0) plan,
                                       COALESCE(SUM(CAST({act_col} AS REAL)),0) actual
                                FROM budget_exec GROUP BY category"""
                        ):
                            p, a = float(r["plan"] or 0), float(r["actual"] or 0)
                            by_category[r["category"] or "未分类"] = {
                                "contract_amount": float(r["amt"] or 0),
                                "plan": p, "actual": a,
                                "completion_rate": (a / p) if p else 0.0,
                            }
            finally:
                conn.close()

        # 交付项目数 + 异常项目数（来自月报 Sheet）
        sign_rows = self._load_sheet(month, SHEET_SIGN)
        project_keys = set()
        abnormal_from_status = 0
        for r in sign_rows:
            key = (r.get(COL_PROJECT) or "").strip() or (r.get("BI履约ID") or "").strip()
            if key:
                project_keys.add(key)
            if (r.get(COL_DELIVERY_STATUS) or "").strip() in ABNORMAL_DELIVERY_STATUSES:
                abnormal_from_status += 1

        exc_rows = self._load_sheet(month, SHEET_EXCEPTION)

        return {
            "month": month,
            "contract_amount": contract_amount,
            "plan_revenue": plan_revenue,
            "actual_revenue": actual_revenue,
            "completion_rate": (actual_revenue / plan_revenue) if plan_revenue else 0.0,
            "delivery_project_count": len(project_keys),
            "delivery_obligation_count": len(sign_rows),
            "exception_project_count": len(exc_rows) if exc_rows else abnormal_from_status,
            "abnormal_obligation_count": abnormal_from_status,
            "by_category": by_category,
        }

    # ═══════ 2. 月度趋势（折线图） ═══════

    def compute_monthly_trend(self, months: Optional[list[str]] = None) -> dict:
        """月度趋势序列：每月 新签/递延/合计 的计划 vs 实际。

        Returns: {
          "months": [...],
          "series": {
            "新签": {"plan": [...], "actual": [...]},
            "递延": {...}, "合计": {...}
          }
        }
        """
        months = months or MONTHS_2026
        conn = self._revenue_conn()
        series = {
            cat: {"plan": [], "actual": []} for cat in ("新签", "递延", "合计")
        }
        used_months: list[str] = []

        if conn is not None:
            try:
                has = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_exec'"
                ).fetchone()
                if has:
                    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_exec)")}
                    for m in months:
                        pcol, acol = f"m{m}", f"a{m}"
                        if pcol not in cols or acol not in cols:
                            continue
                        used_months.append(m)
                        for label, cond in (("新签", "WHERE category='新签'"),
                                            ("递延", "WHERE category='递延'"),
                                            ("合计", "")):
                            r = conn.execute(
                                f"""SELECT COALESCE(SUM(CAST({pcol} AS REAL)),0) plan,
                                           COALESCE(SUM(CAST({acol} AS REAL)),0) actual
                                    FROM budget_exec {cond}"""
                            ).fetchone()
                            series[label]["plan"].append(round(float(r["plan"] or 0), 2))
                            series[label]["actual"].append(round(float(r["actual"] or 0), 2))
            finally:
                conn.close()

        return {"months": used_months or months, "series": series}

    # ═══════ 3. 交付状态分布（柱状图/饼图） ═══════

    def compute_delivery_status_dist(self, month: str, sheet: str = SHEET_SIGN) -> dict:
        """交付状态分布。

        取「签约」(或 POC) sheet 的交付/确收状态列分组计数。
        同时返回验收状态分布（辅助饼图）。

        说明：任务书写的列名是「项目统计状态」，实测 202608 该列在签约 sheet
        中 13377/16872 行为空，只有 3495 行 '已归档'，不具备分组价值；
        真实可用的状态列是「履约项统计状态（即，财报-交付/确收状态）」。
        """
        rows = self._load_sheet(month, sheet)
        delivery_counter: Counter = Counter()
        accept_counter: Counter = Counter()
        stat_counter: Counter = Counter()

        for r in rows:
            d = (r.get(COL_DELIVERY_STATUS) or "").strip()
            if d:
                delivery_counter[d] += 1
            a = (r.get(COL_ACCEPT_STATUS) or "").strip()
            if a:
                accept_counter[a] += 1
            s = (r.get(COL_STAT_STATUS) or "").strip()
            if s:
                stat_counter[s] += 1

        # 按状态编码排序（1..9），保证图表顺序稳定
        def _sort_key(item):
            label = item[0]
            for i, known in enumerate(DELIVERY_STATUSES):
                if label == known:
                    return (0, i)
            return (1, label)

        delivery_items = sorted(delivery_counter.items(), key=_sort_key)
        total = sum(delivery_counter.values())

        return {
            "month": month,
            "sheet": sheet,
            "dimension": "delivery_status",
            "total": total,
            "items": [
                {"label": k, "value": v,
                 "percent": round(v / total, 4) if total else 0.0}
                for k, v in delivery_items
            ],
            "acceptance_status": {
                "total": sum(accept_counter.values()),
                "items": [{"label": k, "value": v}
                          for k, v in accept_counter.most_common()],
            },
            "project_stat_status": {
                "total": sum(stat_counter.values()),
                "items": [{"label": k, "value": v}
                          for k, v in stat_counter.most_common()],
            },
        }

    # ═══════ 4. 异常分布（柱状图/饼图） ═══════

    def compute_exception_dist(self, month: str, group_by: str = "type") -> dict:
        """异常项目分布。

        「异常项目」sheet 无「异常类型」列；异常类型用
        「状态 × 项目验收状态」组合表达（group_by="type"，默认）。
        也支持 group_by="team"（项目经理团队）。

        Returns: {"month","group_by","total","items":[{label,value,percent}]}
        """
        rows = self._load_sheet(month, SHEET_EXCEPTION)
        counter: Counter = Counter()

        for r in rows:
            if group_by == "team":
                label = (r.get(COL_EXC_TEAM) or "").strip() or "未分配"
            elif group_by == "accept_status":
                label = (r.get(COL_EXC_ACCEPT) or "").strip() or "未知"
            else:  # type：状态 × 验收状态
                st = (r.get(COL_EXC_STATUS) or "").strip() or "未知"
                ac = (r.get(COL_EXC_ACCEPT) or "").strip() or "未知验收状态"
                label = f"{st} / {ac}"
            counter[label] += 1

        total = sum(counter.values())
        return {
            "month": month,
            "group_by": group_by,
            "dimension": "exception_type" if group_by == "type" else f"exception_{group_by}",
            "total": total,
            "items": [
                {"label": k, "value": v,
                 "percent": round(v / total, 4) if total else 0.0}
                for k, v in counter.most_common()
            ],
        }

    # ═══════ 5. 部门维度统计 ═══════

    def compute_dept_stats(self, month: str) -> dict:
        """按「项目经理所属部门」分组统计。

        Returns: {
          "month", "dimension": "dept",
          "items": [{label, total, by_delivery_status:{...}, abnormal, ...}]
        }
        """
        rows = self._load_sheet(month, SHEET_SIGN)
        agg: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "abnormal": 0, "by_status": Counter(),
                     "projects": set()}
        )

        for r in rows:
            dept = (r.get(COL_DEPT) or "").strip() or "未分配"
            rec = agg[dept]
            rec["total"] += 1
            status = (r.get(COL_DELIVERY_STATUS) or "").strip()
            if status:
                rec["by_status"][status] += 1
            if status in ABNORMAL_DELIVERY_STATUSES:
                rec["abnormal"] += 1
            proj = (r.get(COL_PROJECT) or "").strip()
            if proj:
                rec["projects"].add(proj)

        items = []
        for dept, rec in sorted(agg.items(), key=lambda kv: -kv[1]["total"]):
            items.append({
                "label": dept,
                "total": rec["total"],
                "project_count": len(rec["projects"]),
                "abnormal": rec["abnormal"],
                "abnormal_rate": round(rec["abnormal"] / rec["total"], 4)
                if rec["total"] else 0.0,
                "by_delivery_status": dict(rec["by_status"].most_common()),
            })

        return {
            "month": month,
            "dimension": "dept",
            "total": sum(i["total"] for i in items),
            "items": items,
        }

    # ═══════ 6. 下钻穿透 ═══════

    def drill_down(self, month: str, sheet: str, dimension: str, value: str,
                   limit: int = 500) -> dict:
        """点击图表后取明细行。

        dimension 取值（对应上面各聚合方法）：
          "delivery_status" → 匹配 COL_DELIVERY_STATUS
          "acceptance_status" → 匹配 COL_ACCEPT_STATUS
          "project_stat_status" → 匹配 COL_STAT_STATUS
          "dept" → 匹配 COL_DEPT
          "exception_type" → 「状态 / 验收状态」组合匹配（异常项目 sheet）
          "exception_team" → 匹配 COL_EXC_TEAM
          "exception_status" → 匹配 COL_EXC_STATUS

        Returns: {"month","sheet","dimension","value","total","columns","rows"}
        """
        dim_col_map = {
            "delivery_status": COL_DELIVERY_STATUS,
            "acceptance_status": COL_ACCEPT_STATUS,
            "project_stat_status": COL_STAT_STATUS,
            "dept": COL_DEPT,
            "archive_year": COL_ARCHIVE_YEAR,
            "exception_type": None,        # 组合维度，特殊处理
            "exception_team": COL_EXC_TEAM,
            "exception_status": COL_EXC_STATUS,
            "exception_acceptance_status": COL_EXC_ACCEPT,
        }
        if dimension not in dim_col_map:
            raise ValueError(
                f"未知下钻维度: {dimension}（可选: {sorted(dim_col_map)}）"
            )

        rows = self._load_sheet(month, sheet)
        matched: list[dict] = []

        if dimension == "exception_type":
            # value 形如 "已完成 / 正常验收"
            for r in rows:
                st = (r.get(COL_EXC_STATUS) or "").strip() or "未知"
                ac = (r.get(COL_EXC_ACCEPT) or "").strip() or "未知验收状态"
                if f"{st} / {ac}" == value:
                    matched.append(r)
        else:
            col = dim_col_map[dimension]
            for r in rows:
                if (r.get(col) or "").strip() == value.strip():
                    matched.append(r)

        conn = _db.get_connection(self.db_path)
        try:
            columns = []
            meta = conn.execute(
                "SELECT columns FROM dr_sheet_meta WHERE month=? AND sheet=?",
                (month, sheet),
            ).fetchone()
            if meta:
                import json
                columns = json.loads(meta["columns"])
        finally:
            conn.close()

        total = len(matched)
        return {
            "month": month,
            "sheet": sheet,
            "dimension": dimension,
            "value": value,
            "total": total,
            "shown": min(total, limit),
            "columns": columns,
            "rows": matched[:limit],
        }

    # ═══════ 辅助：可选月份 ═══════

    def list_available_months(self) -> list[str]:
        """返回月报库中已落盘的月份（降序）。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT DISTINCT month FROM dr_sheet_meta ORDER BY month DESC"
            ).fetchall()
            return [r["month"] for r in rows]
        finally:
            conn.close()
