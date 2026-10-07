# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""Revenue Stats Builders — 7 个统计 Sheet 构建器。

对齐 DESIGN-DETAIL-REVENUE-v2.1.md §3.6。
输出格式与黄金基准（202606 确收分析 Excel）一致。
"""
from __future__ import annotations
from typing import Optional
from pathlib import Path
import sqlite3
import pandas as pd
from bdms.core.paths import DATA_DIR

STAT_SHEETS = [
    "汇总分析", "预算趋势分析", "确收差异分析",
    "重拆履约", "月度汇总记录", "履约汇总记录",
]


def _conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    return sqlite3.connect(db_path or (DATA_DIR / "revenue.db"))


def _rows(cur) -> list:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def build_all_stats_sheets(db_path: Optional[Path] = None, month: str = None) -> dict:
    """构建全部统计 Sheet（dict[str, DataFrame]）。"""
    conn = _conn(db_path)
    try:
        return {
            "汇总分析": build_summary_analysis(conn, month),
            "预算趋势分析": build_budget_trend(conn, month),
            "确收差异分析": build_revenue_diff_analysis(conn, month),
            "重拆履约": build_re_split_performance(conn, month),
            "月度汇总记录": build_monthly_summary_record(conn, month),
            "履约汇总记录": build_performance_summary_record(conn, month),
        }
    finally:
        conn.close()


def build_summary_analysis(conn: sqlite3.Connection, month: str = None) -> pd.DataFrame:
    """汇总分析 Sheet（按团队/产线聚合）。"""
    cur = conn.cursor()
    cur.execute("SELECT * FROM monthly_summary ORDER BY stat_period, contract_period")
    return pd.DataFrame(_rows(cur))


def build_budget_trend(conn: sqlite3.Connection, month: str = None) -> pd.DataFrame:
    """预算趋势分析 Sheet（多月份预算对比）。"""
    cur = conn.cursor()
    cur.execute("""
        SELECT archive_month, category,
               COUNT(*) as contract_count,
               SUM(COALESCE(CAST(perf_amount AS REAL), 0)) as total_amount
        FROM budget_exec
        GROUP BY archive_month, category
        ORDER BY archive_month, category
    """)
    return pd.DataFrame(_rows(cur))


def build_revenue_diff_analysis(conn: sqlite3.Connection, month: str = None) -> pd.DataFrame:
    """确收差异分析 Sheet（项目经理维度差异）。"""
    cur = conn.cursor()
    cur.execute("""
        SELECT contract_no, category, perf_amount,
               m202601, m202602, m202603, m202604, m202605, m202606,
               a202601, a202602, a202603, a202604, a202605, a202606
        FROM budget_exec
        WHERE category IN ('新签', '递延')
        ORDER BY contract_no
    """)
    return pd.DataFrame(_rows(cur))


def build_re_split_performance(conn: sqlite3.Connection, month: str = None) -> pd.DataFrame:
    """重拆履约 Sheet（合同 × 提前/滞后）。"""
    cur = conn.cursor()
    cur.execute("""
        SELECT contract_no, category, perf_amount,
               m202601, m202602, m202603, m202604, m202605, m202606,
               a202601, a202602, a202603, a202604, a202605, a202606
        FROM budget_exec
        WHERE rebuild_perf IN ('是', '1', 1)
        ORDER BY contract_no
    """)
    return pd.DataFrame(_rows(cur))


def build_monthly_summary_record(conn: sqlite3.Connection, month: str = None) -> pd.DataFrame:
    """月度汇总记录 Sheet（按月份聚合）。"""
    cur = conn.cursor()
    cur.execute("SELECT * FROM monthly_summary ORDER BY stat_period, contract_period")
    return pd.DataFrame(_rows(cur))


def build_performance_summary_record(conn: sqlite3.Connection, month: str = None) -> pd.DataFrame:
    """履约汇总记录 Sheet（按履约维度聚合）。"""
    cur = conn.cursor()
    cur.execute("SELECT * FROM performance_summary ORDER BY stat_period, category")
    return pd.DataFrame(_rows(cur))


def build_full_summary(conn: sqlite3.Connection, month: str = None) -> pd.DataFrame:
    """全量汇总（含所有维度的完整视图）。"""
    cur = conn.cursor()
    cur.execute("SELECT * FROM monthly_summary ORDER BY stat_period")
    return pd.DataFrame(_rows(cur))
