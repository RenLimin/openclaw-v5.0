"""
SQLite dialect implementation
"""
import sqlite3
import datetime
from typing import Optional, List, Tuple, Any, Dict

from ai_kb.dialects.base import BaseDialect


class SQLiteDialect(BaseDialect):
    """SQLite dialect implementation"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self, **kwargs):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute(self, sql: str, params: Tuple = ()):
        if not self.conn:
            self.connect()
        return self.conn.execute(sql, params)

    def commit(self):
        if self.conn:
            self.conn.commit()

    def get_now(self) -> str:
        return datetime.datetime.now().isoformat()

    # --- The rest is implemented in ai_kb/db.py but we'll keep the interface
    # FIXME: we need to refactor db.py to use this dialect, but for now this is interface for future refactoring
    # The base methods below are stubs for now — complete interface is coming in next refactor
