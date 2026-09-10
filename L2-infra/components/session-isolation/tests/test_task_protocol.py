"""
Task Protocol 测试 — 任务初始化 + ID 校验 + 目标更新
"""
import os
import pytest
from utils import validate_task_id, load_task_yaml, save_task_yaml
from task_init import TaskInitializer


class TestValidateTaskId:
    """任务 ID 格式校验"""

    def test_valid_task_id(self):
        ok, err = validate_task_id("task-20260910-test-slug")
        assert ok is True
        assert err == ""

    def test_valid_with_numbers_in_slug(self):
        ok, err = validate_task_id("task-20260910-abc123")
        assert ok is True

    def test_invalid_missing_prefix(self):
        ok, err = validate_task_id("20260910-test")
        assert ok is False
        assert "Invalid task_id format" in err

    def test_invalid_wrong_date_format(self):
        ok, err = validate_task_id("task-0910-test")
        assert ok is False

    def test_invalid_empty_slug(self):
        ok, err = validate_task_id("task-20260910-")
        assert ok is False

    def test_invalid_special_chars(self):
        ok, err = validate_task_id("task-20260910-test_underscore")
        assert ok is False


class TestTaskInitializer:
    """任务初始化器"""

    def test_create_task_success(self, tmp_workspace):
        ti = TaskInitializer()
        ok, msg = ti.create_task(
            task_id="task-20260910-utest",
            name="单元测试任务",
            owner="test-agent",
            scope_project="test-proj",
            scope_component="test-comp",
            scope_version="v1.0",
            goals=[{"id": "g1", "description": "完成测试", "status": "pending"}],
            priority="high",
        )
        assert ok is True
        assert "created successfully" in msg

        # 验证目录结构
        task_path = tmp_workspace / "tasks" / "in-progress" / "task-20260910-utest"
        assert task_path.is_dir()
        assert (task_path / "TASK.yml").exists()
        assert (task_path / "CONTEXT.md").exists()
        assert (task_path / "events.jsonl").exists()

    def test_create_task_duplicate(self, tmp_workspace):
        ti = TaskInitializer()
        ok, _ = ti.create_task(
            task_id="task-20260910-dup",
            name="重复任务",
            owner="test",
            scope_project="p",
            scope_component="c",
            scope_version="v1",
            goals=[{"id": "g1", "description": "x", "status": "pending"}],
        )
        assert ok is True

        # 重复创建
        ok2, msg2 = ti.create_task(
            task_id="task-20260910-dup",
            name="重复任务2",
            owner="test",
            scope_project="p",
            scope_component="c",
            scope_version="v1",
            goals=[{"id": "g1", "description": "x", "status": "pending"}],
        )
        assert ok2 is False
        assert "already exists" in msg2

    def test_create_task_invalid_id(self, tmp_workspace):
        ti = TaskInitializer()
        ok, msg = ti.create_task(
            task_id="bad-id",
            name="坏ID任务",
            owner="test",
            scope_project="p",
            scope_component="c",
            scope_version="v1",
            goals=[],
        )
        assert ok is False
        assert "Invalid task_id format" in msg

    def test_create_task_with_context_paths(self, tmp_workspace):
        ti = TaskInitializer()
        ok, msg = ti.create_task(
            task_id="task-20260910-ctx",
            name="带上下文任务",
            owner="test",
            scope_project="p",
            scope_component="c",
            scope_version="v1",
            goals=[{"id": "g1", "description": "x", "status": "pending"}],
            context_paths=["docs/a.md", "docs/b.md"],
        )
        assert ok is True

        data, err = load_task_yaml("task-20260910-ctx")
        assert err == ""
        assert len(data["context"]) == 2
        assert data["context"][0]["path"] == "docs/a.md"

    def test_task_yml_has_correct_fields(self, tmp_workspace):
        ti = TaskInitializer()
        ti.create_task(
            task_id="task-20260910-fields",
            name="字段验证",
            owner="rex",
            scope_project="bdms",
            scope_component="report",
            scope_version="v2.0",
            goals=[{"id": "g1", "description": "目标1", "status": "pending"}],
            priority="urgent",
        )
        data, err = load_task_yaml("task-20260910-fields")
        assert err == ""
        assert data["id"] == "task-20260910-fields"
        assert data["name"] == "字段验证"
        assert data["owner"] == "rex"
        assert data["priority"] == "urgent"
        assert data["scope"]["project"] == "bdms"
        assert data["scope"]["component"] == "report"
        assert data["scope"]["version"] == "v2.0"
        assert len(data["goals"]) == 1


class TestGoalUpdate:
    """目标状态更新"""

    def test_update_goal_status(self, tmp_workspace):
        from service import SessionIsolationService

        svc = SessionIsolationService()
        svc.create_task(
            task_id="task-20260910-goal",
            name="目标更新测试",
            owner="test",
            scope_project="p",
            scope_component="c",
            scope_version="v1",
            goals=[
                {"id": "g1", "description": "目标1", "status": "pending"},
                {"id": "g2", "description": "目标2", "status": "pending"},
            ],
        )

        ok, msg = svc.update_task_goal_status("task-20260910-goal", "g1", "done")
        assert ok is True

        data, _ = load_task_yaml("task-20260910-goal")
        assert data["goals"][0]["status"] == "done"
        assert data["goals"][1]["status"] == "pending"

    def test_update_nonexistent_goal(self, tmp_workspace):
        from service import SessionIsolationService

        svc = SessionIsolationService()
        svc.create_task(
            task_id="task-20260910-nogoal",
            name="无此目标",
            owner="test",
            scope_project="p",
            scope_component="c",
            scope_version="v1",
            goals=[{"id": "g1", "description": "x", "status": "pending"}],
        )

        ok, msg = svc.update_task_goal_status("task-20260910-nogoal", "g99", "done")
        assert ok is False
        assert "not found" in msg
