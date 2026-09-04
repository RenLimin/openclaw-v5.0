"""
DMS-Framework task 模块单元测试
覆盖：CRUD / 状态机主流程 / 阻塞往返 / 取消 / 非法迁移 / 终态保护 / 列表过滤 / 删除 / 看板 / 项目取消联动
"""
import pytest
import tempfile
import os
import sys
sys.path.insert(0, '.')

from core.database import Database
from core.migrations import migrate
from core.saas import TenantContext
from core.module import ModuleRegistry
from core.state_machine import StateMachineEngine
from core.event_bus import EventBus

from modules.project import manifest as project_manifest
from modules.project import ProjectModule
from modules.task import manifest as task_manifest
from modules.task import TaskModule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """临时 SQLite 数据库 + 迁移。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f"sqlite:///{f.name}")
        migrate(db.connect())
        yield db
    os.unlink(f.name)


@pytest.fixture
def registry(db):
    """模块注册中心：注入状态机引擎 + 事件总线，注册 project + task 模块。"""
    reg = ModuleRegistry()
    reg._state_machine_engine = StateMachineEngine()
    reg._event_bus = EventBus()
    reg.register(project_manifest, ProjectModule)
    reg.register(task_manifest, TaskModule)
    reg.initialize_all(db, {})
    return reg


@pytest.fixture
def _tenant():
    """每个测试用例的租户隔离包装器。"""
    TenantContext.set("test")
    yield
    TenantContext.reset()


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _make_project(registry, name="测试项目"):
    """快速创建一个项目（辅助函数）。"""
    pm = registry.get("project")
    return pm.create_project(name=name)


# ===========================================================================
# 1. 创建任务
# ===========================================================================

class TestCreateTask:
    def test_create_task_default_status_backlog(self, registry, _tenant):
        """创建任务：默认状态为 backlog，字段正确，持久化后可回读。"""
        tm = registry.get("task")
        proj = _make_project(registry)

        task = tm.create_task(project_id=proj.id, title="实现登录功能")
        assert task.id is not None
        assert task.title == "实现登录功能"
        assert task.description == ""
        assert task.status == "backlog"
        assert task.priority == "medium"
        assert task.assignee_id == ""
        assert task.type == "task"
        assert task.tenant_id == "test"
        assert task.project_id == proj.id

        # 持久化回读验证
        got = tm.get_task(task.id)
        assert got is not None
        assert got.title == "实现登录功能"
        assert got.status == "backlog"
        assert got.type == "task"

    def test_create_task_with_description_and_priority(self, registry, _tenant):
        """创建任务：传入 description / priority / assignee_id 全部正确持久化。"""
        tm = registry.get("task")
        proj = _make_project(registry)

        task = tm.create_task(
            project_id=proj.id,
            title="高优任务",
            description="紧急修复线上 bug",
            priority="high",
            assignee_id="dev_001",
        )
        got = tm.get_task(task.id)
        assert got.description == "紧急修复线上 bug"
        assert got.priority == "high"
        assert got.assignee_id == "dev_001"


# ===========================================================================
# 2. 元数据读写持久化（priority / assignee_id）
# ===========================================================================

class TestTaskMetadata:
    def test_priority_and_assignee_persist_after_update(self, registry, _tenant):
        """priority / assignee_id 修改后通过 repo.update 持久化，重新读取仍然有效。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="元数据测试")

        # 先 get 刷新对象，再修改字段并 update
        fresh = tm.get_task(task.id)
        fresh.priority = "critical"
        fresh.assignee_id = "pm_007"
        tm._repo.update(fresh)

        got = tm.get_task(task.id)
        assert got.priority == "critical"
        assert got.assignee_id == "pm_007"

    def test_description_update_persists(self, registry, _tenant):
        """description 修改后持久化。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="描述测试", description="初始描述")

        fresh = tm.get_task(task.id)
        fresh.description = "更新后的描述"
        tm._repo.update(fresh)

        got = tm.get_task(task.id)
        assert got.description == "更新后的描述"


# ===========================================================================
# 3. 主流程：backlog → todo → in_progress → done
# ===========================================================================

class TestTransitionMainFlow:
    def test_pull_start_complete_full_flow(self, registry, _tenant):
        """完整主流程：backlog --pull--> todo --start--> in_progress --complete--> done。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="主流程任务")

        # backlog → todo
        t1 = tm.transition_task(task.id, "pull")
        assert t1.status == "todo"
        assert tm.get_task(task.id).status == "todo"

        # todo → in_progress
        t2 = tm.transition_task(task.id, "start")
        assert t2.status == "in_progress"
        assert tm.get_task(task.id).status == "in_progress"

        # in_progress → done
        t3 = tm.transition_task(task.id, "complete")
        assert t3.status == "done"
        assert tm.get_task(task.id).status == "done"

    def test_transition_returns_new_object(self, registry, _tenant):
        """transition 返回的是状态更新后的新对象。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="返回值测试")

        result = tm.transition_task(task.id, "pull")
        # 返回对象状态已更新
        assert result.status == "todo"
        # 原对象（本地）状态未变（验证返回新对象语义）
        assert task.status == "backlog"


# ===========================================================================
# 4. 阻塞往返：in_progress → blocked → in_progress
# ===========================================================================

class TestTransitionBlockUnblock:
    def test_block_and_unblock_roundtrip(self, registry, _tenant):
        """阻塞流程：in_progress --block--> blocked --unblock--> in_progress。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="阻塞测试")

        # 先拉到进行中
        tm.transition_task(task.id, "pull")
        tm.transition_task(task.id, "start")
        assert tm.get_task(task.id).status == "in_progress"

        # 阻塞
        blocked = tm.transition_task(task.id, "block")
        assert blocked.status == "blocked"
        assert tm.get_task(task.id).status == "blocked"

        # 解除阻塞
        unblocked = tm.transition_task(task.id, "unblock")
        assert unblocked.status == "in_progress"
        assert tm.get_task(task.id).status == "in_progress"

    def test_multiple_block_unblock_cycles(self, registry, _tenant):
        """多次阻塞 / 解除阻塞循环正常工作。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="循环阻塞")

        tm.transition_task(task.id, "pull")
        tm.transition_task(task.id, "start")

        for i in range(3):
            tm.transition_task(task.id, "block")
            assert tm.get_task(task.id).status == "blocked"
            tm.transition_task(task.id, "unblock")
            assert tm.get_task(task.id).status == "in_progress"


# ===========================================================================
# 5. 取消：todo → cancelled, blocked → cancelled
# ===========================================================================

class TestTransitionCancel:
    def test_cancel_from_todo(self, registry, _tenant):
        """从 todo 状态取消：cancel → cancelled。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="取消测试-todo")

        tm.transition_task(task.id, "pull")  # backlog → todo
        cancelled = tm.transition_task(task.id, "cancel")
        assert cancelled.status == "cancelled"
        assert tm.get_task(task.id).status == "cancelled"

    def test_cancel_from_blocked(self, registry, _tenant):
        """从 blocked 状态取消：cancel → cancelled（内部映射为 cancel_blocked）。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="取消测试-blocked")

        tm.transition_task(task.id, "pull")
        tm.transition_task(task.id, "start")
        tm.transition_task(task.id, "block")
        assert tm.get_task(task.id).status == "blocked"

        cancelled = tm.transition_task(task.id, "cancel")
        assert cancelled.status == "cancelled"
        assert tm.get_task(task.id).status == "cancelled"


# ===========================================================================
# 6. 非法迁移
# ===========================================================================

class TestInvalidTransition:
    def test_backlog_cannot_direct_complete(self, registry, _tenant):
        """backlog 状态直接 complete 是非法迁移，应抛出异常。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="非法迁移-直达完成")

        with pytest.raises(Exception):
            tm.transition_task(task.id, "complete")

        # 状态未改变
        assert tm.get_task(task.id).status == "backlog"

    def test_nonexistent_transition_name(self, registry, _tenant):
        """不存在的迁移名应抛出异常。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="非法迁移-不存在的名")

        with pytest.raises(Exception):
            tm.transition_task(task.id, "fly_to_the_moon")

    def test_nonexistent_task_id(self, registry, _tenant):
        """对不存在的 task_id 触发迁移应抛出 ValueError。"""
        tm = registry.get("task")
        proj = _make_project(registry)  # 确保数据库已建立

        with pytest.raises(ValueError, match="任务不存在"):
            tm.transition_task("non-existent-id-12345", "pull")

    def test_block_from_todo_invalid(self, registry, _tenant):
        """todo 状态不能直接 block（必须先 start 到 in_progress）。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="非法迁移-todo直接block")
        tm.transition_task(task.id, "pull")  # → todo

        with pytest.raises(Exception):
            tm.transition_task(task.id, "block")


# ===========================================================================
# 7. 终态不能再迁移
# ===========================================================================

class TestTerminalState:
    def test_done_is_terminal_no_more_transition(self, registry, _tenant):
        """done 是终态，再触发任何迁移都应失败。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="终态测试-done")

        tm.transition_task(task.id, "pull")
        tm.transition_task(task.id, "start")
        tm.transition_task(task.id, "complete")
        assert tm.get_task(task.id).status == "done"

        # 终态下尝试各种迁移均失败
        for tr in ["pull", "start", "block", "unblock", "complete", "cancel"]:
            with pytest.raises(Exception):
                tm.transition_task(task.id, tr)

        # 状态保持 done
        assert tm.get_task(task.id).status == "done"

    def test_cancelled_is_terminal_no_more_transition(self, registry, _tenant):
        """cancelled 是终态，再触发任何迁移都应失败。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="终态测试-cancelled")

        tm.transition_task(task.id, "pull")
        tm.transition_task(task.id, "cancel")
        assert tm.get_task(task.id).status == "cancelled"

        for tr in ["pull", "start", "block", "unblock", "complete", "cancel"]:
            with pytest.raises(Exception):
                tm.transition_task(task.id, tr)

        assert tm.get_task(task.id).status == "cancelled"


# ===========================================================================
# 8. 列表过滤 + 项目隔离
# ===========================================================================

class TestListTasks:
    def test_list_by_status_filter(self, registry, _tenant):
        """按 status 参数过滤任务列表。"""
        tm = registry.get("task")
        proj = _make_project(registry)

        t1 = tm.create_task(project_id=proj.id, title="任务A")  # backlog
        t2 = tm.create_task(project_id=proj.id, title="任务B")  # backlog
        t3 = tm.create_task(project_id=proj.id, title="任务C")  # backlog

        # 把 t1 拉到 todo
        tm.transition_task(t1.id, "pull")
        # 把 t2 拉到 in_progress
        tm.transition_task(t2.id, "pull")
        tm.transition_task(t2.id, "start")

        # 按状态过滤
        backlogs = tm.list_tasks(project_id=proj.id, status="backlog")
        assert len(backlogs) == 1
        assert backlogs[0].id == t3.id

        todos = tm.list_tasks(project_id=proj.id, status="todo")
        assert len(todos) == 1
        assert todos[0].id == t1.id

        in_progs = tm.list_tasks(project_id=proj.id, status="in_progress")
        assert len(in_progs) == 1
        assert in_progs[0].id == t2.id

    def test_list_all_without_filter(self, registry, _tenant):
        """不传 status 时返回项目下所有任务。"""
        tm = registry.get("task")
        proj = _make_project(registry)

        for i in range(5):
            tm.create_task(project_id=proj.id, title=f"任务{i}")

        all_tasks = tm.list_tasks(project_id=proj.id)
        assert len(all_tasks) == 5

    def test_list_isolated_by_project(self, registry, _tenant):
        """不同项目之间的任务严格隔离。"""
        tm = registry.get("task")
        proj_a = _make_project(registry, name="项目A")
        proj_b = _make_project(registry, name="项目B")

        tm.create_task(project_id=proj_a.id, title="A-任务1")
        tm.create_task(project_id=proj_a.id, title="A-任务2")
        tm.create_task(project_id=proj_b.id, title="B-任务1")

        list_a = tm.list_tasks(project_id=proj_a.id)
        list_b = tm.list_tasks(project_id=proj_b.id)

        assert len(list_a) == 2
        assert all(t.project_id == proj_a.id for t in list_a)
        assert len(list_b) == 1
        assert list_b[0].project_id == proj_b.id

    def test_tenant_isolation(self, registry, db):
        """跨租户数据隔离：A 租户看不到 B 租户的任务。"""
        tm = registry.get("task")

        # 先创建一个公共 project
        TenantContext.set("tenant_a")
        pm = registry.get("project")
        proj_a = pm.create_project(name="A的项目")
        task_a = tm.create_task(project_id=proj_a.id, title="A的任务")

        TenantContext.set("tenant_b")
        proj_b = pm.create_project(name="B的项目")
        task_b = tm.create_task(project_id=proj_b.id, title="B的任务")

        # A 只能看到自己的
        TenantContext.set("tenant_a")
        got_a = tm.get_task(task_a.id)
        assert got_a is not None
        assert got_a.title == "A的任务"

        got_b_from_a = tm.get_task(task_b.id)
        # Repository 按租户过滤，B 的任务 A 读不到
        assert got_b_from_a is None

        list_a = tm.list_tasks(project_id=proj_a.id)
        assert len(list_a) == 1

        TenantContext.reset()


# ===========================================================================
# 9. 删除
# ===========================================================================

class TestDeleteTask:
    def test_delete_existing_task(self, registry, _tenant):
        """正常删除：返回 True，删除后 get_task 返回 None。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="待删除任务")

        assert tm.get_task(task.id) is not None
        result = tm.delete_task(task.id)
        assert result is True
        assert tm.get_task(task.id) is None

    def test_delete_nonexistent_returns_false(self, registry, _tenant):
        """删除不存在的任务：返回 False。"""
        tm = registry.get("task")
        proj = _make_project(registry)  # 确保库中有表

        result = tm.delete_task("nonexistent-task-id")
        assert result is False

    def test_double_delete_returns_false(self, registry, _tenant):
        """重复删除同一任务：第一次 True，第二次 False。"""
        tm = registry.get("task")
        proj = _make_project(registry)
        task = tm.create_task(project_id=proj.id, title="重复删除测试")

        assert tm.delete_task(task.id) is True
        assert tm.delete_task(task.id) is False


# ===========================================================================
# 10. 看板视图
# ===========================================================================

class TestBoard:
    def test_board_groups_by_status(self, registry, _tenant):
        """board 返回 dict，按状态分组。"""
        tm = registry.get("task")
        proj = _make_project(registry)

        # 创建 3 个 backlog
        for i in range(3):
            tm.create_task(project_id=proj.id, title=f"backlog-{i}")

        # 2 个 todo
        t1 = tm.create_task(project_id=proj.id, title="todo-1")
        t2 = tm.create_task(project_id=proj.id, title="todo-2")
        tm.transition_task(t1.id, "pull")
        tm.transition_task(t2.id, "pull")

        # 1 个 in_progress
        t3 = tm.create_task(project_id=proj.id, title="inprog-1")
        tm.transition_task(t3.id, "pull")
        tm.transition_task(t3.id, "start")

        board = tm.board(project_id=proj.id)

        # 返回类型是 dict
        assert isinstance(board, dict)

        # 各状态数量正确
        assert len(board.get("backlog", [])) == 3
        assert len(board.get("todo", [])) == 2
        assert len(board.get("in_progress", [])) == 1

        # 每个分组中的任务状态正确
        for t in board["backlog"]:
            assert t.status == "backlog"
        for t in board["todo"]:
            assert t.status == "todo"
        for t in board["in_progress"]:
            assert t.status == "in_progress"

    def test_board_empty_project(self, registry, _tenant):
        """空项目的 board 返回空 dict。"""
        tm = registry.get("task")
        proj = _make_project(registry, name="空项目")
        board = tm.board(project_id=proj.id)
        assert isinstance(board, dict)
        assert len(board) == 0

    def test_board_isolated_by_project(self, registry, _tenant):
        """看板只包含指定项目的任务。"""
        tm = registry.get("task")
        proj_a = _make_project(registry, name="看板项目A")
        proj_b = _make_project(registry, name="看板项目B")

        tm.create_task(project_id=proj_a.id, title="A-任务")
        tm.create_task(project_id=proj_b.id, title="B-任务")

        board_a = tm.board(project_id=proj_a.id)
        assert len(board_a["backlog"]) == 1
        assert board_a["backlog"][0].title == "A-任务"


# ===========================================================================
# 11. 项目取消联动：project.cancelled → 非终态 task 自动 cancel
# ===========================================================================

class TestProjectCancelled联动:
    def test_project_cancel_auto_cancels_non_terminal_tasks(self, registry, _tenant):
        """项目取消时，所有非终态任务自动变为 cancelled。"""
        pm = registry.get("project")
        tm = registry.get("task")
        proj = pm.create_project(name="联动测试项目")

        # 创建多个不同状态的任务
        t_backlog = tm.create_task(project_id=proj.id, title="待办池任务")

        t_todo = tm.create_task(project_id=proj.id, title="待开始任务")
        tm.transition_task(t_todo.id, "pull")

        t_inprog = tm.create_task(project_id=proj.id, title="进行中任务")
        tm.transition_task(t_inprog.id, "pull")
        tm.transition_task(t_inprog.id, "start")

        t_blocked = tm.create_task(project_id=proj.id, title="阻塞中任务")
        tm.transition_task(t_blocked.id, "pull")
        tm.transition_task(t_blocked.id, "start")
        tm.transition_task(t_blocked.id, "block")

        # 一个已经完成的任务（终态，不应被影响）
        t_done = tm.create_task(project_id=proj.id, title="已完成任务")
        tm.transition_task(t_done.id, "pull")
        tm.transition_task(t_done.id, "start")
        tm.transition_task(t_done.id, "complete")
        assert tm.get_task(t_done.id).status == "done"

        # 触发项目取消 → 发布 project.cancelled 事件 → task 模块监听联动
        pm.transition_project(proj.id, "cancel")

        # 非终态任务全部被取消
        assert tm.get_task(t_backlog.id).status == "cancelled"
        assert tm.get_task(t_todo.id).status == "cancelled"
        assert tm.get_task(t_inprog.id).status == "cancelled"
        assert tm.get_task(t_blocked.id).status == "cancelled"

        # 终态任务保持不变
        assert tm.get_task(t_done.id).status == "done"

    def test_project_cancel_no_effect_on_other_project_tasks(self, registry, _tenant):
        """项目取消只影响本项目任务，不影响其他项目。"""
        pm = registry.get("project")
        tm = registry.get("task")

        proj_a = pm.create_project(name="项目A-要取消")
        proj_b = pm.create_project(name="项目B-不取消")

        ta = tm.create_task(project_id=proj_a.id, title="A任务")
        tb = tm.create_task(project_id=proj_b.id, title="B任务")

        # 取消 A 项目
        pm.transition_project(proj_a.id, "cancel")

        assert tm.get_task(ta.id).status == "cancelled"
        # B 项目任务不受影响
        assert tm.get_task(tb.id).status == "backlog"
