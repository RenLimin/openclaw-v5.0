"""数据库连接管理 — 确收管理模块"""

import sqlite3
from pathlib import Path
from typing import Optional

from .config import DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取数据库连接"""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None):
    """初始化数据库表结构"""
    conn = get_connection(db_path)
    c = conn.cursor()

    # 计划确收底稿 — 原始明细
    c.execute("""
        CREATE TABLE IF NOT EXISTS plan_draft (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note TEXT,
            init_est_date TEXT,
            est_date TEXT,
            contract_no TEXT,
            archive_month TEXT,
            contract_no2 TEXT,
            prod_seq TEXT,
            perf_id TEXT,
            budget_perf_id TEXT,
            dept TEXT,
            contract_name TEXT,
            customer TEXT,
            end_user TEXT,
            contract_note TEXT,
            ops_note TEXT,
            tax_rate REAL,
            sign_date TEXT,
            contract_start TEXT,
            contract_end TEXT,
            service_months REAL,
            contract_type TEXT,
            version_type TEXT,
            gift TEXT,
            prod_category TEXT,
            prod_name TEXT,
            perf_detail TEXT,
            std_prod_name TEXT,
            rev_subject TEXT,
            tax_subject TEXT,
            price_basis TEXT,
            accept_type TEXT,
            accept_term TEXT,
            payment_term TEXT,
            rev_method TEXT,
            no_exec_reason TEXT,
            qty_unit TEXT,
            qty REAL,
            contract_amount REAL,
            confirm_amount REAL,
            perf_amount REAL,
            plan_perf_amount REAL,
            rev_before_2025 REAL,
            rev_2026_future REAL,
            plan_disappear REAL,
            disappear_reason TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 预算执行表 — 原始明细
    c.execute("""
        CREATE TABLE IF NOT EXISTS budget_exec (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            contract_no TEXT,
            contract_no_cal TEXT,
            customer TEXT,
            end_user TEXT,
            sign_subject TEXT,
            archive_month TEXT,
            perf_id_budget TEXT,
            perf_detail_budget TEXT,
            perf_id TEXT,
            rev_method TEXT,
            perf_amount REAL,
            rev_prior REAL,
            rev_future REAL,
            no_plan REAL,
            unrev_prior REAL,
            unrev_adj REAL,
            plan_start TEXT,
            plan_end TEXT,
            plan_done TEXT,
            m202601 REAL, m202602 REAL, m202603 REAL, m202604 REAL,
            m202605 REAL, m202606 REAL, m202607 REAL, m202608 REAL,
            m202609 REAL, m202610 REAL, m202611 REAL, m202612 REAL,
            year_est REAL,
            h1_plan REAL,
            h1_actual REAL,
            h1_ahead REAL,
            h1_behind REAL,
            a202601 REAL, a202602 REAL, a202603 REAL, a202604 REAL,
            a202605 REAL, a202606 REAL,
            disappear_2026 REAL,
            disappear_future REAL,
            disappear_note TEXT,
            rebuild_perf TEXT,
            forecast_category TEXT,
            comparison_source TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 索引
    c.execute("CREATE INDEX IF NOT EXISTS idx_plan_contract ON plan_draft(contract_no)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_plan_archive ON plan_draft(archive_month)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_plan_perf ON plan_draft(perf_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_budget_contract ON budget_exec(contract_no)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_budget_category ON budget_exec(category)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_budget_archive ON budget_exec(archive_month)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_budget_perf ON budget_exec(perf_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_budget_comparison ON budget_exec(comparison_source)")

    # 系统参考数据表（手工维护）
    c.execute("""
        CREATE TABLE IF NOT EXISTS reference_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_type TEXT NOT NULL,
            code TEXT NOT NULL,
            label TEXT NOT NULL,
            extra TEXT,
            sort_order INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(data_type, code)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ref_type ON reference_data(data_type)")
    # 月度汇总记录 — 手工维护的历史数据
    c.execute("""
        CREATE TABLE IF NOT EXISTS monthly_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_period TEXT NOT NULL,
            contract_period TEXT NOT NULL,
            new_amount REAL,
            new_plan_rev REAL,
            new_actual_rev REAL,
            def_plan_rev REAL,
            def_actual_rev REAL,
            total_plan_rev REAL,
            total_actual_rev REAL,
            adj_plan REAL,
            adj_actual REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(stat_period, contract_period)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ms_stat ON monthly_summary(stat_period)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ms_contract ON monthly_summary(contract_period)")

    # 履约汇总记录 — 手工维护的历史数据
    c.execute("""
        CREATE TABLE IF NOT EXISTS performance_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stat_period TEXT NOT NULL,
            category TEXT NOT NULL,
            new_value REAL,
            deferred_value REAL,
            total_value REAL,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(stat_period, category)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ps_stat ON performance_summary(stat_period)")



    conn.commit()
    conn.close()
    return db_path or DB_PATH


if __name__ == "__main__":
    path = init_db()
    print(f"✅ 确收数据库初始化完成: {path}")
