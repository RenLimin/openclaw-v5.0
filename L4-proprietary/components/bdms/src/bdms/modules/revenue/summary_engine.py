"""确认收入 —— 报表计算引擎。

对齐手工报表结构（202606 为黄金基准）：

  「汇总」sheet：按月份 × 三组指标
     维度：递延合同 / 新签合同 / 合计
     指标：新签合同额 / 预计确收合同额 / 实际确收合同额 / 完成率

  「月度汇总记录」：历史月份数据（手工维护）
  「履约汇总记录」：履约维度数据

数据来源：budget_exec 表（表头自适应导入）。
关键列：分类（递延/新签）、m2026xx（计划月）、a2026xx（实际月）
"""

from pathlib import Path
from typing import Optional

from openpyxl import load_workbook

from bdms.core import db as _db
from bdms.core.header_mapper import detect_header_row, read_header, HeaderMapper

MONTHS_2026 = [f"2026{m:02d}" for m in range(1, 13)]


class SummaryEngine:
    """汇总报表计算（对齐手工「汇总」sheet）。"""

    def __init__(self, db_path: Optional[Path] = None):
        from bdms.core.paths import DATA_DIR
        self.db_path = Path(db_path) if db_path else (DATA_DIR / "revenue.db")

    # ─── 汇总计算 ───

    def compute_summary(self, month: str) -> dict:
        """计算汇总数据。

        Returns: {
          "months": ["202601", ...],
          "rows": [
            {"period":"202601", "new_sign_amount": x, "categories": {
                "递延": {"plan": x, "actual": y, "rate": z},
                "新签": {...},
                "合计": {...}
            }}, ...
          ],
          "subtotals": {...}
        }
        """
        conn = _db.get_connection(self.db_path)
        try:
            has_table = _db.table_exists(conn, "budget_exec")
            if not has_table:
                return {"error": "budget_exec 表不存在，请先导入数据"}

            # 检查月份列是否存在
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_exec)")}
            plan_cols = [f"m{m}" for m in MONTHS_2026 if f"m{m}" in cols]
            actual_cols = [f"a{m}" for m in MONTHS_2026 if f"a{m}" in cols]

            rows = []
            for m in MONTHS_2026:
                pcol, acol = f"m{m}", f"a{m}"
                rec = {"period": m, "categories": {}}

                for cat_label, cat_filter in [("递延", "递延"), ("新签", "新签"),
                                              ("合计", None)]:
                    where = "WHERE category = ?" if cat_filter else ""
                    params = [cat_filter] if cat_filter else []
                    sql = f"""SELECT
                        COALESCE(SUM(CAST(perf_amount AS REAL)), 0) AS amt,
                        COALESCE(SUM(CAST({pcol} AS REAL)), 0) AS plan,
                        COALESCE(SUM(CAST({acol} AS REAL)), 0) AS actual
                      FROM budget_exec {where}"""
                    r = conn.execute(sql, params).fetchone()
                    plan, actual = (r["plan"] or 0), (r["actual"] or 0)
                    rec["categories"][cat_label] = {
                        "plan": plan, "actual": actual,
                        "rate": (actual / plan) if plan else 0,
                    }
                    # 新签合同额只在"合计-新签"维度取（对齐手工报表）
                    if cat_label == "新签":
                        rec["new_sign_amount"] = plan

                rows.append(rec)

            # 小计（1-6月 / 全年）
            subtotals = {
                "h1": self._subtotal(rows, 1, 6),
                "full": self._subtotal(rows, 1, 12),
            }
            return {"months": MONTHS_2026, "rows": rows, "subtotals": subtotals,
                    "available_plan_cols": plan_cols, "available_actual_cols": actual_cols}
        finally:
            conn.close()

    @staticmethod
    def _subtotal(rows: list[dict], start: int, end: int) -> dict:
        """计算区间小计。"""
        out = {"period": f"1-{end}月小计" if start == 1 else f"{start}-{end}月小计",
               "categories": {}}
        for cat in ["递延", "新签", "合计"]:
            plan = sum(r["categories"][cat]["plan"] for r in rows[start - 1:end])
            actual = sum(r["categories"][cat]["actual"] for r in rows[start - 1:end])
            out["categories"][cat] = {
                "plan": plan, "actual": actual,
                "rate": (actual / plan) if plan else 0,
            }
        plan_ns = sum(r.get("new_sign_amount", 0) for r in rows[start - 1:end])
        out["new_sign_amount"] = plan_ns
        return out

    # ─── 手工报表汇总（读取黄金基准，用于对比测试）───

    @staticmethod
    def read_manual_summary(excel_path) -> dict:
        """读手工报表的「汇总」sheet（对比测试基准）。

        用 pandas 读取（openpyxl data_only 读不到公式缓存值）。

        列布局（实测 202606，注意：**新签在前，递延在后**）：
          col1=期间 col2=新签合同额
          col3,4,5=新签(预算/预计确收, 实际确收, 完成率)
          col6,7,8=递延(预算/预计确收, 实际确收, 完成率)
          col9,10,11=合计(计划,实际,率)
        行3 = 子表头行；数据从行4（0-based idx=3）开始。

        验证依据：行19说明「新签合同截止2026年6月实际比预计完成增加102万元」
        对应 col2 = 2101.638241(202606新签合同额)，行21-23「预算完成 新签=1986.73」
        对应 col3 合计 = 1986.738791 ✓
        """
        import pandas as pd
        try:
            df = pd.read_excel(excel_path, sheet_name="汇总", header=None)
        except Exception as e:
            return {"error": str(e), "rows": []}

        rows = []
        for idx in range(3, min(len(df), 25)):
            row = df.iloc[idx]
            period = row.iloc[1]
            if period is None or (isinstance(period, float) and pd.isna(period)):
                continue
            label = str(period).strip()
            if label in ("1-6月小计", "合计") or "小计" in label:
                rows.append({"_kind": "subtotal", "label": label,
                             "values": [row.iloc[c] if c < len(row) else None
                                        for c in range(2, 12)]})
                continue
            if not label.startswith("2026"):
                continue

            def val(c):
                if c >= len(row):
                    return None
                v = row.iloc[c]
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return None
                return float(v)

            rows.append({
                "period": label,
                "new_sign_amount": val(2),
                # 注意：col3-5 = 新签，col6-8 = 递延（手工报表列序）
                "new_sign": {"plan": val(3), "actual": val(4), "rate": val(5)},
                "deferred": {"plan": val(6), "actual": val(7), "rate": val(8)},
                "total": {"plan": val(9), "actual": val(10), "rate": val(11)},
            })
        return {"rows": rows}

    # ─── 月度汇总记录 / 履约汇总记录 ───

    @staticmethod
    def read_sheet_records(excel_path, sheet_name: str, header_row: int = None) -> dict:
        """通用：读取一个 sheet 为结构化记录（自动探测表头）。"""
        wb = load_workbook(excel_path, read_only=True, data_only=True)
        if sheet_name not in wb.sheetnames:
            return {"error": f"无 {sheet_name} sheet", "rows": []}
        ws = wb[sheet_name]
        hr = header_row or detect_header_row(ws)
        if hr is None:
            return {"error": "无法探测表头", "rows": []}
        headers = read_header(ws, hr)
        records = []
        for row in ws.iter_rows(min_row=hr + 1, values_only=True):
            if all(v is None or str(v).strip() == "" for v in row):
                continue
            records.append({headers[i]: row[i] for i in range(min(len(headers), len(row)))
                            if headers[i]})
        return {"headers": headers, "rows": records}
