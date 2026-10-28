"""SQLite 持久化 — bangcle-contract MVP

严格按 DESIGN-DETAIL-v1.0 §7 建三张表：
  reviews / kb_matches / audit_logs

约束：
- audit_logs 为 append-only：本模块只暴露 INSERT，不提供任何
  UPDATE / DELETE 审计表的方法（见 VERIFICATION §7）。
- DB 文件落组件 ``data/`` 目录（gitignored），提供默认路径解析。
- 仅依赖标准库 sqlite3。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

# ------------------------------------------------------------
# 路径解析
# ------------------------------------------------------------

# repository/db.py -> repository -> 组件根
COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(COMPONENT_ROOT, "data")
DEFAULT_DB_NAME = "bangcle_contract.db"


def default_db_path() -> str:
    """返回默认 SQLite 文件路径（组件 data/ 目录）。"""
    return os.path.join(DEFAULT_DATA_DIR, DEFAULT_DB_NAME)


# ------------------------------------------------------------
# Schema（DETAIL §7）
# ------------------------------------------------------------

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_ref     TEXT    NOT NULL,
        source           TEXT    NOT NULL,
        overall_risk     TEXT    NOT NULL,
        satisfaction     TEXT    NOT NULL,
        rule_set_version TEXT,
        report_path      TEXT,
        created_at       TEXT    NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kb_matches (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        review_id       INTEGER NOT NULL,
        input_name      TEXT    NOT NULL,
        matched_product TEXT,
        matched_sku     TEXT,
        score           REAL,
        alert           TEXT,
        FOREIGN KEY (review_id) REFERENCES reviews (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        review_id  INTEGER,
        action     TEXT    NOT NULL,
        operator   TEXT    NOT NULL,
        detail     TEXT,
        created_at TEXT    NOT NULL,
        FOREIGN KEY (review_id) REFERENCES reviews (id)
    )
    """,
)


def _connect(db_path: str) -> sqlite3.Connection:
    directory = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # 外键约束开启，保证 kb_matches / audit_logs 引用完整性
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Optional[str] = None) -> str:
    """初始化数据库：创建三张表（幂等，IF NOT EXISTS）。

    Args:
        db_path: 目标 DB 文件路径；为 None 时使用默认路径。

    Returns:
        实际使用的 DB 文件绝对路径。
    """
    path = db_path or default_db_path()
    conn = _connect(path)
    try:
        with conn:
            for stmt in _SCHEMA_STATEMENTS:
                conn.execute(stmt)
    finally:
        conn.close()
    return os.path.abspath(path)


# ------------------------------------------------------------
# 轻量 Repository
# ------------------------------------------------------------

class Repository:
    """最小持久化仓储（本期仅 4 个写/读方法）。

    审计表 append-only：这里只有 ``append_audit_log``（INSERT），
    刻意不提供 update/delete 审计的入口。
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        # 确保表已存在（幂等）
        self.db_path = init_db(db_path)
        self._conn = _connect(self.db_path)

    # ---- 上下文管理 / 资源释放 ----
    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---- reviews ----
    def add_review(
        self,
        contract_ref: str,
        source: str,
        overall_risk: str,
        satisfaction: str,
        report_path: str = "",
        rule_set_version: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> int:
        """插入一条审查记录，返回其 id。"""
        created_at = created_at or datetime.now().isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO reviews
                (contract_ref, source, overall_risk, satisfaction,
                 rule_set_version, report_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (contract_ref, source, overall_risk, satisfaction,
             rule_set_version, report_path, created_at),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # ---- kb_matches ----
    def add_kb_match(
        self,
        review_id: int,
        input_name: str,
        matched_product: Optional[str] = None,
        matched_sku: Optional[str] = None,
        score: Optional[float] = None,
        alert: Optional[str] = None,
    ) -> int:
        """插入一条 KB 匹配明细，返回其 id。"""
        cur = self._conn.execute(
            """
            INSERT INTO kb_matches
                (review_id, input_name, matched_product, matched_sku, score, alert)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (review_id, input_name, matched_product, matched_sku, score, alert),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # ---- audit_logs：仅 INSERT（append-only）----
    def append_audit_log(
        self,
        action: str,
        operator: str,
        review_id: Optional[int] = None,
        detail: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> int:
        """追加一条审计日志（只增不改不删），返回其 id。"""
        created_at = created_at or datetime.now().isoformat()
        cur = self._conn.execute(
            """
            INSERT INTO audit_logs
                (review_id, action, operator, detail, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (review_id, action, operator, detail, created_at),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # ---- 读取 ----
    def get_review(self, review_id: int) -> Optional[Dict[str, Any]]:
        """按 id 取审查记录（含其 KB 匹配与审计日志），无则返回 None。"""
        row = self._conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)
        ).fetchone()
        if row is None:
            return None
        record: Dict[str, Any] = dict(row)

        kb_rows = self._conn.execute(
            "SELECT * FROM kb_matches WHERE review_id = ? ORDER BY id",
            (review_id,),
        ).fetchall()
        record["kb_matches"] = [dict(r) for r in kb_rows]

        audit_rows = self._conn.execute(
            "SELECT * FROM audit_logs WHERE review_id = ? ORDER BY id",
            (review_id,),
        ).fetchall()
        record["audit_logs"] = [dict(r) for r in audit_rows]
        return record
