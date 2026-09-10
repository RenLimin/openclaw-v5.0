"""数据库连接管理

SQLite 数据库连接和基础操作。
Bangcle 交付管理系统 (BDMS) 的数据持久层。
"""

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".openclaw" / "data" / "bdms.db"


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    # OA 合同台账
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oa_contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            htbh TEXT UNIQUE,
            合同名称 TEXT,
            客户名称 TEXT,
            签约金额 REAL,
            责任销售 TEXT,
            责任销售部门 TEXT,
            签约销售 TEXT,
            签约销售团队 TEXT,
            创建日期 DATE,
            申请日期 DATE,
            服务开始日期 DATE,
            服务结束日期 DATE,
            直签或代理 TEXT,
            合同分类 TEXT,
            归档状态 TEXT,
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ONES 项目
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ones_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT UNIQUE,
            项目名称 TEXT,
            合同编号 TEXT,
            客户名称 TEXT,
            项目经理 TEXT,
            部门 TEXT,
            项目状态 TEXT,
            立项日期 DATE,
            预估结项日期 DATE,
            实际结项日期 DATE,
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 确收凭证
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_id TEXT,
            bi_id TEXT,
            合同编号 TEXT,
            合同名称 TEXT,
            客户名称 TEXT,
            销售部门 TEXT,
            项目经理 TEXT,
            交接日期 DATE,
            财务 TEXT,
            是否接收 TEXT,
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 验收凭证
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acceptance_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_id TEXT,
            bi_id TEXT,
            合同编号 TEXT,
            合同名称 TEXT,
            客户名称 TEXT,
            项目经理 TEXT,
            验收单编号 TEXT,
            交接日期 DATE,
            验收方式 TEXT,
            全部或部分 TEXT,
            财务 TEXT,
            财务是否接收 TEXT,
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 工时数据
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workhours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            工作项 TEXT,
            总工时 REAL,
            迁移工时 REAL,
            剩余工时 REAL,
            月份 TEXT,
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 月度报告记录
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT UNIQUE,
            report_type TEXT,
            file_path TEXT,
            生成日期 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_oa_htbh ON oa_contracts(htbh)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ones_project_id ON ones_projects(project_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ones_contract_no ON ones_projects(合同编号)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rev_contract_no ON revenue_vouchers(合同编号)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_acc_contract_no ON acceptance_vouchers(合同编号)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workhour_month ON workhours(月份)")

    conn.commit()
    conn.close()
    print(f"✅ 数据库初始化完成: {DB_PATH}")


def query(sql: str, params: tuple = ()) -> list:
    """执行查询"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()
    return results


def execute(sql: str, params: tuple = ()) -> int:
    """执行写入"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()
    rowid = cursor.lastrowid
    conn.close()
    return rowid


def executemany(sql: str, params_list: list) -> int:
    """批量写入"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executemany(sql, params_list)
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count


def upsert(table: str, data: dict, unique_key: str) -> int:
    """插入或更新"""
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    updates = ", ".join([f"{k}=excluded.{k}" for k in data.keys() if k != unique_key])
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT({unique_key}) DO UPDATE SET {updates}"
    return execute(sql, tuple(data.values()))


if __name__ == "__main__":
    init_db()
