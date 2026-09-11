#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkItem Model — 统一工作项模型
涵盖 task / milestone / deliverable / risk / decision / ...
统一建模，扩展性好
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import datetime
from models.base import BaseModel

@dataclass
class WorkItem(BaseModel):
    """统一工作项实体"""
    project_id: str = ""
    type: str = "task"  # task | milestone | deliverable | risk | decision | change
    title: str = ""
    description: Optional[str] = None
    status: str = "draft"  # draft | active | blocked | completed | cancelled | approved
    priority: str = "medium"  # low | medium | high | critical
    assignee_id: Optional[str] = None
    reviewer_id: Optional[str] = None
    planned_date: Optional[datetime.date] = None
    actual_date: Optional[datetime.date] = None
    due_date: Optional[datetime.date] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    parent_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def dict(self):
        d = super().dict()
        # 序列化日期和 JSON 字段
        if d["planned_date"]:
            d["planned_date"] = d["planned_date"].isoformat()
        if d["actual_date"]:
            d["actual_date"] = d["actual_date"].isoformat()
        if d["due_date"]:
            d["due_date"] = d["due_date"].isoformat()
        if d["metadata"] is not None:
            import json
            d["metadata"] = json.dumps(d["metadata"])
        return d

from repo.base_repo import BaseRepository

class WorkItemRepository(BaseRepository[WorkItem]):
    """工作项 Repository"""

    def __init__(self, db_path: str):
        super().__init__(db_path, WorkItem)

    def list_by_project(self, project_id: str, type_filter: Optional[str] = None) -> list[WorkItem]:
        """列出项目下工作项，可以按类型过滤"""
        sql = f"SELECT * FROM {self.table_name} WHERE project_id = ? AND tenant_id = ?"
        params = [project_id, self._current_tenant()]
        if type_filter:
            sql += " AND type = ?"
            params.append(type_filter)
        sql += " ORDER BY created_at DESC;"

        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]
