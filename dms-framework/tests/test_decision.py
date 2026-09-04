"""
DMS-Framework decision 模块单元测试
覆盖 Decision 模型、状态机、CRUD、事件联动、决策日志
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
from core.event_bus import EventBus
from core.state_machine import StateMachineEngine

from modules.project import manifest as project_manifest
from modules.project import ProjectModule
from modules.decision import manifest as decision_manifest
from modules.decision import DecisionModule


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f"sqlite:///{f.name}")
        migrate(db.connect())
        yield db
    os.unlink(f.name)


@pytest.fixture
def registry(db):
    reg = ModuleRegistry()
    reg._state_machine_engine = StateMachineEngine()
    reg._event_bus = EventBus()
    reg.register(project_manifest, ProjectModule)
    reg.register(decision_manifest, DecisionModule)
    reg.initialize_all(db, {})
    return reg


class TestDecisionModule:
    def test_create(self, registry, db):
        """1. 创建决策，默认状态 proposed"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="决策项目")

        d = dm.create_decision(project_id=proj.id, title="架构选型",
                               description="选哪个数据库", priority="high",
                               assignee_id="cto-001")
        assert d.id is not None
        assert d.title == "架构选型"
        assert d.status == "proposed"
        assert d.type == "decision"
        assert d.priority == "high"
        assert d.assignee_id == "cto-001"

        got = dm.get_decision(d.id)
        assert got is not None
        assert got.title == "架构选型"
        assert got.priority == "high"
        TenantContext.reset()

    def test_metadata(self, registry, db):
        """2. metadata 字段读写持久化"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="元数据项目")

        d = dm.create_decision(project_id=proj.id, title="决策1")
        d.description = "详细决策描述"
        d.priority = "critical"
        d.assignee_id = "vp-001"
        dm._repo.update(d)

        got = dm.get_decision(d.id)
        assert got.description == "详细决策描述"
        assert got.priority == "critical"
        assert got.assignee_id == "vp-001"
        TenantContext.reset()

    def test_transition_approve(self, registry, db):
        """3. proposed → approved（终态）"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="审批测试")

        d = dm.create_decision(project_id=proj.id, title="决策A")
        assert d.status == "proposed"

        d = dm.transition_decision(d.id, "approve")
        assert d.status == "approved"
        assert dm.get_decision(d.id).status == "approved"
        TenantContext.reset()

    def test_transition_reject(self, registry, db):
        """4. proposed → rejected（终态）"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="驳回测试")

        d = dm.create_decision(project_id=proj.id, title="决策B")
        d = dm.transition_decision(d.id, "reject")
        assert d.status == "rejected"
        assert dm.get_decision(d.id).status == "rejected"
        TenantContext.reset()

    def test_transition_supersede(self, registry, db):
        """5. approved → superseded（终态）"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="替代测试")

        d = dm.create_decision(project_id=proj.id, title="旧决策")
        dm.transition_decision(d.id, "approve")  # 先批准
        d = dm.transition_decision(d.id, "supersede")  # 再取代
        assert d.status == "superseded"
        assert dm.get_decision(d.id).status == "superseded"
        TenantContext.reset()

    def test_invalid_transition(self, registry, db):
        """6. 非法迁移抛 ValueError"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="非法迁移")

        d = dm.create_decision(project_id=proj.id, title="决策C")
        # approved 后不能再 reject
        dm.transition_decision(d.id, "approve")
        with pytest.raises(ValueError):
            dm.transition_decision(d.id, "reject")
        # 不存在的迁移名
        with pytest.raises(ValueError):
            dm.transition_decision(d.id, "nonexistent")
        # 不存在的 ID
        with pytest.raises(ValueError):
            dm.transition_decision("non-exist-id", "approve")
        TenantContext.reset()

    def test_terminal_no_transition(self, registry, db):
        """7. 三种终态都不能再迁移"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="终态测试")

        d1 = dm.create_decision(project_id=proj.id, title="D1")
        dm.transition_decision(d1.id, "approve")
        with pytest.raises(ValueError):
            dm.transition_decision(d1.id, "reject")

        d2 = dm.create_decision(project_id=proj.id, title="D2")
        dm.transition_decision(d2.id, "reject")
        with pytest.raises(ValueError):
            dm.transition_decision(d2.id, "approve")

        d3 = dm.create_decision(project_id=proj.id, title="D3")
        dm.transition_decision(d3.id, "approve")
        dm.transition_decision(d3.id, "supersede")  # approved→superseded
        with pytest.raises(ValueError):
            dm.transition_decision(d3.id, "approve")
        TenantContext.reset()

    def test_list_filter(self, registry, db):
        """8. list 按状态过滤 + 按项目隔离"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj1 = pm.create_project(name="项目A")
        proj2 = pm.create_project(name="项目B")

        d1 = dm.create_decision(project_id=proj1.id, title="决策A1")  # proposed
        d2 = dm.create_decision(project_id=proj1.id, title="决策A2")
        dm.transition_decision(d2.id, "approve")  # approved
        d3 = dm.create_decision(project_id=proj2.id, title="决策B1")  # proposed

        all_a = dm.list_decisions(proj1.id)
        assert len(all_a) == 2

        proposed = dm.list_decisions(proj1.id, status="proposed")
        assert len(proposed) == 1
        assert proposed[0].id == d1.id

        approved = dm.list_decisions(proj1.id, status="approved")
        assert len(approved) == 1
        assert approved[0].id == d2.id

        all_b = dm.list_decisions(proj2.id)
        assert len(all_b) == 1
        TenantContext.reset()

    def test_delete(self, registry, db):
        """9. 删除决策"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="删除测试")

        d = dm.create_decision(project_id=proj.id, title="待删决策")
        assert dm.delete_decision(d.id) is True
        assert dm.get_decision(d.id) is None
        assert dm.delete_decision(d.id) is False
        TenantContext.reset()

    def test_log_order(self, registry, db):
        """10. 决策日志按时间倒序"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="日志测试")

        d1 = dm.create_decision(project_id=proj.id, title="最早的决策")
        d2 = dm.create_decision(project_id=proj.id, title="中间的决策")
        d3 = dm.create_decision(project_id=proj.id, title="最新的决策")

        log = dm.log(proj.id)
        assert len(log) == 3
        # 按 created_at 倒序：最新的在前
        assert log[0].title == "最新的决策"
        assert log[1].title == "中间的决策"
        assert log[2].title == "最早的决策"
        TenantContext.reset()

    def test_project_cancelled(self, registry, db):
        """11. project.cancelled 联动：非终态→superseded，终态不变"""
        TenantContext.set("test")
        dm = registry.get("decision")
        pm = registry.get("project")
        proj = pm.create_project(name="联动项目")

        d_prop = dm.create_decision(project_id=proj.id, title="待决")
        d_appr = dm.create_decision(project_id=proj.id, title="已批")
        dm.transition_decision(d_appr.id, "approve")
        d_rej = dm.create_decision(project_id=proj.id, title="已拒")
        dm.transition_decision(d_rej.id, "reject")

        assert dm.get_decision(d_prop.id).status == "proposed"
        assert dm.get_decision(d_appr.id).status == "approved"
        assert dm.get_decision(d_rej.id).status == "rejected"

        pm.transition_project(proj.id, "cancel")

        # proposed → rejected（项目取消时否决待决策项）
        assert dm.get_decision(d_prop.id).status == "rejected"
        # 终态不变
        assert dm.get_decision(d_appr.id).status == "approved"
        assert dm.get_decision(d_rej.id).status == "rejected"
        TenantContext.reset()
