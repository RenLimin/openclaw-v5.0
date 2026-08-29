"""数据库连接管理

SQLite 数据库连接和基础操作。
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
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    # 签约项目表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT,
            合同编号 TEXT,
            客户名称 TEXT,
            签约金额 REAL,
            项目经理 TEXT,
            部门 TEXT,
            项目状态 TEXT,
            创建日期 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 确收凭证表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            合同编号 TEXT,
            确收金额 REAL,
            确收日期 DATE,
            创建日期 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 验收凭证表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS acceptance_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            合同编号 TEXT,
            验收日期 DATE,
            是否合格 TEXT,
            创建日期 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 月度报告记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT UNIQUE,
            report_type TEXT,
            file_path TEXT,
            生成日期 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("数据库初始化完成")


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
