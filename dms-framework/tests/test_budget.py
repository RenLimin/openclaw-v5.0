"""
DMS-Framework budget 模块单元测试
覆盖 Budget 模型、状态机、CRUD、事件联动、summary 统计
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
from core.event_bus import Event

from modules.project import manifest as project_manifest
from modules.project import ProjectModule
from modules.budget import manifest as budget_manifest
from modules.budget import BudgetModule, Budget


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
    reg.register(budget_manifest, BudgetModule)
    reg.initialize_all(db, {})
    return reg


class TestBudgetModule:
    def test_create(self, registry, db):
        """1. 创建预算，验证默认状态 draft"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="预算项目")

        b = bm.create_budget(project_id=proj.id, title="测试预算",
                             planned_cost=10000.0, cost_type="capital")
        assert isinstance(b, Budget)
        assert b.id is not None
        assert b.title == "测试预算"
        assert b.status == "draft"
        assert b.type == "budget"
        assert b.project_id == proj.id
        assert b.tenant_id == "test"
        TenantContext.reset()

    def test_metadata(self, registry, db):
        """2. planned_cost / actual_cost / variance / cost_type 读写"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="元数据项目")

        b = bm.create_budget(project_id=proj.id, title="元数据预算",
                             planned_cost=5000.0, cost_type="operational")
        # 读
        assert b.planned_cost == 5000.0
        assert b.actual_cost == 0.0
        assert b.cost_type == "operational"

        # 写回并持久化
        b.actual_cost = 3000.0
        b.cost_type = "capital"
        # 通过 repo 更新（模拟外部修改后保存）
        bm._repo.update(b)

        got = bm.get_budget(b.id)
        assert got.planned_cost == 5000.0
        assert got.actual_cost == 3000.0
        assert got.cost_type == "capital"
        TenantContext.reset()

    def test_variance_auto_calc(self, registry, db):
        """3. variance 自动计算（代码实现：actual_cost - planned_cost）"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="偏差项目")

        b = bm.create_budget(project_id=proj.id, title="偏差预算", planned_cost=10000.0)
        # 刚创建时 actual=0，variance = 0 - 10000 = -10000
        assert b.variance == -10000.0

        # 修改 actual_cost，variance 自动更新
        b.actual_cost = 8000.0
        assert b.actual_cost == 8000.0
        assert b.variance == 8000.0 - 10000.0  # -2000

        # 修改 planned_cost，variance 也自动更新
        b.planned_cost = 9000.0
        assert b.variance == 8000.0 - 9000.0  # -1000

        # 超支：actual > planned → variance 为正
        b.actual_cost = 12000.0
        assert b.variance == 12000.0 - 9000.0  # 3000
        TenantContext.reset()

    def test_transition_approve(self, registry, db):
        """4. draft → approved"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="审批项目")

        b = bm.create_budget(project_id=proj.id, title="审批预算")
        assert b.status == "draft"

        r = bm.transition_budget(b.id, "approve")
        assert r.status == "approved"

        got = bm.get_budget(b.id)
        assert got.status == "approved"
        TenantContext.reset()

    def test_transition_execute(self, registry, db):
        """5. approved → executing"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="执行项目")

        b = bm.create_budget(project_id=proj.id, title="执行预算")
        bm.transition_budget(b.id, "approve")
        assert bm.get_budget(b.id).status == "approved"

        r = bm.transition_budget(b.id, "execute")
        assert r.status == "executing"
        TenantContext.reset()

    def test_transition_overrun(self, registry, db):
        """6. executing → over_budget"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="超支项目")

        b = bm.create_budget(project_id=proj.id, title="超支预算")
        bm.transition_budget(b.id, "approve")
        bm.transition_budget(b.id, "execute")
        assert bm.get_budget(b.id).status == "executing"

        r = bm.transition_budget(b.id, "flag_over_budget")
        assert r.status == "over_budget"

        # 还可以回到 executing
        r2 = bm.transition_budget(b.id, "back_to_executing")
        assert r2.status == "executing"
        TenantContext.reset()

    def test_transition_close(self, registry, db):
        """7. executing → closed (terminal)"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="关闭项目")

        b = bm.create_budget(project_id=proj.id, title="关闭预算")
        bm.transition_budget(b.id, "approve")
        bm.transition_budget(b.id, "execute")

        r = bm.transition_budget(b.id, "close")
        assert r.status == "closed"

        # closed 是终态，无法继续迁移
        with pytest.raises(ValueError):
            bm.transition_budget(b.id, "flag_over_budget")
        TenantContext.reset()

    def test_invalid_transition(self, registry, db):
        """8. 非法迁移抛 ValueError"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="非法迁移项目")

        b = bm.create_budget(project_id=proj.id, title="非法预算")

        # draft 不能直接 close
        with pytest.raises(ValueError):
            bm.transition_budget(b.id, "close")

        # draft 不能直接 execute
        with pytest.raises(ValueError):
            bm.transition_budget(b.id, "execute")

        # 不存在的迁移名
        with pytest.raises(ValueError):
            bm.transition_budget(b.id, "nonexistent_action")

        # 不存在的预算 ID
        with pytest.raises(ValueError):
            bm.transition_budget("non-exist-id", "approve")
        TenantContext.reset()

    def test_budget_summary(self, registry, db):
        """9. 统计视图：count / total_planned / total_actual / total_variance"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="汇总项目")

        # 空项目
        s0 = bm.summary(proj.id)
        assert s0["count"] == 0
        assert s0["total_planned"] == 0.0
        assert s0["total_actual"] == 0.0
        assert s0["total_variance"] == 0.0

        # 添加 3 条预算
        b1 = bm.create_budget(project_id=proj.id, title="B1", planned_cost=10000.0)
        b2 = bm.create_budget(project_id=proj.id, title="B2", planned_cost=20000.0)
        b3 = bm.create_budget(project_id=proj.id, title="B3", planned_cost=5000.0)

        # 设置实际成本
        b1.actual_cost = 8000.0
        b2.actual_cost = 22000.0
        b3.actual_cost = 5000.0
        bm._repo.update(b1)
        bm._repo.update(b2)
        bm._repo.update(b3)

        s = bm.summary(proj.id)
        assert s["count"] == 3
        assert s["total_planned"] == 35000.0
        assert s["total_actual"] == 35000.0
        assert s["total_variance"] == 0.0  # 35000 - 35000

        # list 过滤验证
        drafts = bm.list_budgets(proj.id, status="draft")
        assert len(drafts) == 3
        TenantContext.reset()

    def test_project_cancelled(self, registry, db):
        """10. project.cancelled 联动：draft→cancelled, executing→closed"""
        TenantContext.set("test")
        bm = registry.get("budget")
        pm = registry.get("project")
        proj = pm.create_project(name="联动项目")

        # draft 状态预算
        b_draft = bm.create_budget(project_id=proj.id, title="草稿预算")
        # approved 状态预算（不在联动映射中，应保持不变）
        b_approved = bm.create_budget(project_id=proj.id, title="已批预算")
        bm.transition_budget(b_approved.id, "approve")
        # executing 状态预算
        b_exec = bm.create_budget(project_id=proj.id, title="执行中预算")
        bm.transition_budget(b_exec.id, "approve")
        bm.transition_budget(b_exec.id, "execute")
        # 已终态的预算（closed）
        b_closed = bm.create_budget(project_id=proj.id, title="已关闭预算")
        bm.transition_budget(b_closed.id, "approve")
        bm.transition_budget(b_closed.id, "execute")
        bm.transition_budget(b_closed.id, "close")

        assert bm.get_budget(b_draft.id).status == "draft"
        assert bm.get_budget(b_approved.id).status == "approved"
        assert bm.get_budget(b_exec.id).status == "executing"
        assert bm.get_budget(b_closed.id).status == "closed"

        # 取消项目 → 触发 project.cancelled 事件
        pm.transition_project(proj.id, "cancel")

        # draft → cancelled
        assert bm.get_budget(b_draft.id).status == "cancelled"
        # approved → 保持不变（不在联动映射中）
        assert bm.get_budget(b_approved.id).status == "approved"
        # executing → closed
        assert bm.get_budget(b_exec.id).status == "closed"
        # closed → 保持 closed（已是终态）
        assert bm.get_budget(b_closed.id).status == "closed"
        TenantContext.reset()
