"""Repository 基类。

提供通用的 CRUD 操作，子类只需定义 table_name。
"""
from __future__ import annotations

from typing import Any, Optional

from persistence.connection import get_connection


class Repository:
    """业务仓储基类。"""

    table_name: str

    def _conn(self):
        return get_connection()

    def _execute(self, sql: str, params: tuple = ()) -> Any:
        return self._conn().execute(sql, params)

    def get(self, id: str) -> Optional[dict]:
        """根据 ID 获取单条记录。"""
        row = self._execute(
            f"SELECT * FROM {self.table_name} WHERE id = ?", (id,)
        ).fetchone()
        return dict(row) if row else None

    def list(self, where: str = "", params: tuple = ()) -> list[dict]:
        """列出记录（可选过滤条件）。"""
        sql = f"SELECT * FROM {self.table_name}"
        if where:
            sql += f" WHERE {where}"
        rows = self._execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def create(self, **data) -> dict:
        """创建记录。"""
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        self._execute(
            f"INSERT INTO {self.table_name} ({cols}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        self._conn().commit()
        return data

    def update(self, id: str, **data) -> Optional[dict]:
        """更新记录。"""
        if not data:
            return self.get(id)
        sets = ", ".join(f"{k} = ?" for k in data.keys())
        self._execute(
            f"UPDATE {self.table_name} SET {sets} WHERE id = ?",
            (*data.values(), id),
        )
        self._conn().commit()
        return self.get(id)

    def delete(self, id: str) -> bool:
        """删除记录。"""
        cursor = self._execute(
            f"DELETE FROM {self.table_name} WHERE id = ?", (id,)
        )
        self._conn().commit()
        return cursor.rowcount > 0

    def count(self, where: str = "", params: tuple = ()) -> int:
        """计数。"""
        sql = f"SELECT COUNT(*) FROM {self.table_name}"
        if where:
            sql += f" WHERE {where}"
        row = self._execute(sql, params).fetchone()
        return row[0] if row else 0
