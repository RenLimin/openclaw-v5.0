"""
Event Protocol 测试 — append-only 事件日志
"""
import json
import pytest
from event_logger import EventLogger
from task_init import TaskInitializer


@pytest.fixture
def sample_task(tmp_workspace):
    """创建一个测试用任务"""
    ti = TaskInitializer()
    ti.create_task(
        task_id="task-20260910-event",
        name="事件测试任务",
        owner="test",
        scope_project="p",
        scope_component="c",
        scope_version="v1",
        goals=[{"id": "g1", "description": "x", "status": "pending"}],
    )
    return "task-20260910-event"


class TestEventLogger:
    """事件日志"""

    def test_log_event(self, sample_task):
        el = EventLogger()
        ok, msg = el.log_event(sample_task, "task.started", {"by": "test-agent"})
        assert ok is True
        assert "logged" in msg

    def test_log_event_nonexistent_task(self):
        el = EventLogger()
        ok, msg = el.log_event("task-20260910-noexist", "test", {})
        assert ok is False
        assert "not found" in msg

    def test_read_events(self, sample_task):
        el = EventLogger()
        el.log_event(sample_task, "event.one", {"data": 1})
        el.log_event(sample_task, "event.two", {"data": 2})
        el.log_event(sample_task, "event.three", {"data": 3})

        events, err = el.read_events(sample_task)
        assert err == ""
        assert len(events) == 3
        assert events[0]["type"] == "event.one"
        assert events[1]["type"] == "event.two"
        assert events[2]["type"] == "event.three"

    def test_read_events_with_limit(self, sample_task):
        el = EventLogger()
        for i in range(10):
            el.log_event(sample_task, f"event.{i}", {"i": i})

        events, _ = el.read_events(sample_task, limit=3)
        assert len(events) == 3
        assert events[0]["type"] == "event.0"
        assert events[2]["type"] == "event.2"

    def test_event_has_timestamp(self, sample_task):
        el = EventLogger()
        el.log_event(sample_task, "test.ts", {})
        events, _ = el.read_events(sample_task)
        assert "ts" in events[0]
        # ISO 格式检查
        assert "T" in events[0]["ts"]

    def test_event_includes_data_fields(self, sample_task):
        el = EventLogger()
        el.log_event(sample_task, "goal.completed", {"goal_id": "g1", "by": "agent-x"})
        events, _ = el.read_events(sample_task)
        assert events[0]["goal_id"] == "g1"
        assert events[0]["by"] == "agent-x"

    def test_clear_events(self, sample_task):
        el = EventLogger()
        el.log_event(sample_task, "e1", {})
        el.log_event(sample_task, "e2", {})

        ok, _ = el.clear_events(sample_task)
        assert ok is True

        events, _ = el.read_events(sample_task)
        assert len(events) == 0
