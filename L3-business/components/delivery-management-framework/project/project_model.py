#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Project Model — 项目核心模型
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import datetime
from models.base import BaseModel

@dataclass
class Project(BaseModel):
    """项目实体"""
    name: str = ""
    description: Optional[str] = None
    type: str = "generic"
    status: str = "initiated"
    priority: str = "medium"
    planned_start: Optional[datetime.date] = None
    planned_end: Optional[datetime.date] = None
    actual_start: Optional[datetime.date] = None
    actual_end: Optional[datetime.date] = None
    budget: Optional[float] = None
    currency: str = "CNY"
    owner_id: Optional[str] = None
    proprietary_metadata: Optional[Dict[str, Any]] = field(default_factory=dict)

    def dict(self):
        d = super().dict()
        # 序列化日期和 JSON 字段
        if d["planned_start"]:
            d["planned_start"] = d["planned_start"].isoformat()
        if d["planned_end"]:
            d["planned_end"] = d["planned_end"].isoformat()
        if d["actual_start"]:
            d["actual_start"] = d["actual_start"].isoformat()
        if d["actual_end"]:
            d["actual_end"] = d["actual_end"].isoformat()
        if d["proprietary_metadata"] is not None:
            import json
            d["proprietary_metadata"] = json.dumps(d["proprietary_metadata"])
        return d

from repo.base_repo import BaseRepository

class ProjectRepository(BaseRepository[Project]):
    """项目 Repository"""

    def __init__(self, db_path: str):
        super().__init__(db_path, Project)
