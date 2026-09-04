"""
DMS-Framework Phase 2 模块集成测试
覆盖 project / milestone / deliverable / risk / raci 5 个模块
"""
import pytest
import tempfile
import os
import sys
sys.path.insert(0, '.')

from core.database import Database
from core.migrations import migrate
from core.saas import TenantContext
from core.raci import Assignment
from core.module import ModuleRegistry

# 模块导入（subagent 完成后自动可用）
from modules.project import manifest as project_manifest
from modules.project import ProjectModule
from modules.milestone import manifest as milestone_manifest
from modules.milestone import MilestoneModule
from modules.deliverable import manifest as deliverable_manifest
from modules.deliverable import DeliverableModule
from modules.risk import manifest as risk_manifest
from modules.risk import RiskModule
from modules.raci import manifest as raci_manifest
from modules.raci import RACIModule


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
    reg.register(project_manifest, ProjectModule)
    reg.register(milestone_manifest, MilestoneModule)
    reg.register(deliverable_manifest, DeliverableModule)
    reg.register(risk_manifest, RiskModule)
    reg.register(raci_manifest, RACIModule)
    reg.initialize_all(db, {})
    return reg


class TestProjectModule:
    def test_project_crud(self, registry, db):
        """项目 CRUD 全流程"""
        TenantContext.set("test")
        pm = registry.get("project")

        # create
        proj = pm.create_project(name="测试项目", description="desc")
        assert proj.name == "测试项目"
        assert proj.status == "planning"
        assert proj.tenant_id == "test"
        assert proj.id is not None

        # get
        got = pm.get_project(proj.id)
        assert got.name == "测试项目"

        # list
        projects = pm.list_projects()
        assert len(projects) >= 1

        # transition
        result = pm.transition_project(proj.id, "start")
        assert result.status == "in_progress"
        got = pm.get_project(proj.id)
        assert got.status == "in_progress"

        # delete
        result = pm.delete_project(proj.id)
        assert result is True
        assert pm.get_project(proj.id) is None
        TenantContext.reset()

    def test_project_status_workflow(self, registry, db):
        """项目状态机完整流转"""
        TenantContext.set("test")
        pm = registry.get("project")
        proj = pm.create_project(name="WF测试")

        # planning → in_progress → review → completed
        r = pm.transition_project(proj.id, "start")
        assert r.status == "in_progress"
        r = pm.transition_project(proj.id, "submit")
        assert r.status == "review"
        r = pm.transition_project(proj.id, "accept")
        assert r.status == "completed"

        TenantContext.reset()

    def test_project_cancel(self, registry, db):
        """项目取消（任意非终态 → cancelled）"""
        TenantContext.set("test")
        pm = registry.get("project")
        proj = pm.create_project(name="取消测试")
        pm.transition_project(proj.id, "start")
        result = pm.transition_project(proj.id, "cancel")
        assert result.status == "cancelled"
        TenantContext.reset()


class TestMilestoneModule:
    def test_milestone_crud(self, registry, db):
        """里程碑 CRUD"""
        TenantContext.set("test")
        pm = registry.get("project")
        mm = registry.get("milestone")
        proj = pm.create_project(name="里程碑项目")

        ms = mm.create_milestone(project_id=proj.id, title="M1", priority="high")
        assert ms.title == "M1"
        assert ms.type == "milestone"
        assert ms.project_id == proj.id
        assert ms.status == "pending"

        got = mm.get_milestone(ms.id)
        assert got.title == "M1"

        mlist = mm.list_milestones(project_id=proj.id)
        assert len(mlist) >= 1
        TenantContext.reset()

    def test_milestone_workflow(self, registry, db):
        """里程碑状态流转"""
        TenantContext.set("test")
        pm = registry.get("project")
        mm = registry.get("milestone")
        proj = pm.create_project(name="MS项目")
        ms = mm.create_milestone(project_id=proj.id, title="M1")

        r = mm.transition_milestone(ms.id, "start")
        assert r.status == "in_progress"
        r = mm.transition_milestone(ms.id, "achieve")
        assert r.status == "achieved"
        TenantContext.reset()


class TestDeliverableModule:
    def test_deliverable_crud(self, registry, db):
        """交付物 CRUD"""
        TenantContext.set("test")
        pm = registry.get("project")
        dm = registry.get("deliverable")
        proj = pm.create_project(name="交付物项目")

        d = dm.create_deliverable(project_id=proj.id, title="设计文档")
        assert d.title == "设计文档"
        assert d.type == "deliverable"
        assert d.status == "draft"

        got = dm.get_deliverable(d.id)
        assert got.title == "设计文档"
        TenantContext.reset()

    def test_deliverable_workflow(self, registry, db):
        """交付物审批流程"""
        TenantContext.set("test")
        pm = registry.get("project")
        dm = registry.get("deliverable")
        proj = pm.create_project(name="审批项目")
        d = dm.create_deliverable(project_id=proj.id, title="PRD文档")

        r = dm.transition_deliverable(d.id, "submit")
        assert r.status == "in_review"
        r = dm.transition_deliverable(d.id, "approve")
        assert r.status == "accepted"
        TenantContext.reset()


class TestRiskModule:
    def test_risk_crud(self, registry, db):
        """风险 CRUD"""
        TenantContext.set("test")
        pm = registry.get("project")
        rm = registry.get("risk")
        proj = pm.create_project(name="风险项目")

        r = rm.create_risk(project_id=proj.id, title="技术风险", priority="high")
        assert r.title == "技术风险"
        assert r.type == "risk"
        assert r.status == "identified"
        TenantContext.reset()

    def test_risk_workflow(self, registry, db):
        """风险全生命周期"""
        TenantContext.set("test")
        pm = registry.get("project")
        rm = registry.get("risk")
        proj = pm.create_project(name="风险流程")
        r = rm.create_risk(project_id=proj.id, title="需求风险")

        r2 = rm.transition_risk(r.id, "analyze")
        assert r2.status == "analyzing"
        r2 = rm.transition_risk(r.id, "plan")
        assert r2.status == "mitigating"
        r2 = rm.transition_risk(r.id, "resolve")
        assert r2.status == "resolved"
        TenantContext.reset()


class TestRACIModule:
    def test_raci_assign_and_query(self, registry, db):
        """RACI 分配与查询（持久化）"""
        TenantContext.set("test")
        pm = registry.get("project")
        proj = pm.create_project(name="RACI测试项目")
        rm = registry.get("raci")

        rm.assign(Assignment(
            project_id=proj.id,
            member_id="m1",
            capability="scope_management",
            raci_role="R"
        ))
        assignments = rm.get_assignments(project_id=proj.id)
        assert len(assignments) >= 1
        assert any(a.member_id == "m1" for a in assignments)
        TenantContext.reset()

    def test_raci_conflict_detection(self, registry, db):
        """RACI 冲突检测"""
        TenantContext.set("test")
        pm = registry.get("project")
        proj = pm.create_project(name="冲突测试项目")
        rm = registry.get("raci")

        rm.assign(Assignment(proj.id, "m1", "scope_management", "R"))
        rm.assign(Assignment(proj.id, "m1", "scope_management", "A"))
        conflicts = rm.check_conflicts(proj.id)
        assert len(conflicts) > 0
        TenantContext.reset()

    def test_raci_coverage_check(self, registry, db):
        """RACI 覆盖率检查"""
        TenantContext.set("test")
        pm = registry.get("project")
        proj = pm.create_project(name="覆盖测试项目")
        rm = registry.get("raci")

        rm.assign(Assignment(proj.id, "m1", "scope_management", "A"))
        gaps = rm.validate_coverage(proj.id)
        assert len(gaps) > 0  # 缺 R
        TenantContext.reset()


class TestCrossModule:
    def test_full_delivery_lifecycle(self, registry, db):
        """端到端交付全流程：建项目 → 建里程碑 → 建交付物 → 建风险 → 分配RACI"""
        TenantContext.set("test")
        pm = registry.get("project")
        mm = registry.get("milestone")
        dm = registry.get("deliverable")
        rm = registry.get("risk")
        raci = registry.get("raci")

        # 1. 建项目
        proj = pm.create_project(name="端到端交付项目", description="E2E测试")
        assert proj.status == "planning"

        # 2. 建里程碑
        m1 = mm.create_milestone(project_id=proj.id, title="设计完成", priority="high")
        m2 = mm.create_milestone(project_id=proj.id, title="交付上线", priority="high")
        assert len(mm.list_milestones(project_id=proj.id)) == 2

        # 3. 建交付物
        d1 = dm.create_deliverable(project_id=proj.id, title="设计文档", priority="high")
        d2 = dm.create_deliverable(project_id=proj.id, title="测试报告")
        assert len(dm.list_deliverables(project_id=proj.id)) == 2

        # 4. 建风险
        r1 = rm.create_risk(project_id=proj.id, title="技术选型风险", priority="high")
        assert len(rm.list_risks(project_id=proj.id)) == 1

        # 5. 分配 RACI
        raci.assign(Assignment(proj.id, "pm1", "scope_management", "R"))
        raci.assign(Assignment(proj.id, "dm1", "scope_management", "A"))
        assert len(raci.get_assignments(project_id=proj.id)) == 2

        # 6. 项目开始
        pm.transition_project(proj.id, "start")
        got = pm.get_project(proj.id)
        assert got.status == "in_progress"

        # 7. 完成里程碑
        mm.transition_milestone(m1.id, "start")
        mm.transition_milestone(m1.id, "achieve")
        assert mm.get_milestone(m1.id).status == "achieved"

        # 8. 交付物验收
        dm.transition_deliverable(d1.id, "submit")
        dm.transition_deliverable(d1.id, "approve")
        assert dm.get_deliverable(d1.id).status == "accepted"

        # 9. 风险关闭
        rm.transition_risk(r1.id, "analyze")
        rm.transition_risk(r1.id, "plan")
        rm.transition_risk(r1.id, "resolve")
        assert rm.get_risk(r1.id).status == "resolved"

        # 10. 项目验收
        pm.transition_project(proj.id, "submit")
        pm.transition_project(proj.id, "accept")
        assert pm.get_project(proj.id).status == "completed"

        TenantContext.reset()

    def test_tenant_isolation(self, registry, db):
        """跨租户数据隔离验证"""
        TenantContext.set("tenant_a")
        pm = registry.get("project")
        pa = pm.create_project(name="A租户项目")

        TenantContext.set("tenant_b")
        pb = pm.create_project(name="B租户项目")

        # A 只能看到自己的
        TenantContext.set("tenant_a")
        pa_list = pm.list_projects()
        assert len(pa_list) == 1
        assert pa_list[0].name == "A租户项目"

        # B 只能看到自己的
        TenantContext.set("tenant_b")
        pb_list = pm.list_projects()
        assert len(pb_list) == 1
        assert pb_list[0].name == "B租户项目"

        TenantContext.reset()


class TestModuleManifest:
    def test_all_modules_registered(self, registry):
        """所有 5 个模块都已注册"""
        for name in ["project", "milestone", "deliverable", "risk", "raci"]:
            assert registry.has_module(name), f"模块 {name} 未注册"

    def test_module_dependencies(self):
        """依赖关系正确"""
        assert "project" in milestone_manifest.dependencies
        assert "project" in deliverable_manifest.dependencies
        assert "project" in risk_manifest.dependencies
        assert "project" in raci_manifest.dependencies

    def test_project_no_dependencies(self):
        """project 模块无依赖"""
        assert len(project_manifest.dependencies) == 0
