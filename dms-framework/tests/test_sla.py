"""
DMS-Framework sla 模块单元测试
覆盖 SLA 模型、状态机、CRUD、事件联动
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
from modules.sla import manifest as sla_manifest
from modules.sla import SLAModule


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
    reg.register(sla_manifest, SLAModule)
    reg.initialize_all(db, {})
    return reg


class TestSLAModule:
    def test_create(self, registry, db):
        """1. 创建 SLA，默认状态 defined"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="SLA项目")

        s = sm.create_sla(project_id=proj.id, title="响应时间SLA",
                          priority="high")
        assert s.id is not None
        assert s.title == "响应时间SLA"
        assert s.status == "defined"
        assert s.type == "sla"
        assert s.priority == "high"

        got = sm.get_sla(s.id)
        assert got is not None
        assert got.title == "响应时间SLA"
        assert got.priority == "high"
        TenantContext.reset()

    def test_metadata(self, registry, db):
        """2. metadata 字段读写：priority / assignee_id / description"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="元数据项目")

        s = sm.create_sla(project_id=proj.id, title="可用性SLA",
                          description="99.9%可用性承诺",
                          priority="critical", assignee_id="ops-001")
        sm._repo.update(s)

        got = sm.get_sla(s.id)
        assert got.description == "99.9%可用性承诺"
        assert got.priority == "critical"
        assert got.assignee_id == "ops-001"
        TenantContext.reset()

    def test_transition_start_monitoring(self, registry, db):
        """3. defined → monitoring 开始监控"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="监控测试")

        s = sm.create_sla(project_id=proj.id, title="SLA1")
        assert s.status == "defined"

        s = sm.transition_sla(s.id, "start_monitoring")
        assert s.status == "monitoring"
        assert sm.get_sla(s.id).status == "monitoring"
        TenantContext.reset()

    def test_transition_meet(self, registry, db):
        """4. monitoring → met 达标"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="达标测试")

        s = sm.create_sla(project_id=proj.id, title="SLA2")
        sm.transition_sla(s.id, "start_monitoring")
        s = sm.transition_sla(s.id, "meet")
        assert s.status == "met"
        assert sm.get_sla(s.id).status == "met"
        TenantContext.reset()

    def test_transition_breach_resume(self, registry, db):
        """5. monitoring → breached → monitoring 违约往返"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="违约测试")

        s = sm.create_sla(project_id=proj.id, title="SLA3")
        sm.transition_sla(s.id, "start_monitoring")

        s = sm.transition_sla(s.id, "breach")
        assert s.status == "breached"
        assert sm.get_sla(s.id).status == "breached"

        s = sm.transition_sla(s.id, "resume")
        assert s.status == "monitoring"
        TenantContext.reset()

    def test_transition_escalate(self, registry, db):
        """6. breached → escalated → monitoring 升级往返"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="升级测试")

        s = sm.create_sla(project_id=proj.id, title="SLA4")
        sm.transition_sla(s.id, "start_monitoring")
        sm.transition_sla(s.id, "breach")

        s = sm.transition_sla(s.id, "escalate")
        assert s.status == "escalated"
        assert sm.get_sla(s.id).status == "escalated"

        s = sm.transition_sla(s.id, "escalate_resume")
        assert s.status == "monitoring"
        TenantContext.reset()

    def test_transition_close_terminal(self, registry, db):
        """7. 各状态关闭到 closed（终态）"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="关闭测试")

        # defined → closed
        s1 = sm.create_sla(project_id=proj.id, title="SLA-d")
        s1 = sm.transition_sla(s1.id, "close")
        assert s1.status == "closed"

        # monitoring → closed
        s2 = sm.create_sla(project_id=proj.id, title="SLA-m")
        sm.transition_sla(s2.id, "start_monitoring")
        s2 = sm.transition_sla(s2.id, "close_monitoring")
        assert s2.status == "closed"

        # met → closed
        s3 = sm.create_sla(project_id=proj.id, title="SLA-t")
        sm.transition_sla(s3.id, "start_monitoring")
        sm.transition_sla(s3.id, "meet")
        s3 = sm.transition_sla(s3.id, "close_met")
        assert s3.status == "closed"

        # 终态不能再迁移
        with pytest.raises(ValueError):
            sm.transition_sla(s3.id, "start_monitoring")
        TenantContext.reset()

    def test_invalid_transition(self, registry, db):
        """8. 非法迁移抛 ValueError"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="非法迁移")

        s = sm.create_sla(project_id=proj.id, title="SLA5")
        # defined 不能直接 breach
        with pytest.raises(ValueError):
            sm.transition_sla(s.id, "breach")
        # 不存在的迁移名
        with pytest.raises(ValueError):
            sm.transition_sla(s.id, "nonexistent_action")
        # 不存在的 SLA ID
        with pytest.raises(ValueError):
            sm.transition_sla("non-exist-id", "start_monitoring")
        TenantContext.reset()

    def test_list_filter(self, registry, db):
        """9. list 按状态过滤 + 按项目隔离"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj1 = pm.create_project(name="项目A")
        proj2 = pm.create_project(name="项目B")

        s1 = sm.create_sla(project_id=proj1.id, title="SLA-A1")  # defined
        s2 = sm.create_sla(project_id=proj1.id, title="SLA-A2")
        sm.transition_sla(s2.id, "start_monitoring")  # monitoring
        s3 = sm.create_sla(project_id=proj2.id, title="SLA-B1")  # defined

        all_a = sm.list_slas(proj1.id)
        assert len(all_a) == 2
        defineds = sm.list_slas(proj1.id, status="defined")
        assert len(defineds) == 1
        assert defineds[0].id == s1.id
        monitorings = sm.list_slas(proj1.id, status="monitoring")
        assert len(monitorings) == 1
        assert monitorings[0].id == s2.id
        all_b = sm.list_slas(proj2.id)
        assert len(all_b) == 1
        TenantContext.reset()

    def test_delete(self, registry, db):
        """10. 删除 SLA"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="删除测试")

        s = sm.create_sla(project_id=proj.id, title="待删SLA")
        assert sm.delete_sla(s.id) is True
        assert sm.get_sla(s.id) is None
        assert sm.delete_sla(s.id) is False
        TenantContext.reset()

    def test_project_cancelled(self, registry, db):
        """11. project.cancelled 联动：非终态→closed，终态不变"""
        TenantContext.set("test")
        sm = registry.get("sla")
        pm = registry.get("project")
        proj = pm.create_project(name="联动项目")

        # defined
        s_def = sm.create_sla(project_id=proj.id, title="已定义SLA")
        # monitoring
        s_mon = sm.create_sla(project_id=proj.id, title="监控中SLA")
        sm.transition_sla(s_mon.id, "start_monitoring")
        # closed
        s_cls = sm.create_sla(project_id=proj.id, title="已关闭SLA")
        sm.transition_sla(s_cls.id, "close")

        assert sm.get_sla(s_def.id).status == "defined"
        assert sm.get_sla(s_mon.id).status == "monitoring"
        assert sm.get_sla(s_cls.id).status == "closed"

        pm.transition_project(proj.id, "cancel")

        # defined → closed
        assert sm.get_sla(s_def.id).status == "closed"
        # monitoring → closed
        assert sm.get_sla(s_mon.id).status == "closed"
        # 已终态不变
        assert sm.get_sla(s_cls.id).status == "closed"
        TenantContext.reset()
