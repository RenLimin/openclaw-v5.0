"""数据库连接 + 迁移框架"""

import sqlite3
import os
from pathlib import Path

_global_conn = None

DB_DIR = Path(os.path.expanduser("~/.fin-l4"))
DB_DIR.mkdir(parents=True, exist_ok=True)

# 迁移脚本（按顺序执行）
MIGRATIONS = [
    # V1: 核心表族
    """
    CREATE TABLE IF NOT EXISTS fin4_family (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        currency TEXT DEFAULT 'CNY',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_accounts (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        code TEXT NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        currency TEXT DEFAULT 'CNY',
        parent_id TEXT,
        opening_balance TEXT DEFAULT '0',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id),
        FOREIGN KEY (parent_id) REFERENCES fin4_accounts(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_categories (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        name TEXT NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
        parent_id TEXT,
        color TEXT,
        icon TEXT,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_transactions (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        date TEXT NOT NULL,
        amount TEXT NOT NULL,
        note TEXT,
        category_id TEXT,
        debit_account_id TEXT NOT NULL,
        credit_account_id TEXT NOT NULL,
        source TEXT DEFAULT 'manual',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id),
        FOREIGN KEY (category_id) REFERENCES fin4_categories(id),
        FOREIGN KEY (debit_account_id) REFERENCES fin4_accounts(id),
        FOREIGN KEY (credit_account_id) REFERENCES fin4_accounts(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_budgets (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        category_id TEXT,
        amount TEXT NOT NULL,
        period TEXT NOT NULL CHECK(period IN ('month', 'year')),
        start_date TEXT,
        end_date TEXT,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id),
        FOREIGN KEY (category_id) REFERENCES fin4_categories(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_loans (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        name TEXT NOT NULL,
        principal TEXT NOT NULL,
        annual_rate TEXT NOT NULL,
        term_months INTEGER NOT NULL,
        method TEXT NOT NULL,
        start_date TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        extra_terms TEXT,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_insurance_policies (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        product_name TEXT NOT NULL,
        policy_type TEXT NOT NULL,
        sum_assured TEXT NOT NULL,
        annual_premium TEXT NOT NULL,
        term_years INTEGER NOT NULL,
        payment_years INTEGER NOT NULL,
        insured_name TEXT,
        insured_age INTEGER,
        insured_gender TEXT,
        status TEXT DEFAULT 'active',
        extra_terms TEXT,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_portfolios (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        name TEXT NOT NULL,
        base_currency TEXT DEFAULT 'CNY',
        FOREIGN KEY (family_id) REFERENCES fin4_family(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_holdings (
        id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        asset_name TEXT NOT NULL,
        asset_code TEXT,
        shares TEXT NOT NULL,
        cost_basis_price TEXT NOT NULL,
        current_price TEXT,
        updated_at TIMESTAMP,
        FOREIGN KEY (portfolio_id) REFERENCES fin4_portfolios(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_rate_snapshots (
        id TEXT PRIMARY KEY,
        rate_type TEXT NOT NULL,
        term TEXT,
        rate TEXT NOT NULL,
        effective_date TEXT,
        source TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_import_rules (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        pattern TEXT NOT NULL,
        category_id TEXT,
        priority INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id),
        FOREIGN KEY (category_id) REFERENCES fin4_categories(id)
    );
    """,
    # V2: 外部系统链接
    """
    CREATE TABLE IF NOT EXISTS fin4_integrations (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        name TEXT NOT NULL,
        link_type TEXT NOT NULL CHECK(link_type IN ('bank', 'broker', 'fund', 'other')),
        url TEXT NOT NULL,
        username_hint TEXT,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id)
    );
    """,
    # V3: 安全相关
    """
    CREATE TABLE IF NOT EXISTS fin4_security_config (
        family_id TEXT PRIMARY KEY,
        password_hash TEXT,
        pin_hash TEXT,
        encryption_enabled INTEGER DEFAULT 0,
        backup_enabled INTEGER DEFAULT 1,
        backup_interval_days INTEGER DEFAULT 7,
        backup_retention_count INTEGER DEFAULT 10,
        last_backup_at TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS fin4_audit_log (
        id TEXT PRIMARY KEY,
        family_id TEXT NOT NULL,
        user TEXT NOT NULL,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        details TEXT,
        ip TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (family_id) REFERENCES fin4_family(id)
    );
    """,
    # 索引
    "CREATE INDEX IF NOT EXISTS idx_txn_date ON fin4_transactions(date);",
    "CREATE INDEX IF NOT EXISTS idx_txn_account ON fin4_transactions(debit_account_id, credit_account_id);",
    "CREATE INDEX IF NOT EXISTS idx_accounts_family ON fin4_accounts(family_id);",
    "CREATE INDEX IF NOT EXISTS idx_audit_family ON fin4_audit_log(family_id, created_at);",
]


def get_db(db_path: str = None) -> sqlite3.Connection:
    """获取数据库连接"""
    if db_path is None:
        db_path = str(DB_DIR / "fin_l4.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str = None):
    """初始化数据库（执行所有迁移）"""
    global _global_conn
    conn = get_db(db_path)
    _global_conn = conn
    for migration in MIGRATIONS:
        if callable(migration):
            migration()
        else:
            conn.executescript(migration)
    conn.commit()
    return conn


def get_db_path(family_id: str = None) -> str:
    """获取数据库路径（支持多家庭隔离）"""
    if family_id:
        return str(DB_DIR / f"fin_l4_{family_id}.db")
    return str(DB_DIR / "fin_l4.db")

# 迁移: insurance 表加 start_date（忽略已存在错误）
MIGRATIONS.append("""
    SELECT 1;
""")
# 用 try/except 方式加列
def _add_insurance_start_date():
    try:
        _global_conn.execute("ALTER TABLE fin4_insurance_policies ADD COLUMN start_date TEXT")
        _global_conn.commit()
    except Exception:
        pass

MIGRATIONS.append(_add_insurance_start_date)
