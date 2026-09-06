"""Schema 迁移引擎。

版本号 + 迁移脚本模式。按版本顺序执行，幂等设计。
"""
from __future__ import annotations

import importlib
from pathlib import Path

from persistence.connection import get_connection

SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


def get_current_version(conn) -> int:
    """获取当前 schema 版本号。"""
    conn.execute(SCHEMA_TABLE)
    row = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()
    return row[0] or 0 if row else 0


def apply_migration(conn, version: int, sql: str) -> None:
    """执行单个迁移并记录版本。"""
    conn.cursor().executescript(sql)
    conn.execute(
        "INSERT INTO _schema_version (version, applied_at) VALUES (?, datetime('now'))",
        (version,),
    )
    conn.commit()


def run_migrations() -> None:
    """运行所有待执行的迁移。"""
    conn = get_connection()
    current = get_current_version(conn)

    schemas_pkg = Path(__file__).parent / "schemas"
    if not schemas_pkg.is_dir():
        return

    migrations: list[tuple[int, str]] = []
    for f in sorted(schemas_pkg.glob("v*.py")):
        version_str = f.stem[1:].split("_")[0]
        try:
            version = int(version_str)
        except ValueError:
            continue
        module = importlib.import_module(f"persistence.schemas.{f.stem}")
        sql = getattr(module, "MIGRATION", None)
        if sql and version > current:
            migrations.append((version, sql))

    for version, sql in sorted(migrations, key=lambda x: x[0]):
        apply_migration(conn, version, sql)
