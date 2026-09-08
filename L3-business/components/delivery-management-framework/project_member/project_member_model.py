#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Project Member Model — 项目成员模型
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from L3-business.components.delivery-management-framework.models.base import BaseModel

@dataclass
class ProjectMember(BaseModel):
    """项目成员实体"""
    project_id: str = ""
    member_id: str = ""
    member_name: str = ""
    role_template: Optional[str] = None  # 角色模板名

    def dict(self):
        return super().dict()

from L3-business.components.delivery-management-framework.repo.base_repo import BaseRepository

class ProjectMemberRepository(BaseRepository[ProjectMember]):
    """项目成员 Repository"""

    def __init__(self, db_path: str):
        super().__init__(db_path, ProjectMember)

    def list_by_project(self, project_id: str) -> list[ProjectMember]:
        """列出项目所有成员"""
        sql = f"SELECT * FROM {self.table_name} WHERE project_id = ? AND tenant_id = ? ORDER BY member_name;"
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, (project_id, self._current_tenant()))
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]
