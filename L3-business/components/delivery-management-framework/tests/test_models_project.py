# -*- coding: utf-8 -*-
"""Project 模型测试。"""

import datetime
from project.project_model import Project


class TestProject:
    """Project 核心模型测试。"""

    def test_default_values(self):
        """Project 应有合理的默认值。"""
        p = Project(name="测试项目")
        assert p.name == "测试项目"
        assert p.status == "initiated"
        assert p.priority == "medium"
        assert p.type == "generic"
        assert p.currency == "CNY"
        assert p.description is None
        assert p.budget is None

    def test_auto_inherited_fields(self):
        """应继承 BaseModel 的自动字段。"""
        p = Project(name="A")
        assert p.id is not None
        assert p.created_at is not None
        assert p.updated_at is not None
        assert p.tenant_id is not None

    def test_dict_serializes_dates(self):
        """dict() 应将日期字段序列化为 ISO 格式字符串。"""
        p = Project(
            name="带日期项目",
            planned_start=datetime.date(2026, 1, 1),
            planned_end=datetime.date(2026, 6, 30),
        )
        d = p.dict()
        assert d["planned_start"] == "2026-01-01"
        assert d["planned_end"] == "2026-06-30"

    def test_dict_serializes_metadata(self):
        """dict() 应将 proprietary_metadata 序列化为 JSON 字符串。"""
        p = Project(
            name="带元数据项目",
            proprietary_metadata={"key": "value", "num": 42},
        )
        d = p.dict()
        import json
        parsed = json.loads(d["proprietary_metadata"])
        assert parsed == {"key": "value", "num": 42}

    def test_dict_none_dates_remain_none(self):
        """未设置的日期字段应保持 None。"""
        p = Project(name="无日期项目")
        d = p.dict()
        assert d["planned_start"] is None
        assert d["actual_end"] is None

    def test_custom_status_and_priority(self):
        """应支持自定义状态和优先级。"""
        p = Project(name="定制", status="active", priority="high")
        assert p.status == "active"
        assert p.priority == "high"
