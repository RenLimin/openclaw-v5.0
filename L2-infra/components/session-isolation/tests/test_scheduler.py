"""
Task Scheduler 测试 — 拓扑排序 + 批次 + 优先级 + 环检测
"""
import os
import pytest
from scheduler import Task, TaskScheduler


def _make_task(task_id, deps=None, priority="medium", status="pending"):
    """快速创建 Task 实例（不涉及文件）"""
    return Task(
        id=task_id,
        name=f"Task {task_id}",
        status=status,
        dependencies=deps or [],
        priority=priority,
        scope={"project": "test", "component": "test", "version": "v1"},
        goals=[{"id": "g1", "description": "do it", "status": "pending"}],
        blockers=[],
        context=[],
        artifacts=[],
        created_at="2026-09-10T00:00:00+08:00",
        updated_at="2026-09-10T00:00:00+08:00",
        owner="test",
        file_path="",
    )


class TestTaskDataclass:
    """Task 数据类"""

    def test_is_pending(self):
        t = _make_task("t1")
        assert t.is_pending() is True

    def test_not_pending_when_in_progress(self):
        t = _make_task("t1", status="in-progress")
        assert t.is_pending() is False

    def test_is_blocked_by_unmet_deps(self):
        t = _make_task("t2", deps=["t1"])
        assert t.is_blocked_by_unmet_deps(set()) is True
        assert t.is_blocked_by_unmet_deps({"t1"}) is False


class TestTopologicalSort:
    """拓扑排序"""

    def test_no_dependencies_single_batch(self):
        sched = TaskScheduler()
        tasks = [_make_task("t1"), _make_task("t2"), _make_task("t3")]
        batches, done = sched.topological_sort(tasks)
        assert len(batches) == 1
        assert len(batches[0]) == 3
        assert len(done) == 3

    def test_linear_dependency(self):
        sched = TaskScheduler()
        t1 = _make_task("t1")
        t2 = _make_task("t2", deps=["t1"])
        t3 = _make_task("t3", deps=["t2"])
        batches, done = sched.topological_sort([t2, t3, t1])
        assert len(batches) == 3
        assert [t.id for t in batches[0]] == ["t1"]
        assert [t.id for t in batches[1]] == ["t2"]
        assert [t.id for t in batches[2]] == ["t3"]

    def test_fan_out_fan_in(self):
        """t1 -> (t2, t3) -> t4"""
        sched = TaskScheduler()
        t1 = _make_task("t1")
        t2 = _make_task("t2", deps=["t1"])
        t3 = _make_task("t3", deps=["t1"])
        t4 = _make_task("t4", deps=["t2", "t3"])
        batches, done = sched.topological_sort([t1, t2, t3, t4])
        assert len(batches) == 3
        assert [t.id for t in batches[0]] == ["t1"]
        batch2_ids = sorted([t.id for t in batches[1]])
        assert batch2_ids == ["t2", "t3"]
        assert [t.id for t in batches[2]] == ["t4"]

    def test_cycle_detection(self):
        sched = TaskScheduler()
        t1 = _make_task("t1", deps=["t2"])
        t2 = _make_task("t2", deps=["t1"])
        batches, done = sched.topological_sort([t1, t2])
        assert batches == []
        assert done == []

    def test_self_cycle(self):
        sched = TaskScheduler()
        t1 = _make_task("t1", deps=["t1"])
        batches, done = sched.topological_sort([t1])
        assert batches == []

    def test_external_deps_ignored(self):
        """依赖不在待办列表里的，视为已完成"""
        sched = TaskScheduler()
        t1 = _make_task("t1", deps=["external-task"])
        batches, done = sched.topological_sort([t1])
        assert len(batches) == 1
        assert batches[0][0].id == "t1"


class TestPrioritySorting:
    """同批次内优先级排序"""

    def test_same_batch_sorted_by_priority(self):
        sched = TaskScheduler()
        t1 = _make_task("t-low", priority="low")
        t2 = _make_task("t-urgent", priority="urgent")
        t3 = _make_task("t-medium", priority="medium")
        t4 = _make_task("t-high", priority="high")
        batches, _ = sched.topological_sort([t1, t2, t3, t4])
        assert len(batches) == 1
        ids = [t.id for t in batches[0]]
        assert ids == ["t-urgent", "t-high", "t-medium", "t-low"]


class TestSchedulerRun:
    """调度器运行（dry-run 和 mock spawn）"""

    def test_dry_run_no_pending(self, tmp_workspace):
        sched = TaskScheduler()
        stats = sched.run(lambda t: True, dry_run=True)
        assert stats["total_pending"] == 0
        assert stats["status"] == "no pending tasks"

    def test_dry_run_with_pending_tasks(self, tmp_workspace):
        """创建几个 pending 任务文件，测试 dry-run"""
        from task_init import TaskInitializer
        ti = TaskInitializer()

        ti.create_task(
            task_id="task-20260910-a", name="任务A", owner="test",
            scope_project="p", scope_component="c", scope_version="v1",
            goals=[{"id": "g1", "description": "a", "status": "pending"}],
            initial_status="pending",
        )
        ti.create_task(
            task_id="task-20260910-b", name="任务B", owner="test",
            scope_project="p", scope_component="c", scope_version="v1",
            goals=[{"id": "g1", "description": "b", "status": "pending"}],
            initial_status="pending",
        )

        sched = TaskScheduler()
        stats = sched.run(lambda t: True, dry_run=True)
        assert stats["total_pending"] == 2
        assert stats["started"] == 2
        assert stats["batches"] == 1
        assert stats["status"] == "completed"

    def test_spawn_callback_called(self, tmp_workspace):
        """验证 spawn 回调被调用且任务状态被更新"""
        from task_init import TaskInitializer
        ti = TaskInitializer()
        ti.create_task(
            task_id="task-20260910-spawn", name="Spawn 测试", owner="test",
            scope_project="p", scope_component="c", scope_version="v1",
            goals=[{"id": "g1", "description": "x", "status": "pending"}],
            initial_status="pending",
        )

        called = []
        def fake_spawn(task):
            called.append(task.id)
            return True

        sched = TaskScheduler()
        # interval=0 加速测试
        stats = sched.run(fake_spawn, interval_sec=0, dry_run=False)
        assert stats["started"] == 1
        assert called == ["task-20260910-spawn"]

        # 验证任务状态变成 in-progress
        from utils import load_task_yaml
        data, _ = load_task_yaml("task-20260910-spawn")
        assert data["status"] == "in-progress"

    def test_spawn_failure(self, tmp_workspace):
        """spawn 失败时任务不标记为 in-progress"""
        from task_init import TaskInitializer
        ti = TaskInitializer()
        ti.create_task(
            task_id="task-20260910-fail", name="失败测试", owner="test",
            scope_project="p", scope_component="c", scope_version="v1",
            goals=[{"id": "g1", "description": "x", "status": "pending"}],
            initial_status="pending",
        )

        sched = TaskScheduler()
        stats = sched.run(lambda t: False, interval_sec=0)
        assert stats["started"] == 0
        assert "task-20260910-fail" in stats["failed"]
