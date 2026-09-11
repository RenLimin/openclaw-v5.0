# -*- coding: utf-8 -*-
"""WorkItem 模型测试。"""

import datetime
from work_item.work_item_model import WorkItem


class TestWorkItem:
    """WorkItem 核心模型测试。"""

    def test_default_values(self):
        """WorkItem 应有合理的默认值。"""
        wi = WorkItem(project_id="p1", title="任务A")
        assert wi.project_id == "p1"
        assert wi.title == "任务A"
        assert wi.type == "task"
        assert wi.status == "draft"
        assert wi.priority == "medium"
        assert wi.assignee_id is None

    def test_dict_serializes_dates(self):
        """dict() 应将日期字段序列化为 ISO 格式字符串。"""
        wi = WorkItem(
            project_id="p1",
            title="带日期任务",
            planned_date=datetime.date(2026, 3, 1),
            due_date=datetime.date(2026, 3, 31),
        )
        d = wi.dict()
        assert d["planned_date"] == "2026-03-01"
        assert d["due_date"] == "2026-03-31"

    def test_dict_serializes_metadata(self):
        """dict() 应将 metadata 序列化为 JSON 字符串。"""
        wi = WorkItem(
            project_id="p1",
            title="带元数据任务",
            metadata={"tag": "urgent"},
        )
        d = wi.dict()
        import json
        parsed = json.loads(d["metadata"])
        assert parsed == {"tag": "urgent"}

    def test_various_types(self):
        """应支持多种工作项类型。"""
        for t in ["task", "milestone", "deliverable", "risk", "decision", "change"]:
            wi = WorkItem(project_id="p1", title=f"{t}项", type=t)
            assert wi.type == t

    def test_hierarchy(self):
        """应支持父子层级关系。"""
        parent = WorkItem(project_id="p1", title="父任务")
        child = WorkItem(project_id="p1", title="子任务", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_hours_tracking(self):
        """应支持工时跟踪。"""
        wi = WorkItem(
            project_id="p1",
            title="工时任务",
            estimated_hours=8.0,
            actual_hours=6.5,
        )
        assert wi.estimated_hours == 8.0
        assert wi.actual_hours == 6.5
