"""
集成测试 — 完整流程：创建任务 → 调度 → 执行 → 状态更新 → 事件记录
"""
import pytest


def test_full_task_lifecycle(tmp_workspace):
    """完整生命周期测试"""
    from service import SessionIsolationService

    svc = SessionIsolationService()

    # 1. 创建任务
    ok, msg = svc.create_task(
        task_id="task-20260910-integ",
        name="集成测试任务",
        owner="test-agent",
        scope_project="test-proj",
        scope_component="integ",
        scope_version="v1.0",
        goals=[
            {"id": "g1", "description": "第一步", "status": "pending"},
            {"id": "g2", "description": "第二步", "status": "pending"},
        ],
        priority="high",
    )
    assert ok is True, f"创建任务失败: {msg}"

    # 2. 验证事件自动记录
    events, err = svc.get_task_events("task-20260910-integ")
    assert err == ""
    assert len(events) == 1
    assert events[0]["type"] == "task.created"

    # 3. 手动更新目标状态
    ok, _ = svc.update_task_goal_status("task-20260910-integ", "g1", "done")
    assert ok is True

    # 4. 验证目标更新事件
    events, _ = svc.get_task_events("task-20260910-integ")
    assert len(events) == 2
    assert events[-1]["type"] == "goal.updated"
    assert events[-1]["goal_id"] == "g1"

    # 5. 写入共享状态
    ok, _ = svc.write_shared_state(
        "task/task-20260910-integ",
        "progress",
        {"completed": 1, "total": 2},
        reducer="last-write-wins",
    )
    assert ok is True

    # 6. 读取共享状态
    state, err = svc.read_shared_state(
        "task/task-20260910-integ", "progress"
    )
    assert err == ""
    assert state["completed"] == 1
    assert state["total"] == 2

    # 7. 记录自定义事件
    ok, _ = svc.log_task_event(
        "task-20260910-integ",
        "milestone.reached",
        {"milestone": "phase1", "duration_sec": 42},
    )
    assert ok is True

    # 8. 最终事件数验证
    events, _ = svc.get_task_events("task-20260910-integ")
    assert len(events) == 3
    assert events[-1]["type"] == "milestone.reached"
    assert events[-1]["milestone"] == "phase1"


def test_scheduler_with_dependencies(tmp_workspace):
    """带依赖的调度集成测试"""
    from task_init import TaskInitializer
    from utils import load_task_yaml, save_task_yaml
    from scheduler import TaskScheduler

    ti = TaskInitializer()

    # 创建三个任务: A → B → C
    ti.create_task(
        task_id="task-20260910-dep-a", name="任务A", owner="test",
        scope_project="p", scope_component="c", scope_version="v1",
        goals=[{"id": "g1", "description": "a", "status": "pending"}],
        initial_status="pending",
    )
    ti.create_task(
        task_id="task-20260910-dep-b", name="任务B", owner="test",
        scope_project="p", scope_component="c", scope_version="v1",
        goals=[{"id": "g1", "description": "b", "status": "pending"}],
        initial_status="pending",
    )
    ti.create_task(
        task_id="task-20260910-dep-c", name="任务C", owner="test",
        scope_project="p", scope_component="c", scope_version="v1",
        goals=[{"id": "g1", "description": "c", "status": "pending"}],
        initial_status="pending",
    )

    # 设置依赖关系: B 依赖 A, C 依赖 B
    def set_deps(task_id, deps):
        data, _ = load_task_yaml(task_id)
        data["dependencies"] = deps
        data["status"] = "pending"  # 重置为 pending
        save_task_yaml(task_id, data)

    set_deps("task-20260910-dep-b", ["task-20260910-dep-a"])
    set_deps("task-20260910-dep-c", ["task-20260910-dep-b"])

    # 调度 (dry-run)
    sched = TaskScheduler()
    stats = sched.run(lambda t: True, dry_run=True)

    assert stats["total_pending"] == 3
    assert stats["batches"] == 3
    assert stats["started"] == 3
    assert stats["status"] == "completed"


def test_service_layer_readme_api(tmp_workspace):
    """验证 Service 层所有公开 API 可用"""
    from service import SessionIsolationService

    svc = SessionIsolationService()

    # Task
    ok, _ = svc.create_task(
        task_id="task-20260910-api", name="API 测试", owner="test",
        scope_project="p", scope_component="c", scope_version="v1",
        goals=[{"id": "g1", "description": "x", "status": "pending"}],
        initial_status="pending",
    )
    assert ok is True

    # State
    svc.write_shared_state("test/api", "key1", "value1")
    data, _ = svc.read_shared_state("test/api", "key1")
    assert data == "value1"

    keys, _ = svc.list_shared_states("test/api")
    assert "key1" in keys

    svc.delete_shared_state("test/api", "key1")
    data, _ = svc.read_shared_state("test/api", "key1")
    assert data is None

    # Event
    svc.log_task_event("task-20260910-api", "custom.event", {"foo": "bar"})
    events, _ = svc.get_task_events("task-20260910-api")
    assert len(events) == 2  # task.created + custom.event
    assert events[-1]["foo"] == "bar"

    # Scheduler
    sched = svc.get_scheduler()
    assert sched is not None
    stats = svc.run_scheduler(lambda t: True, dry_run=True)
    assert stats["total_pending"] == 1
