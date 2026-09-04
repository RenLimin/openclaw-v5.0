"""
DMS-Framework 核心引擎测试
Phase 1 覆盖：状态机 / RACI / WorkflowScheme / EventBus / TenantContext / RouteDef
"""
import pytest
from core.state_machine import StateMachine, State, Transition, StateMachineEngine
from core.raci import RACIEngine, Assignment, RACI_ROLES, CAPABILITY_ATOMS, ROLE_TEMPLATES
from core.workflow_scheme import WorkflowScheme, WorkflowSchemeEngine, DEFAULT_SCHEME
from core.event_bus import EventBus, Event
from core.saas import TenantContext, RouteDef


# ── fixtures ──────────────────────────────────────────────────
@pytest.fixture
def raci():
    return RACIEngine()

@pytest.fixture
def event_bus():
    return EventBus()

@pytest.fixture
def sm():
    m = StateMachine("test")
    m.add_state(State("draft", "todo", is_start=True))
    m.add_state(State("review", "in_progress"))
    m.add_state(State("approved", "done", is_terminal=True))
    m.add_transition(Transition("submit", "draft", "review"))
    m.add_transition(Transition("approve", "review", "approved"))
    m.add_transition(Transition("reject", "review", "draft"))
    return m


# ── StateMachine ──────────────────────────────────────────────
class TestStateMachine:
    def test_start_state(self, sm):
        assert sm.get_start_state() == "draft"

    def test_can_transition(self, sm):
        assert sm.can_transition("draft", "submit")
        assert not sm.can_transition("draft", "approve")
        assert sm.can_transition("review", "approve")

    def test_fire_transition_returns_from_to(self, sm):
        from_s, to_s = sm.fire("draft", "submit", {})
        assert from_s == "draft"
        assert to_s == "review"

    def test_fire_approve(self, sm):
        _, to_s = sm.fire("review", "approve", {})
        assert to_s == "approved"

    def test_available_transitions(self, sm):
        available = sm.get_available_transitions("draft")
        assert "submit" in available
        assert "approve" not in available

    def test_terminal_state_no_transitions(self, sm):
        available = sm.get_available_transitions("approved")
        assert available == []

    def test_invalid_transition_raises(self, sm):
        with pytest.raises(ValueError):
            sm.fire("draft", "approve", {})

    def test_guard_blocks_transition(self, sm):
        """guard 返回 False 时不允许迁移"""
        m = StateMachine("guarded")
        m.add_state(State("a", "todo", is_start=True))
        m.add_state(State("b", "done", is_terminal=True))
        m.add_transition(Transition("go", "a", "b", guards=[lambda ctx: ctx.get("allow", False)]))
        with pytest.raises(PermissionError):
            m.fire("a", "go", {"allow": False})
        # guard 通过则可迁移
        from_s, to_s = m.fire("a", "go", {"allow": True})
        assert to_s == "b"


# ── StateMachineEngine ───────────────────────────────────────
class TestStateMachineEngine:
    def test_register_and_get(self, sm):
        engine = StateMachineEngine()
        engine.register("test_flow", sm)
        assert engine.get("test_flow") is sm

    def test_list_machines(self, sm):
        engine = StateMachineEngine()
        engine.register("test_flow", sm)
        names = engine.list_machines()
        assert "test_flow" in names

    def test_duplicate_register_raises(self, sm):
        engine = StateMachineEngine()
        engine.register("test_flow", sm)
        with pytest.raises(ValueError):
            engine.register("test_flow", sm)


# ── RACI Engine ───────────────────────────────────────────────
class TestRACI:
    def test_assign_and_query(self, raci):
        a = Assignment(
            project_id="p1", member_id="m1",
            capability="scope_management", raci_role="R",
            work_item_id="w1"
        )
        raci.assign(a)
        results = raci.get_assignments("p1")
        assert len(results) == 1
        assert results[0].member_id == "m1"
        assert results[0].raci_role == "R"

    def test_assign_is_upsert(self, raci):
        """assign 是 upsert，同 key 不报错，直接覆盖"""
        a = Assignment(
            project_id="p1", member_id="m1",
            capability="scope_management", raci_role="R",
            work_item_id="w1"
        )
        raci.assign(a)
        raci.assign(a)  # 不报错，upsert
        assert len(raci.get_assignments("p1")) == 1

    def test_unassign(self, raci):
        a = Assignment("p1", "m1", "scope_management", "R", work_item_id="w1")
        raci.assign(a)
        assert raci.unassign(a) is True
        assert len(raci.get_assignments("p1")) == 0
        assert raci.unassign(a) is False

    def test_conflict_same_person_r_and_a(self, raci):
        """同一人在同一任务同一能力上不能既是 R 又是 A"""
        raci.assign(Assignment("p1", "m1", "scope_management", "R", work_item_id="w1"))
        raci.assign(Assignment("p1", "m1", "scope_management", "A", work_item_id="w1"))
        conflicts = raci.check_conflicts("p1")
        assert len(conflicts) > 0
        assert any(c.type == "raci_mismatch" for c in conflicts)

    def test_validate_coverage_missing_r(self, raci):
        """每个任务+能力至少 1 个 R"""
        raci.assign(Assignment("p1", "m1", "scope_management", "A", work_item_id="w1"))
        gaps = raci.validate_coverage("p1", work_item_id="w1", required_capabilities=["scope_management"])
        assert len(gaps) > 0

    def test_responsibility_matrix(self, raci):
        raci.assign(Assignment("p1", "m1", "scope_management", "R", work_item_id="w1"))
        raci.assign(Assignment("p1", "m2", "scope_management", "C", work_item_id="w1"))
        matrix = raci.get_responsibility_matrix("p1")
        assert matrix["project_id"] == "p1"
        assert "w1" in matrix["work_items"]
        assert "scope_management" in matrix["work_items"]["w1"]
        assert "m1" in matrix["work_items"]["w1"]["scope_management"]["R"]
        assert "m2" in matrix["work_items"]["w1"]["scope_management"]["C"]

    def test_assign_by_role_template(self, raci):
        """按角色模板批量分配"""
        raci.assign_by_role("p1", "m1", "project_manager")
        results = raci.get_assignments("p1")
        assert len(results) > 0
        # 项目管理角色应包含 scope_management
        assert any(r.capability == "scope_management" for r in results)

    def test_all_capability_atoms_exist(self):
        assert "scope_management" in CAPABILITY_ATOMS
        assert "schedule_management" in CAPABILITY_ATOMS
        assert "risk_management" in CAPABILITY_ATOMS
        assert "quality_management" in CAPABILITY_ATOMS
        assert "deliverable_management" in CAPABILITY_ATOMS
        assert "milestone_tracking" in CAPABILITY_ATOMS
        assert "budget_management" in CAPABILITY_ATOMS
        assert "communication_management" in CAPABILITY_ATOMS

    def test_raci_roles(self):
        assert set(RACI_ROLES) == {"R", "A", "C", "I"}

    def test_role_templates_cover(self):
        assert "project_manager" in ROLE_TEMPLATES
        assert "delivery_manager" in ROLE_TEMPLATES
        assert "product_manager" in ROLE_TEMPLATES
        assert "scrum_master" in ROLE_TEMPLATES
        assert "qa_engineer" in ROLE_TEMPLATES
        assert "delivery_director" in ROLE_TEMPLATES


# ── WorkflowScheme ────────────────────────────────────────────
class TestWorkflowScheme:
    def test_scheme_creation(self):
        scheme = WorkflowScheme("test", "test", {
            "task": "task_flow",
            "deliverable": "delivery_flow"
        })
        assert scheme.get_machine_name("task") == "task_flow"
        assert scheme.get_machine_name("unknown") is None

    def test_scheme_entity_types(self):
        scheme = WorkflowScheme("test", "test", {"task": "t", "milestone": "m"})
        assert set(scheme.entity_types()) == {"task", "milestone"}

    def test_add_mapping(self):
        scheme = WorkflowScheme("test", "test", {})
        scheme.add_mapping("risk", "risk_flow")
        assert scheme.get_machine_name("risk") == "risk_flow"


# ── WorkflowSchemeEngine ─────────────────────────────────────
class TestWorkflowSchemeEngine:
    def test_default_builtin_schemes(self):
        engine = WorkflowSchemeEngine()
        schemes = engine.list_schemes()
        assert len(schemes) >= 3  # default + agile + waterfall
        assert any(s.name == "default" for s in schemes)

    def test_active_scheme_defaults_to_default(self):
        engine = WorkflowSchemeEngine()
        assert engine.get_active() == "default"

    def test_set_and_get_active(self):
        engine = WorkflowSchemeEngine()
        engine.set_active("agile")
        assert engine.get_active() == "agile"

    def test_get_machine_name(self):
        engine = WorkflowSchemeEngine()
        engine.set_active("default")
        # default scheme should have task mapping
        name = engine.get_machine_name("task")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_register_custom_scheme(self):
        engine = WorkflowSchemeEngine()
        scheme = WorkflowScheme("custom_scheme", "Custom", {"task": "custom_flow"})
        engine.register(scheme)
        engine.set_active("custom_scheme")
        assert engine.get_machine_name("task") == "custom_flow"

    def test_project_level_override(self):
        engine = WorkflowSchemeEngine()
        engine.register(WorkflowScheme("strict_scheme", "Strict", {"task": "strict_flow"}))
        engine.set_active("default")
        engine.set_project_scheme("p1", "strict_scheme")
        # p1 走 strict_scheme
        assert engine.get_machine_name("task", project_id="p1") == "strict_flow"
        # 其他项目走 default
        default_name = engine.get_machine_name("task", project_id="p2")
        assert default_name != "strict_flow"


# ── EventBus ──────────────────────────────────────────────────
class TestEventBus:
    def test_publish_subscribe(self, event_bus):
        received = []
        event_bus.subscribe("project.created", lambda e: received.append(e))
        event_bus.publish("project.created", {"id": "p1"}, source="project_module")
        assert len(received) == 1
        assert received[0].payload["id"] == "p1"
        assert received[0].name == "project.created"

    def test_no_subscription_no_event(self, event_bus):
        received = []
        event_bus.subscribe("project.created", lambda e: received.append(e))
        event_bus.publish("project.deleted", {"id": "p1"})
        assert len(received) == 0

    def test_history(self, event_bus):
        event_bus.publish("test.event", {"x": 1})
        event_bus.publish("test.event", {"x": 2})
        history = event_bus.get_history()
        assert len(history) == 2

    def test_multiple_subscribers(self, event_bus):
        r1, r2 = [], []
        event_bus.subscribe("test.event", lambda e: r1.append(e))
        event_bus.subscribe("test.event", lambda e: r2.append(e))
        event_bus.publish("test.event", {"x": 1})
        assert len(r1) == 1 and len(r2) == 1

    def test_event_has_timestamp(self, event_bus):
        event_bus.publish("test.event", {})
        e = event_bus.get_history()[0]
        assert e.timestamp is not None

    def test_predefined_events_exist(self, event_bus):
        assert len(event_bus.PREDEFINED_EVENTS) > 0
        assert "project.created" in event_bus.PREDEFINED_EVENTS


# ── TenantContext ────────────────────────────────────────────
class TestTenantContext:
    def test_default_system(self):
        TenantContext.reset()
        assert TenantContext.current() == "system"

    def test_set_and_get(self):
        TenantContext.reset()
        TenantContext.set("tenant_a")
        assert TenantContext.current() == "tenant_a"

    def test_reset(self):
        TenantContext.set("tenant_b")
        TenantContext.reset()
        assert TenantContext.current() == "system"


# ── RouteDef ─────────────────────────────────────────────────
class TestRouteDef:
    def test_basic(self):
        route = RouteDef(
            path="/api/projects",
            method="GET",
            handler="project.list",
            auth_required=True,
            rate_limit="100/min"
        )
        assert route.path == "/api/projects"
        assert route.method == "GET"

    def test_defaults(self):
        route = RouteDef(path="/api/test", method="POST", handler="test.action")
        assert route.auth_required is True
        assert route.rate_limit is None
