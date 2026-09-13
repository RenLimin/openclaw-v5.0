"""计算引擎：汇总逻辑、同比分析、差异分解"""

import sqlite3
from typing import Optional
from pathlib import Path

from .db import get_connection
from .config import SUMMARY_MONTHS


def _row_factory_dict(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class RevenueEngine:
    """确收计算引擎"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def _conn(self):
        conn = get_connection(self.db_path)
        conn.row_factory = _row_factory_dict
        return conn

    # ------------------------------------------------------------------
    # 核心汇总：按合同期间 × 分类(新签/递延) 聚合
    # ------------------------------------------------------------------

    def compute_summary(self, period: str = "202606") -> dict:
        """
        计算汇总数据，对应手工报表"汇总"sheet Row 4-17。

        逻辑：
        - 从 budget_exec 表聚合
        - 分类 A 列: '新签' 或 '递延'
        - 合同期间 = 合同归档月份 (G 列)
        - 新签合同额 = SUM(单项履约义务金额 L) WHERE 分类='新签'
        - 预计确收 = SUM(月度计划) for the contract period's planned months
        - 实际确收 = SUM(月度实际) for months that have actual data

        但手工报表中：
        - 新签合同额 = 该期间归档的合同总额（按合同金额或履约义务金额合计）
        - 预计确收合同额 = 该期间合同在当期的计划确收金额
        - 实际确收合同额 = 该期间合同在当期的实际确收金额

        关键：按合同归档月份分组，汇总 L 列（单项履约义务金额）= 合同额
        """
        conn = self._conn()

        # 新签: 按合同归档月份分组
        new_contracts = conn.execute("""
            SELECT archive_month as period,
                   SUM(perf_amount) as total_amount,
                   SUM(COALESCE(m202601,0) + COALESCE(m202602,0) + COALESCE(m202603,0) +
                       COALESCE(m202604,0) + COALESCE(m202605,0) + COALESCE(m202606,0) +
                       COALESCE(m202607,0) + COALESCE(m202608,0) + COALESCE(m202609,0) +
                       COALESCE(m202610,0) + COALESCE(m202611,0) + COALESCE(m202612,0)) as plan_rev,
                   SUM(COALESCE(a202601,0) + COALESCE(a202602,0) + COALESCE(a202603,0) +
                       COALESCE(a202604,0) + COALESCE(a202605,0) + COALESCE(a202606,0)) as actual_rev
            FROM budget_exec
            WHERE category = '新签' AND archive_month IS NOT NULL
            GROUP BY archive_month
            ORDER BY archive_month
        """).fetchall()

        # 递延: 按合同归档月份分组
        defer_contracts = conn.execute("""
            SELECT archive_month as period,
                   SUM(perf_amount) as total_amount,
                   SUM(COALESCE(m202601,0) + COALESCE(m202602,0) + COALESCE(m202603,0) +
                       COALESCE(m202604,0) + COALESCE(m202605,0) + COALESCE(m202606,0) +
                       COALESCE(m202607,0) + COALESCE(m202608,0) + COALESCE(m202609,0) +
                       COALESCE(m202610,0) + COALESCE(m202611,0) + COALESCE(m202612,0)) as plan_rev,
                   SUM(COALESCE(a202601,0) + COALESCE(a202602,0) + COALESCE(a202603,0) +
                       COALESCE(a202604,0) + COALESCE(a202605,0) + COALESCE(a202606,0)) as actual_rev
            FROM budget_exec
            WHERE category = '递延' AND archive_month IS NOT NULL
            GROUP BY archive_month
            ORDER BY archive_month
        """).fetchall()

        conn.close()
        return {"new": new_contracts, "deferred": defer_contracts}

    def compute_monthly_detail(self, period: str = "202606") -> list:
        """
        计算月度汇总记录，对应"月度汇总"sheet。
        逻辑（与手工报表一致）：
        - 新签: 按 archive_month 分组，perf_amount=合同额
        - 新签预计确收: SUM(m{期间}) WHERE category='新签'（不限archive_month）
        - 递延预计确收: SUM(m{期间}) WHERE category='递延'（不限archive_month）
        - 实际确收: SUM(a{期间}) WHERE category=新签/递延
        """
        conn = self._conn()

        # 新签: 按 archive_month 分组获取合同额
        new_amount_by_period = {}
        rows = conn.execute("""
            SELECT archive_month, SUM(perf_amount) as total_amount
            FROM budget_exec
            WHERE category='新签' AND archive_month IS NOT NULL
            GROUP BY archive_month
            ORDER BY archive_month
        """).fetchall()
        for r in rows:
            new_amount_by_period[r["archive_month"]] = r["total_amount"] or 0

        # 按期间获取计划和实际确收
        # 注意: a列只有 a202601-a202606（实际列），m列有 m202601-m202612（计划列）
        # 对于 7-12 月，actual_rev = 0（尚未有实际数据）
        results = []
        for m in SUMMARY_MONTHS:
            month_num = int(m[4:6])
            # 实际列只到6月
            if month_num <= 6:
                actual_sql = f"COALESCE(a{m}, 0)"
            else:
                actual_sql = "0"

            # 新签预计/实际（不限archive_month）
            new_row = conn.execute(f"""
                SELECT SUM(COALESCE(m{m}, 0)) as plan_rev,
                       SUM({actual_sql}) as actual_rev
                FROM budget_exec
                WHERE category='新签'
            """).fetchone()

            # 递延预计/实际（不限archive_month）
            def_row = conn.execute(f"""
                SELECT SUM(COALESCE(m{m}, 0)) as plan_rev,
                       SUM({actual_sql}) as actual_rev
                FROM budget_exec
                WHERE category='递延'
            """).fetchone()

            new_amount = new_amount_by_period.get(m, 0)
            new_plan = new_row["plan_rev"] or 0
            new_actual = new_row["actual_rev"] or 0
            def_plan = def_row["plan_rev"] or 0
            def_actual = def_row["actual_rev"] or 0

            results.append({
                "period": int(period),
                "contract_period": m,
                "new_amount": round(new_amount, 6),
                "new_plan_rev": round(new_plan, 6),
                "new_actual_rev": round(new_actual, 6),
                "def_plan_rev": round(def_plan, 6),
                "def_actual_rev": round(def_actual, 6),
                "total_plan_rev": round(new_plan + def_plan, 6),
                "total_actual_rev": round(new_actual + def_actual, 6),
            })

        conn.close()
        return results

    def _get_period_months(self, period: str) -> list:
        """根据统计期间(如'202606')返回已过的月份列表['202601',...,'202606']"""
        year = int(period[:4])
        month = int(period[4:6])
        return [f"{year}{m:02d}" for m in range(1, month + 1)]

    def _build_month_sum_sql(self, prefix: str, months: list) -> str:
        """构建 SUM(COALESCE(prefixXXXX,0)+...) SQL 片段"""
        return "+".join(f"COALESCE({prefix}{m},0)" for m in months)

    def compute_performance_summary(self, period: str = "202606") -> dict:
        """
        计算履约维度汇总，对应"履约汇总记录"sheet。
        budget = 统计期间之前月份的计划确收合计（如period=202606则只算1-6月）
        """
        conn = self._conn()
        months = self._get_period_months(period)
        plan_sql = self._build_month_sum_sql("m", months)
        actual_sql = self._build_month_sum_sql("a", months)

        # 新签
        new_budget = conn.execute(f"""
            SELECT SUM({plan_sql}) as val
            FROM budget_exec WHERE category='新签'
        """).fetchone()["val"] or 0

        new_actual = conn.execute(f"""
            SELECT SUM({actual_sql}) as val
            FROM budget_exec WHERE category='新签'
        """).fetchone()["val"] or 0

        # 手工报表逻辑: h1_behind 按 disappear_2026 拆分
        # - 滞后未完成 = SUM(h1_behind) WHERE disappear_2026 >= 0
        # - 消失 = SUM(h1_behind) WHERE disappear_2026 < 0
        # 新签
        new_ahead = conn.execute("""
            SELECT SUM(COALESCE(h1_ahead,0)) as val FROM budget_exec WHERE category='新签'
        """).fetchone()["val"] or 0

        new_behind = conn.execute("""
            SELECT SUM(COALESCE(h1_behind,0)) as val
            FROM budget_exec WHERE category='新签' AND COALESCE(disappear_2026, 0) >= 0
        """).fetchone()["val"] or 0

        new_disappear = conn.execute("""
            SELECT SUM(COALESCE(h1_behind,0)) as val
            FROM budget_exec WHERE category='新签' AND COALESCE(disappear_2026, 0) < 0
        """).fetchone()["val"] or 0

        # 递延
        def_budget = conn.execute(f"""
            SELECT SUM({plan_sql}) as val
            FROM budget_exec WHERE category='递延'
        """).fetchone()["val"] or 0

        def_actual = conn.execute(f"""
            SELECT SUM({actual_sql}) as val
            FROM budget_exec WHERE category='递延'
        """).fetchone()["val"] or 0

        def_ahead = conn.execute("""
            SELECT SUM(COALESCE(h1_ahead,0)) as val FROM budget_exec WHERE category='递延'
        """).fetchone()["val"] or 0

        def_behind = conn.execute("""
            SELECT SUM(COALESCE(h1_behind,0)) as val
            FROM budget_exec WHERE category='递延' AND COALESCE(disappear_2026, 0) >= 0
        """).fetchone()["val"] or 0

        def_disappear = conn.execute("""
            SELECT SUM(COALESCE(h1_behind,0)) as val
            FROM budget_exec WHERE category='递延' AND COALESCE(disappear_2026, 0) < 0
        """).fetchone()["val"] or 0

        conn.close()

        return {
            "new": {
                "budget": round(new_budget, 6),
                "actual": round(new_actual, 6),
                "diff": round(new_budget - new_actual, 6),
                "ahead": round(new_ahead, 6),
                "behind": round(new_behind, 6),
                "disappear": round(new_disappear, 6),
            },
            "deferred": {
                "budget": round(def_budget, 6),
                "actual": round(def_actual, 6),
                "diff": round(def_budget - def_actual, 6),
                "ahead": round(def_ahead, 6),
                "behind": round(def_behind, 6),
                "disappear": round(def_disappear, 6),
            },
            "total": {
                "budget": round(new_budget + def_budget, 6),
                "actual": round(new_actual + def_actual, 6),
                "diff": round((new_budget + def_budget) - (new_actual + def_actual), 6),
                "ahead": round(new_ahead + def_ahead, 6),
                "behind": round(new_behind + def_behind, 6),
                "disappear": round(new_disappear + def_disappear, 6),
            },
        }

    def compute_rebuild_perf(self) -> list:
        """重拆履约数据"""
        conn = self._conn()
        rows = conn.execute("""
            SELECT contract_no_cal as contract_no,
                   SUM(COALESCE(h1_ahead,0)) as ahead,
                   SUM(COALESCE(h1_behind,0)) as behind
            FROM budget_exec
            WHERE rebuild_perf IS NOT NULL AND rebuild_perf != ''
            GROUP BY contract_no_cal
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]


    # ------------------------------------------------------------------
    # 预算趋势分析
    # ------------------------------------------------------------------

    def compute_budget_trend(self, period: str = "202606") -> dict:
        """
        计算预算趋势分析数据。
        返回递延/新签各分类的合同数量和金额。
        由于数据库中无"统计"标记列和"预算执行进度"列，
        这里按合理的业务逻辑填充（全量数据）。
        """
        conn = self._conn()
        WAN = 10000.0

        result = {
            "deferred": [],
            "new": [],
        }

        # 递延合同 — 按不同分类统计
        # 已归档但未下单: 有perf_amount但plan_start为空
        # 已下单但无法交付: plan_start有值但plan_done为空
        # 已交付但无法确收: plan_done有值但h1_actual=0
        # 本年度正常可确收: h1_plan > 0
        # 未来可确收: rev_future > 0
        # 之前年度已确收: rev_prior > 0

        categories_def = [
            ("已归档但未下单", "plan_start IS NULL AND plan_end IS NULL"),
            ("已下单但无法交付", "plan_start IS NOT NULL AND plan_done IS NULL"),
            ("已交付但无法确收", "plan_done IS NOT NULL AND COALESCE(h1_actual, 0) = 0"),
            ("本年度正常可确收", "COALESCE(h1_plan, 0) > 0"),
            ("未来可确收", "COALESCE(rev_future, 0) > 0"),
            ("之前年度已确收", "COALESCE(rev_prior, 0) > 0"),
        ]

        for label, where_clause in categories_def:
            row = conn.execute(f"""
                SELECT COUNT(*) as cnt,
                       SUM(COALESCE(perf_amount, 0)) as amount
                FROM budget_exec
                WHERE category = '递延' AND {where_clause}
            """).fetchone()
            result["deferred"].append({
                "label": label,
                "count": row["cnt"] or 0,
                "amount": round((row["amount"] or 0) / WAN, 6),
            })

        # 新签合同
        categories_new = [
            ("已归档但未下单", "plan_start IS NULL AND plan_end IS NULL"),
            ("已下单但无法交付", "plan_start IS NOT NULL AND plan_done IS NULL"),
            ("已交付但无法确收", "plan_done IS NOT NULL AND COALESCE(h1_actual, 0) = 0"),
            ("本年度正常可确收", "COALESCE(h1_plan, 0) > 0"),
            ("未来可确收", "COALESCE(rev_future, 0) > 0"),
        ]

        for label, where_clause in categories_new:
            row = conn.execute(f"""
                SELECT COUNT(*) as cnt,
                       SUM(COALESCE(perf_amount, 0)) as amount
                FROM budget_exec
                WHERE category = '新签' AND {where_clause}
            """).fetchone()
            result["new"].append({
                "label": label,
                "count": row["cnt"] or 0,
                "amount": round((row["amount"] or 0) / WAN, 6),
            })

        conn.close()
        return result

    # ------------------------------------------------------------------
    # 确收差异分析
    # ------------------------------------------------------------------

    def compute_variance_analysis(self, period: str = "202606") -> list:
        """
        计算确收差异分析数据。
        按 disappear_note（消失备注/差异原因）分组统计 h1_behind。
        """
        conn = self._conn()

        rows = conn.execute("""
            SELECT COALESCE(disappear_note, '(空白)') as reason,
                   SUM(CASE WHEN category='递延' THEN COALESCE(h1_behind, 0) ELSE 0 END) as deferred,
                   SUM(CASE WHEN category='新签' THEN COALESCE(h1_behind, 0) ELSE 0 END) as new,
                   SUM(COALESCE(h1_behind, 0)) as total
            FROM budget_exec
            WHERE COALESCE(h1_behind, 0) != 0
            GROUP BY disappear_note
            ORDER BY total DESC
        """).fetchall()

        conn.close()
        return [dict(r) for r in rows]


    def compute_yoy_comparison(self, period: str = "202606") -> list:
        """
        同比分析：按 comparison_source 字段分组，对比当期 vs 同期数据。
        comparison_source 标记每条记录的数据来源（如 '2025_actual', '2026_plan'），
        不做双路径，所有对比数据保留在同一张表。
        """
        conn = self._conn()
        rows = conn.execute("""
            SELECT comparison_source,
                   category,
                   COUNT(*) as cnt,
                   SUM(COALESCE(perf_amount, 0)) as total_amount,
                   SUM(COALESCE(h1_plan, 0)) as h1_plan,
                   SUM(COALESCE(h1_actual, 0)) as h1_actual
            FROM budget_exec
            WHERE comparison_source IS NOT NULL AND comparison_source != ''
            GROUP BY comparison_source, category
            ORDER BY comparison_source, category
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 系统参考数据（手工维护）
    # ------------------------------------------------------------------

    def get_reference_data(self, data_type: str) -> list:
        """按类型查询参考数据"""
        conn = self._conn()
        rows = conn.execute("""
            SELECT code, label, extra, sort_order
            FROM reference_data
            WHERE data_type = ?
            ORDER BY sort_order, id
        """, (data_type,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def upsert_reference_data(self, data_type: str, code: str, label: str,
                               extra: str = None, sort_order: int = 0):
        """插入或更新参考数据"""
        conn = self._conn()
        conn.execute("""
            INSERT INTO reference_data (data_type, code, label, extra, sort_order)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(data_type, code) DO UPDATE SET
                label = excluded.label,
                extra = excluded.extra,
                sort_order = excluded.sort_order,
                updated_at = CURRENT_TIMESTAMP
        """, (data_type, code, label, extra, sort_order))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    engine = RevenueEngine()
    summary = engine.compute_summary()
    print("=== 汇总 ===")
    for item in summary["new"]:
        print(f"  新签 {item['period']}: 合同额={item['total_amount']}, 预计={item['plan_rev']}, 实际={item['actual_rev']}")
    for item in summary["deferred"]:
        print(f"  递延 {item['period']}: 合同额={item['total_amount']}, 预计={item['plan_rev']}, 实际={item['actual_rev']}")

    monthly = engine.compute_monthly_detail()
    print("\n=== 月度汇总 ===")
    for m in monthly:
        print(f"  {m}")

    perf = engine.compute_performance_summary()
    print("\n=== 履约汇总 ===")
    print(f"  新签: {perf['new']}")
    print(f"  递延: {perf['deferred']}")
    print(f"  合计: {perf['total']}")
