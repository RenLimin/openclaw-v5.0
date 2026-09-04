"""
DMS-Framework communication 模块单元测试
覆盖 Communication 模型 + CommunicationModule 的 CRUD / 状态机 / 事件联动
"""
import pytest
import tempfile
import os
import sys
sys.path.insert(0, '.')

from core.database import Database
from core.migrations import migrate
from core.saas import TenantContext
from core.event_bus import Event, EventBus
from core.state_machine import StateMachineEngine
from core.module import ModuleRegistry

from modules.project import manifest as project_manifest
from modules.project import ProjectModule
from modules.communication import manifest as communication_manifest
from modules.communication import CommunicationModule, Communication


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
    reg.register(communication_manifest, CommunicationModule)
    reg.initialize_all(db, {})
    return reg


class TestCommunicationModule:
    def test_create(self, registry, db):
        """创建，验证默认状态 planned"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="沟通测试项目")

        comm = cm.create_communication(project_id=proj.id, title="周报沟通")
        assert comm.title == "周报沟通"
        assert comm.status == "planned"
        assert comm.type == "communication"
        assert comm.project_id == proj.id
        assert comm.tenant_id == "test"
        assert comm.id is not None

        got = cm.get_communication(comm.id)
        assert got is not None
        assert got.status == "planned"
        TenantContext.reset()

    def test_metadata(self, registry, db):
        """channel/audience/frequency/message_type/scheduled_at 读写"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="元数据测试项目")

        comm = cm.create_communication(
            project_id=proj.id, title="状态汇报",
            channel="email", audience="stakeholders", frequency="weekly",
            message_type="status", scheduled_at="2026-09-10T10:00:00"
        )
        assert comm._meta("channel") == "email"
        assert comm._meta("audience") == "stakeholders"
        assert comm._meta("frequency") == "weekly"
        assert comm._meta("message_type") == "status"
        assert comm._meta("scheduled_at") == "2026-09-10T10:00:00"

        # 通过 __getattr__ 访问
        assert comm.channel == "email"
        assert comm.audience == "stakeholders"

        # 持久化后读取
        got = cm.get_communication(comm.id)
        assert got._meta("channel") == "email"
        assert got._meta("scheduled_at") == "2026-09-10T10:00:00"
        TenantContext.reset()

    def test_transition_start(self, registry, db):
        """planned → in_progress"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="迁移测试项目")
        comm = cm.create_communication(project_id=proj.id, title="启动沟通")

        assert comm.status == "planned"
        r = cm.transition_communication(comm.id, "start")
        assert r.status == "in_progress"
        got = cm.get_communication(comm.id)
        assert got.status == "in_progress"
        TenantContext.reset()

    def test_transition_complete(self, registry, db):
        """in_progress → completed (terminal)"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="完成测试项目")
        comm = cm.create_communication(project_id=proj.id, title="完成沟通")
        cm.transition_communication(comm.id, "start")

        r = cm.transition_communication(comm.id, "complete")
        assert r.status == "completed"

        # terminal: completed 后不能再迁移
        with pytest.raises(ValueError):
            cm.transition_communication(comm.id, "start")
        TenantContext.reset()

    def test_transition_escalate(self, registry, db):
        """in_progress → escalated → in_progress"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="升级测试项目")
        comm = cm.create_communication(project_id=proj.id, title="升级沟通")
        comm = cm.transition_communication(comm.id, "start")
        assert comm.status == "in_progress"

        # escalate
        r = cm.transition_communication(comm.id, "escalate")
        assert r.status == "escalated"
        got = cm.get_communication(comm.id)
        assert got.status == "escalated"

        # deescalate (回 in_progress)
        r = cm.transition_communication(comm.id, "deescalate")
        assert r.status == "in_progress"
        TenantContext.reset()

    def test_invalid_transition(self, registry, db):
        """非法迁移抛 ValueError"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="非法迁移测试")
        comm = cm.create_communication(project_id=proj.id, title="非法迁移")

        # planned 不能直接 complete
        with pytest.raises(ValueError):
            cm.transition_communication(comm.id, "complete")

        # 不存在的迁移名
        with pytest.raises(ValueError):
            cm.transition_communication(comm.id, "nonexistent")

        # 状态还是 planned
        got = cm.get_communication(comm.id)
        assert got.status == "planned"
        TenantContext.reset()

    def test_list_filter(self, registry, db):
        """按状态过滤"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="列表过滤项目")

        c1 = cm.create_communication(project_id=proj.id, title="A")
        c2 = cm.create_communication(project_id=proj.id, title="B")
        c3 = cm.create_communication(project_id=proj.id, title="C")

        cm.transition_communication(c2.id, "start")
        cm.transition_communication(c3.id, "start")
        cm.transition_communication(c3.id, "complete")

        # 全部
        all_items = cm.list_communications(project_id=proj.id)
        assert len(all_items) == 3

        # 按 planned 状态过滤
        planned = cm.list_communications(project_id=proj.id, status="planned")
        assert len(planned) == 1
        assert planned[0].title == "A"

        in_progress = cm.list_communications(project_id=proj.id, status="in_progress")
        assert len(in_progress) == 1
        assert in_progress[0].title == "B"

        completed = cm.list_communications(project_id=proj.id, status="completed")
        assert len(completed) == 1
        assert completed[0].title == "C"
        TenantContext.reset()

    def test_calendar(self, registry, db):
        """calendar 方法返回按 scheduled_at 升序的排序结果"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="日历测试项目")

        cm.create_communication(project_id=proj.id, title="周五汇报", scheduled_at="2026-09-20")
        cm.create_communication(project_id=proj.id, title="周一例会", scheduled_at="2026-09-08")
        cm.create_communication(project_id=proj.id, title="月末总结", scheduled_at="2026-09-30")
        cm.create_communication(project_id=proj.id, title="无计划")

        cal = cm.calendar(project_id=proj.id)
        assert len(cal) == 4
        dates = [c._meta("scheduled_at") or "" for c in cal]
        # 前三个有日期，按升序；最后一个无日期
        assert dates[0] == "2026-09-08"
        assert dates[1] == "2026-09-20"
        assert dates[2] == "2026-09-30"
        assert dates[3] == ""
        TenantContext.reset()

    def test_delete(self, registry, db):
        """删除"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="删除测试项目")
        comm = cm.create_communication(project_id=proj.id, title="待删除")

        assert cm.get_communication(comm.id) is not None

        result = cm.delete_communication(comm.id)
        assert result is True
        assert cm.get_communication(comm.id) is None

        # 重复删除返回 False
        result2 = cm.delete_communication(comm.id)
        assert result2 is False
        TenantContext.reset()

    def test_project_cancelled(self, registry, db):
        """project.cancelled 联动：planned 沟通自动转为 cancelled"""
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("communication")
        proj = pm.create_project(name="联动测试项目")

        c1 = cm.create_communication(project_id=proj.id, title="planned沟通")
        c2 = cm.create_communication(project_id=proj.id, title="进行中沟通")
        cm.transition_communication(c2.id, "start")

        # 取消项目
        pm.transition_project(proj.id, "start")
        pm.transition_project(proj.id, "cancel")

        # planned 的沟通应该被取消
        got1 = cm.get_communication(c1.id)
        assert got1.status == "cancelled"

        # in_progress 的沟通：当前实现仅处理 planned → cancel
        # 所以 in_progress 保持原状态
        got2 = cm.get_communication(c2.id)
        assert got2.status == "in_progress"
        TenantContext.reset()
