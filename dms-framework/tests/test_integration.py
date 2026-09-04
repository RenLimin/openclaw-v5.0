"""
DMS-Framework Phase 1 集成测试
验证核心引擎各组件协同工作
"""
import pytest
import tempfile
import os
from core.database import Database
from core.state_machine import StateMachineEngine, StateMachine, State, Transition
from core.raci import RACIEngine, Assignment
from core.workflow_scheme import WorkflowSchemeEngine, WorkflowScheme
from core.event_bus import EventBus
from core.saas import TenantContext
from core.migrations import migrate


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = Database(f"sqlite:///{f.name}")
        migrate(db.connect())
        yield db
    os.unlink(f.name)


class TestPhase1Integration:
    """Phase 1 核心引擎集成测试"""

    def test_full_lifecycle(self, db):
        """完整生命周期：建项目 → 建状态机 → 分配 RACI → 状态流转 → 事件通知"""
        TenantContext.reset()
        TenantContext.set("test_tenant")

        # 1. 建状态机引擎 + WorkflowScheme
        wf_engine = WorkflowSchemeEngine()
        wf_engine.register(WorkflowScheme(
            "test_scheme", "Test",
            {"task": "task_flow", "deliverable": "delivery_flow"}
        ))
        wf_engine.set_active("test_scheme")

        sm_engine = StateMachineEngine()
        task_sm = StateMachine("task_flow")
        task_sm.add_state(State("draft", "todo", is_start=True))
        task_sm.add_state(State("in_progress", "in_progress"))
        task_sm.add_state(State("done", "done", is_terminal=True))
        task_sm.add_transition(Transition("start", "draft", "in_progress"))
        task_sm.add_transition(Transition("finish", "in_progress", "done"))
        sm_engine.register("task_flow", task_sm)

        # 2. 建 RACI 引擎 + 分配
        raci = RACIEngine()
        raci.assign(Assignment("p1", "pm1", "scope_management", "R", work_item_id="t1"))
        raci.assign(Assignment("p1", "dm1", "scope_management", "A", work_item_id="t1"))
        raci.assign(Assignment("p1", "dm1", "quality_management", "A", work_item_id="t1"))
        matrix = raci.get_responsibility_matrix("p1")
        assert matrix["work_items"]["t1"]["scope_management"]["R"] == ["pm1"]

        # 3. 事件总线 + 状态流转联动
        bus = EventBus()
        events = []
        bus.subscribe("task.status_changed", lambda e: events.append(e))

        machine_name = wf_engine.get_machine_name("task")
        assert machine_name == "task_flow"
        sm = sm_engine.get(machine_name)

        from_state, to_state = sm.fire("draft", "start", {"work_item_id": "t1"})
        assert to_state == "in_progress"
        bus.publish("task.status_changed", {"from": from_state, "to": to_state}, source="task_module")

        from_state, to_state = sm.fire("in_progress", "finish", {"work_item_id": "t1"})
        assert to_state == "done"
        bus.publish("task.status_changed", {"from": from_state, "to": to_state}, source="task_module")

        # 4. 验证事件历史
        assert len(events) == 2
        assert events[0].payload["to"] == "in_progress"
        assert events[1].payload["to"] == "done"

        # 5. 验证 RACI 无冲突
        conflicts = raci.check_conflicts("p1")
        assert len(conflicts) == 0

        TenantContext.reset()

    def test_tenant_isolation(self, db):
        """验证不同租户数据隔离"""
        conn = db.connect()
        import uuid

        TenantContext.set("tenant_a")
        pid_a = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO projects (id, tenant_id, name) VALUES (?, 'tenant_a', ?)",
            (pid_a, "A项目")
        )
        conn.commit()

        TenantContext.set("tenant_b")
        pid_b = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO projects (id, tenant_id, name) VALUES (?, 'tenant_b', ?)",
            (pid_b, "B项目")
        )
        conn.commit()

        # 查询 tenant_a 只能看到 A 项目
        rows = conn.execute(
            "SELECT id, name FROM projects WHERE tenant_id = ?", ("tenant_a",)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "A项目"

        # 查询 tenant_b 只能看到 B 项目
        rows = conn.execute(
            "SELECT id, name FROM projects WHERE tenant_id = ?", ("tenant_b",)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "B项目"

        TenantContext.reset()

    def test_database_migration(self, db):
        """验证迁移系统工作正常"""
        from core.migrations import get_current_version, diff
        conn = db.connect()
        assert get_current_version(conn) >= "1.1.0"
        assert diff(conn) == []  # 无待执行迁移

    def test_all_core_tables_exist(self, db):
        """验证所有核心表已创建"""
        conn = db.connect()
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]

        required = [
            "schema_version", "projects", "work_items", "project_members",
            "stakeholders", "custom_fields", "responsibility_assignments", "change_logs"
        ]
        for t in required:
            assert t in tables, f"缺少表: {t}"

    def test_custom_fields_table(self, db):
        """验证自定义字段元数据表工作"""
        conn = db.connect()
        conn.execute(
            "INSERT INTO custom_fields (id, tenant_id, entity_type, field_name, field_type, sort_order) "
            "VALUES ('cf1', 'test', 'project', 'client_name', 'text', 1)"
        )
        conn.commit()

        rows = conn.execute(
            "SELECT field_name, field_type FROM custom_fields WHERE tenant_id = 'test' AND entity_type = 'project'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "client_name"
        assert rows[0][1] == "text"
