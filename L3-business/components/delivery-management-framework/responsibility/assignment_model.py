#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Responsibility Assignment Model — RACI 责任分配模型
"""

from dataclasses import dataclass
from typing import Optional
from models.base import BaseModel

@dataclass
class ResponsibilityAssignment(BaseModel):
    """责任分配实体"""
    project_id: str = ""
    work_item_id: Optional[str] = None  # 如果是项目级分配，留空
    member_id: str = ""
    capability: str = ""
    raci_role: str = ""  # R | A | C | I
    notes: Optional[str] = None

    def dict(self):
        return super().dict()

from repo.base_repo import BaseRepository

class ResponsibilityAssignmentRepository(BaseRepository[ResponsibilityAssignment]):
    """责任分配 Repository"""

    def __init__(self, db_path: str):
        super().__init__(db_path, ResponsibilityAssignment)

    def list_by_project(self, project_id: str, work_item_id: Optional[str] = None) -> list[ResponsibilityAssignment]:
        """列出项目/工作项责任分配"""
        sql = f"SELECT * FROM {self.table_name} WHERE project_id = ? AND tenant_id = ?"
        params = [project_id, self._current_tenant()]
        if work_item_id is not None:
            sql += " AND work_item_id = ?"
            params.append(work_item_id)
        sql += " ORDER BY capability;"

        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]
