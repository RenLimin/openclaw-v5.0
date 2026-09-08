#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BaseRepository — 统一数据访问基类
支持 SQLite 持久化，租户隔离
"""

import sqlite3
import json
from typing import List, Optional, Dict, Any, Type
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

class BaseRepository[T]:
    """基础 Repository"""

    def __init__(self, db_path: str, model_class: Type[T], table_name: Optional[str] = None):
        self.db_path = db_path
        self.model_class = model_class
        self.table_name = table_name or model_class.table_name()

    @contextmanager
    def get_connection(self):
        """获取数据库连接，自动开启 WAL 模式"""
        conn = sqlite3.connect(self.db_path)
        try:
            # 启用 WAL 模式，提高并发性能
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_table_if_not_exists(self, create_sql: str) -> None:
        """创建表如果不存在"""
        with self.get_connection() as conn:
            conn.execute(create_sql)

    def insert(self, model: T) -> bool:
        """插入一条记录"""
        model_dict = model.dict()
        columns = ", ".join(model_dict.keys())
        placeholders = ", ".join([f":{k}" for k in model_dict.keys()])
        sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders});"

        with self.get_connection() as conn:
            try:
                cursor = conn.execute(sql, model_dict)
                return cursor.rowcount > 0
            except sqlite3.IntegrityError as e:
                logger.error(f"Insert failed: {e}")
                return False

    def update(self, model: T) -> bool:
        """更新一条记录"""
        model_dict = model.dict()
        set_clause = ", ".join([f"{k} = :{k}" for k in model_dict.keys() if k != "id"])
        sql = f"UPDATE {self.table_name} SET {set_clause} WHERE id = :id;"

        with self.get_connection() as conn:
            try:
                cursor = conn.execute(sql, model_dict)
                return cursor.rowcount > 0
            except sqlite3.IntegrityError as e:
                logger.error(f"Update failed: {e}")
                return False

    def upsert(self, model: T) -> bool:
        """插入或更新"""
        existing = self.get_by_id(model.id)
        if existing:
            return self.update(model)
        else:
            return self.insert(model)

    def get_by_id(self, id: str) -> Optional[T]:
        """根据 ID 获取"""
        sql = f"SELECT * FROM {self.table_name} WHERE id = ? AND tenant_id = ?;"
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, (id, self._current_tenant()))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    def list_all(self) -> List[T]:
        """列出当前租户所有记录"""
        sql = f"SELECT * FROM {self.table_name} WHERE tenant_id = ?;"
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, (self._current_tenant(),))
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]

    def delete_by_id(self, id: str) -> bool:
        """删除记录"""
        sql = f"DELETE FROM {self.table_name} WHERE id = ? AND tenant_id = ?;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (id, self._current_tenant()))
            return cursor.rowcount > 0

    def count(self) -> int:
        """统计当前租户记录数"""
        sql = f"SELECT COUNT(*) FROM {self.table_name} WHERE tenant_id = ?;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (self._current_tenant(),))
            return cursor.fetchone()[0]

    def _row_to_model(self, row: sqlite3.Row) -> T:
        """转换 SQLite 行到模型实例"""
        data = dict(row)
        # 处理 JSON 字段（如果需要）
        for key, value in data.items():
            if isinstance(value, str) and (value.startswith("{") or value.startswith("[")):
                try:
                    data[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass
        return self.model_class(**data)

    def _current_tenant(self) -> str:
        """获取当前租户，从 BaseModel 上下文获取"""
        from ..models.base import TenantContext
        return TenantContext.current()
