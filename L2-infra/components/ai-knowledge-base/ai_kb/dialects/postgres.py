"""
PostgreSQL dialect implementation
"""
import psycopg2
from psycopg2.extensions import connection as Connection
import datetime
from typing import Optional, List, Tuple, Any, Dict

from ai_kb.dialects.base import BaseDialect


class PostgresDialect(BaseDialect):
    """PostgreSQL dialect implementation"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "aikb",
        user: str = "postgres",
        password: str = "",
        sslmode: str = None
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.sslmode = sslmode
        self.conn: Optional[Connection] = None

    def connect(self, **kwargs):
        conn_kwargs = {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
        }
        if self.sslmode:
            conn_kwargs["sslmode"] = self.sslmode
        self.conn = psycopg2.connect(**conn_kwargs)
        # psycopg2 by default returns dict-like rows
        # We don't need row_factory, psycopg2 does it with RealDictCursor

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def execute(self, sql: str, params: Tuple = ()):
        if not self.conn:
            self.connect()
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else cur

    def commit(self):
        if self.conn:
            self.conn.commit()

    def get_now(self) -> str:
        return datetime.datetime.now().isoformat()
