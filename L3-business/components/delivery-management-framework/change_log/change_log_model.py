#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChangeLog Model — 变更日志记录
"""

from dataclasses import dataclass
from typing import Optional
from L3-business.components.delivery-management-framework.models.base import BaseModel

@dataclass
class ChangeLog(BaseModel):
    """变更日志实体"""
    entity_type: str = ""
    entity_id: str = ""
    action: str = ""  # create | update | delete | status_change
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    actor_id: Optional[str] = None

    def dict(self):
        return super().dict()

from L3-business.components.delivery-management-framework.repo.base_repo import BaseRepository

class ChangeLogRepository(BaseRepository[ChangeLog]):
    """变更日志 Repository"""

    def __init__(self, db_path: str):
        super().__init__(db_path, ChangeLog)

    def list_by_entity(self, entity_type: str, entity_id: str) -> list[ChangeLog]:
        """列出实体变更历史"""
        sql = f"SELECT * FROM {self.table_name} WHERE entity_type = ? AND entity_id = ? AND tenant_id = ? ORDER BY created_at DESC;"
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, (entity_type, entity_id, self._current_tenant()))
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]
