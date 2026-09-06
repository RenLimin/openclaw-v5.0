"""
DMS-Framework issue 模块单元测试
覆盖：CRUD、状态机完整生命周期、重开回路、非法迁移、终态保护、列表过滤、
      删除、分诊视图、项目取消事件联动
"""
import pytest
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database
from core.migrations import migrate
from core.saas import TenantContext
from core.module import ModuleRegistry
from core.state_machine import StateMachineEngine
from core.event_bus import EventBus

from modules.project import manifest as project_manifest
from modules.project import ProjectModule
from modules.issue import manifest as issue_manifest
from modules.issue import IssueModule


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """临时 SQLite 数据库，执行迁移后提供给测试。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f"sqlite:///{f.name}")
        migrate(db.connect())
        yield db
    os.unlink(f.name)


@pytest.fixture
def registry(db):
    """注册 project + issue 模块，注入状态机引擎与事件总线。

    注：_state_machine_engine 和 _event_bus 必须在 register 之前挂到 registry 上，
    这样模块 initialize 时才能正确注册状态机、on_ready 时才能订阅事件。
    """
    reg = ModuleRegistry()
    reg._state_machine_engine = StateMachineEngine()
    reg._event_bus = EventBus()
    reg.register(project_manifest, ProjectModule)
    reg.register(issue_manifest, IssueModule)
    reg.initialize_all(db, {})
    return reg


@pytest.fixture
def project(registry):
    """便捷 fixture：创建一个测试项目。"""
    TenantContext.set("test")
    pm = registry.get("project")
    proj = pm.create_project(name="issue测试项目", description="用于issue模块测试的项目")
    yield proj
    TenantContext.reset()


# ---------------------------------------------------------------------------
# 1. 创建问题
# ---------------------------------------------------------------------------

class TestCreateIssue:
    def test_create_issue_default_status_open(self, registry, project):
        """创建问题：默认状态为 open，类型为 issue，可持久化回读。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="测试问题", description="问题描述")

        # 基本字段校验
        assert issue.id is not None
        assert issue.title == "测试问题"
        assert issue.description == "问题描述"
        assert issue.status == "open"
        assert issue.type == "issue"
        assert issue.project_id == project.id
        assert issue.tenant_id == "test"
        assert issue.priority == "medium"
        assert issue.assignee_id == ""

        # 持久化回读
        got = im.get_issue(issue.id)
        assert got is not None
        assert got.id == issue.id
        assert got.title == "测试问题"
        assert got.status == "open"
        assert got.type == "issue"
        TenantContext.reset()

    def test_create_issue_with_priority_and_assignee(self, registry, project):
        """创建问题：指定 priority 和 assignee_id 能正确持久化。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(
            project_id=project.id,
            title="高优问题",
            priority="high",
            assignee_id="user_001",
        )

        assert issue.priority == "high"
        assert issue.assignee_id == "user_001"

        # 回读确认
        got = im.get_issue(issue.id)
        assert got.priority == "high"
        assert got.assignee_id == "user_001"
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 2. metadata 读写持久化
# ---------------------------------------------------------------------------

class TestIssueMetadata:
    def test_severity_category_root_cause_persistence(self, registry, project):
        """metadata 字段（severity/category/root_cause）写入后可持久化回读。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="元数据测试问题")
        # 通过属性写入 metadata
        issue.severity = "critical"
        issue.category = "bug"
        issue.root_cause = "空指针异常"
        im._repo.update(issue)

        # 回读确认
        got = im.get_issue(issue.id)
        assert got.severity == "critical"
        assert got.category == "bug"
        assert got.root_cause == "空指针异常"
        TenantContext.reset()

    def test_default_metadata_values(self, registry, project):
        """新建问题的 metadata 默认值：severity=medium, category/root_cause 为空。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="默认元数据问题")
        assert issue.severity == "medium"
        assert issue.category == ""
        assert issue.root_cause == ""
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 3. 完整生命周期
# ---------------------------------------------------------------------------

class TestTransitionFullLifecycle:
    def test_open_to_resolved_full_path(self, registry, project):
        """完整生命周期：open → investigating → resolving → resolved。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="生命周期测试")

        # open → investigating
        r = im.transition_issue(issue.id, "investigate")
        assert r.status == "investigating"
        assert im.get_issue(issue.id).status == "investigating"

        # investigating → resolving
        r = im.transition_issue(issue.id, "resolve")
        assert r.status == "resolving"
        assert im.get_issue(issue.id).status == "resolving"

        # resolving → resolved（终态）
        r = im.transition_issue(issue.id, "verify")
        assert r.status == "resolved"
        assert im.get_issue(issue.id).status == "resolved"
        TenantContext.reset()

    def test_close_from_open(self, registry, project):
        """从 open 直接关闭：open → closed。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="直接关闭测试")
        r = im.transition_issue(issue.id, "close")
        assert r.status == "closed"
        assert im.get_issue(issue.id).status == "closed"
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 4. resolved 重开回路
# ---------------------------------------------------------------------------

class TestTransitionReopen:
    def test_resolved_reopen_resolved_again(self, registry, project):
        """重开回路：resolved → reopened → resolving → resolved。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="重开测试")
        # 先走到 resolved
        im.transition_issue(issue.id, "investigate")
        im.transition_issue(issue.id, "resolve")
        im.transition_issue(issue.id, "verify")
        assert im.get_issue(issue.id).status == "resolved"

        # 重开
        r = im.transition_issue(issue.id, "reopen")
        assert r.status == "reopened"

        # 重新解决
        r = im.transition_issue(issue.id, "resolve_again")
        assert r.status == "resolving"

        r = im.transition_issue(issue.id, "verify")
        assert r.status == "resolved"
        TenantContext.reset()

    def test_reopened_close_to_closed(self, registry, project):
        """reopened 状态可关闭到 closed。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="重开后关闭")
        im.transition_issue(issue.id, "investigate")
        im.transition_issue(issue.id, "resolve")
        im.transition_issue(issue.id, "verify")  # → resolved
        im.transition_issue(issue.id, "reopen")   # → reopened

        r = im.transition_issue(issue.id, "close_reopened")
        assert r.status == "closed"
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 5. investigating 状态直接重开（无此路径，验证非法）
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    def test_cannot_verify_from_open(self, registry, project):
        """非法迁移：open 状态下不能直接 verify。"""
        TenantContext.set("test")
        im = registry.get("issue")
        issue = im.create_issue(project_id=project.id, title="非法迁移测试")

        with pytest.raises(ValueError, match="Cannot fire"):
            im.transition_issue(issue.id, "verify")
        TenantContext.reset()

    def test_nonexistent_transition_name(self, registry, project):
        """非法迁移：不存在的迁移名称。"""
        TenantContext.set("test")
        im = registry.get("issue")
        issue = im.create_issue(project_id=project.id, title="不存在的迁移")

        with pytest.raises(ValueError, match="Unknown transition"):
            im.transition_issue(issue.id, "do_something_impossible")
        TenantContext.reset()

    def test_nonexistent_issue_id(self, registry, project):
        """非法迁移：不存在的 issue ID。"""
        TenantContext.set("test")
        im = registry.get("issue")

        with pytest.raises(ValueError, match="问题不存在"):
            im.transition_issue("non-existent-id", "investigate")
        TenantContext.reset()

    def test_cannot_reopen_from_investigating(self, registry, project):
        """非法迁移：investigating 状态下不能直接 reopen（需先到 resolved）。"""
        TenantContext.set("test")
        im = registry.get("issue")
        issue = im.create_issue(project_id=project.id, title="investigating不能重开")
        im.transition_issue(issue.id, "investigate")

        with pytest.raises(ValueError, match="Cannot fire"):
            im.transition_issue(issue.id, "reopen")
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 6. 终态保护
# ---------------------------------------------------------------------------

class TestTerminalState:
    def test_resolved_terminal_no_investigate(self, registry, project):
        """终态保护：resolved 状态下不能再 investigate。"""
        TenantContext.set("test")
        im = registry.get("issue")
        issue = im.create_issue(project_id=project.id, title="终态测试")
        im.transition_issue(issue.id, "investigate")
        im.transition_issue(issue.id, "resolve")
        im.transition_issue(issue.id, "verify")
        assert im.get_issue(issue.id).status == "resolved"

        # resolved 不能直接回到 investigating
        with pytest.raises(ValueError):
            im.transition_issue(issue.id, "investigate")
        TenantContext.reset()

    def test_closed_terminal_no_transition(self, registry, project):
        """终态保护：closed 终态不能再迁移。"""
        TenantContext.set("test")
        im = registry.get("issue")
        issue = im.create_issue(project_id=project.id, title="closed终态测试")
        im.transition_issue(issue.id, "close")
        assert im.get_issue(issue.id).status == "closed"

        # closed 是终态，尝试各种迁移都应失败
        with pytest.raises(ValueError):
            im.transition_issue(issue.id, "investigate")
        with pytest.raises(ValueError):
            im.transition_issue(issue.id, "reopen")
        with pytest.raises(ValueError):
            im.transition_issue(issue.id, "close")
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 7. 列表过滤与项目隔离
# ---------------------------------------------------------------------------

class TestListIssues:
    def test_list_by_status_filter(self, registry, project):
        """列表过滤：按 status 过滤问题。"""
        TenantContext.set("test")
        im = registry.get("issue")

        # 创建 3 个 open、2 个 investigating
        for i in range(3):
            im.create_issue(project_id=project.id, title=f"open问题{i}")
        for i in range(2):
            issue = im.create_issue(project_id=project.id, title=f"调查中问题{i}")
            im.transition_issue(issue.id, "investigate")

        all_issues = im.list_issues(project_id=project.id)
        assert len(all_issues) == 5

        open_issues = im.list_issues(project_id=project.id, status="open")
        assert len(open_issues) == 3

        inv_issues = im.list_issues(project_id=project.id, status="investigating")
        assert len(inv_issues) == 2
        TenantContext.reset()

    def test_list_isolated_by_project(self, registry):
        """项目隔离：不同项目的问题互不干扰。"""
        TenantContext.set("test")
        pm = registry.get("project")
        im = registry.get("issue")

        proj_a = pm.create_project(name="项目A")
        proj_b = pm.create_project(name="项目B")

        im.create_issue(project_id=proj_a.id, title="A的问题1")
        im.create_issue(project_id=proj_a.id, title="A的问题2")
        im.create_issue(project_id=proj_b.id, title="B的问题1")

        list_a = im.list_issues(project_id=proj_a.id)
        list_b = im.list_issues(project_id=proj_b.id)

        assert len(list_a) == 2
        assert len(list_b) == 1
        assert all(it.project_id == proj_a.id for it in list_a)
        assert all(it.project_id == proj_b.id for it in list_b)
        TenantContext.reset()

    def test_tenant_isolation(self, registry, project):
        """租户隔离：不同租户的问题互不可见。"""
        TenantContext.set("tenant_a")
        im = registry.get("issue")
        issue_a = im.create_issue(project_id=project.id, title="租户A的问题")

        TenantContext.set("tenant_b")
        # 租户 B 看不到租户 A 的问题
        got = im.get_issue(issue_a.id)
        assert got is None

        TenantContext.reset()


# ---------------------------------------------------------------------------
# 8. 删除问题
# ---------------------------------------------------------------------------

class TestDeleteIssue:
    def test_delete_existing_issue(self, registry, project):
        """删除存在的问题返回 True，删除后查询不到。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="待删除问题")
        assert im.get_issue(issue.id) is not None

        result = im.delete_issue(issue.id)
        assert result is True
        assert im.get_issue(issue.id) is None
        TenantContext.reset()

    def test_delete_nonexistent_returns_false(self, registry, project):
        """删除不存在的问题返回 False。"""
        TenantContext.set("test")
        im = registry.get("issue")

        result = im.delete_issue("non-existent-issue-id")
        assert result is False
        TenantContext.reset()

    def test_double_delete_returns_false(self, registry, project):
        """重复删除：第二次删除返回 False。"""
        TenantContext.set("test")
        im = registry.get("issue")

        issue = im.create_issue(project_id=project.id, title="重复删除测试")
        assert im.delete_issue(issue.id) is True
        assert im.delete_issue(issue.id) is False
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 9. 分诊视图
# ---------------------------------------------------------------------------

class TestTriage:
    def test_triage_returns_dict_grouped_by_severity(self, registry, project):
        """分诊视图：返回 dict，按 severity 分组。"""
        TenantContext.set("test")
        im = registry.get("issue")

        # 创建不同 severity 的问题
        for sev in ["critical", "high", "medium", "low"]:
            issue = im.create_issue(project_id=project.id, title=f"{sev}问题")
            issue.severity = sev
            im._repo.update(issue)

        triage = im.triage(project_id=project.id)
        assert isinstance(triage, dict)
        assert "critical" in triage
        assert "high" in triage
        assert "medium" in triage
        assert "low" in triage
        assert len(triage["critical"]) == 1
        assert len(triage["high"]) == 1
        assert len(triage["medium"]) == 1
        assert len(triage["low"]) == 1
        assert triage["critical"][0].severity == "critical"
        TenantContext.reset()

    def test_triage_empty_project(self, registry, project):
        """分诊视图：空项目返回空 dict。"""
        TenantContext.set("test")
        im = registry.get("issue")

        triage = im.triage(project_id=project.id)
        assert isinstance(triage, dict)
        assert len(triage) == 0
        TenantContext.reset()

    def test_triage_only_includes_issues_of_project(self, registry):
        """分诊视图：只包含指定项目的问题。"""
        TenantContext.set("test")
        pm = registry.get("project")
        im = registry.get("issue")

        proj_a = pm.create_project(name="分诊项目A")
        proj_b = pm.create_project(name="分诊项目B")

        issue = im.create_issue(project_id=proj_a.id, title="A的critical问题")
        issue.severity = "critical"
        im._repo.update(issue)

        im.create_issue(project_id=proj_b.id, title="B的问题")

        triage_a = im.triage(project_id=proj_a.id)
        assert len(triage_a) == 1
        assert len(triage_a["critical"]) == 1
        TenantContext.reset()


# ---------------------------------------------------------------------------
# 10. 项目取消事件联动
# ---------------------------------------------------------------------------

class TestProjectCancelledIntegration:
    def test_project_cancel_closes_open_and_reopened_issues(self, registry):
        """项目取消事件联动：open / reopened 状态的 issue 自动关闭。

        注：当前实现中 _on_project_cancelled 通过 close / close_reopened 迁移
        关闭问题，仅支持从 open 和 reopened 状态触发。investigating / resolving
        状态无 close 迁移，会被静默跳过（保留原状态）。
        """
        TenantContext.set("test")
        pm = registry.get("project")
        im = registry.get("issue")

        proj = pm.create_project(name="取消联动项目")

        # 创建不同状态的问题
        issue_open = im.create_issue(project_id=proj.id, title="open问题")

        issue_reopened = im.create_issue(project_id=proj.id, title="reopened问题")
        im.transition_issue(issue_reopened.id, "investigate")
        im.transition_issue(issue_reopened.id, "resolve")
        im.transition_issue(issue_reopened.id, "verify")
        im.transition_issue(issue_reopened.id, "reopen")

        issue_resolved = im.create_issue(project_id=proj.id, title="resolved问题")
        im.transition_issue(issue_resolved.id, "investigate")
        im.transition_issue(issue_resolved.id, "resolve")
        im.transition_issue(issue_resolved.id, "verify")

        issue_closed = im.create_issue(project_id=proj.id, title="closed问题")
        im.transition_issue(issue_closed.id, "close")

        # 取消项目 → 触发 project.cancelled 事件
        pm.transition_project(proj.id, "cancel")

        # open → closed（有 close 迁移）
        assert im.get_issue(issue_open.id).status == "closed"
        # reopened → closed（有 close_reopened 迁移）
        assert im.get_issue(issue_reopened.id).status == "closed"
        # resolved 保持不变（已是终态）
        assert im.get_issue(issue_resolved.id).status == "resolved"
        # closed 保持不变
        assert im.get_issue(issue_closed.id).status == "closed"
        TenantContext.reset()

    def test_project_cancel_reopened_issue_closes(self, registry):
        """项目取消：reopened 状态的 issue 也会被关闭。"""
        TenantContext.set("test")
        pm = registry.get("project")
        im = registry.get("issue")

        proj = pm.create_project(name="reopened联动项目")
        issue = im.create_issue(project_id=proj.id, title="reopened问题")
        im.transition_issue(issue.id, "investigate")
        im.transition_issue(issue.id, "resolve")
        im.transition_issue(issue.id, "verify")   # → resolved
        im.transition_issue(issue.id, "reopen")    # → reopened
        assert im.get_issue(issue.id).status == "reopened"

        pm.transition_project(proj.id, "cancel")
        assert im.get_issue(issue.id).status == "closed"
        TenantContext.reset()

    def test_project_cancel_no_effect_on_other_project(self, registry):
        """项目取消：只影响被取消项目下的 issue，不影响其他项目。"""
        TenantContext.set("test")
        pm = registry.get("project")
        im = registry.get("issue")

        proj_a = pm.create_project(name="项目A（将被取消）")
        proj_b = pm.create_project(name="项目B（保留）")

        issue_a = im.create_issue(project_id=proj_a.id, title="A的问题")
        issue_b = im.create_issue(project_id=proj_b.id, title="B的问题")

        pm.transition_project(proj_a.id, "cancel")

        assert im.get_issue(issue_a.id).status == "closed"
        assert im.get_issue(issue_b.id).status == "open"
        TenantContext.reset()
