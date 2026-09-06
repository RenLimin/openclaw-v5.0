"""数据库连接管理。

提供线程安全的 SQLite 连接，启用 WAL 模式和外键约束。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import local

DATA_DIR = Path.home() / ".openclaw" / "data"
DB_PATH = DATA_DIR / "platform.db"

_thread_local = local()


def get_connection() -> sqlite3.Connection:
    """获取当前线程的数据库连接（懒初始化）。"""
    conn = getattr(_thread_local, "conn", None)
    if conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _thread_local.conn = conn
    return conn


def close() -> None:
    """关闭当前线程的连接。"""
    conn = getattr(_thread_local, "conn", None)
    if conn is not None:
        conn.close()
        _thread_local.conn = None


def init_schema() -> None:
    """初始化/迁移 schema。"""
    from persistence.migration import run_migrations
    run_migrations()
