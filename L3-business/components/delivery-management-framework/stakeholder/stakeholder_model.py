#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stakeholder Model — 干系人模型
"""

from dataclasses import dataclass
from typing import Optional
from L3-business.components.delivery-management-framework.models.base import BaseModel

@dataclass
class Stakeholder(BaseModel):
    """干系人实体"""
    project_id: str = ""
    name: str = ""
    role: Optional[str] = None
    org: Optional[str] = None
    influence: str = "medium"  # low | medium | high
    interest: str = "medium"  # low | medium | high
    notes: Optional[str] = None

    def dict(self):
        return super().dict()

from L3-business.components.delivery-management-framework.repo.base_repo import BaseRepository

class StakeholderRepository(BaseRepository[Stakeholder]):
    """干系人 Repository"""

    def __init__(self, db_path: str):
        super().__init__(db_path, Stakeholder)

    def list_by_project(self, project_id: str) -> list[Stakeholder]:
        """列出项目所有干系人"""
        sql = f"SELECT * FROM {self.table_name} WHERE project_id = ? AND tenant_id = ? ORDER BY name;"
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, (project_id, self._current_tenant()))
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]
