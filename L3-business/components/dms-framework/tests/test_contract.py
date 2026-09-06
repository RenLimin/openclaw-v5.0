"""
DMS-Framework contract 模块单元测试
覆盖 Contract 模型、ContractModule CRUD、状态机、事件联动、合规检查。
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
from core.event_bus import EventBus

from modules.project import manifest as project_manifest
from modules.project import ProjectModule
from modules.contract import manifest as contract_manifest
from modules.contract import ContractModule, Contract


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_obj = Database(f"sqlite:///{f.name}")
        migrate(db_obj.connect())
        yield db_obj
    os.unlink(f.name)


@pytest.fixture
def registry(db):
    """注册 project + contract 模块，并注入 event_bus 以支持事件联动。"""
    reg = ModuleRegistry()
    reg._event_bus = EventBus()
    reg.register(project_manifest, ProjectModule)
    reg.register(contract_manifest, ContractModule)
    reg.initialize_all(db, {})
    return reg


class TestContractModule:
    """contract 模块单元测试"""

    # 1. 创建，验证默认状态 draft
    def test_create(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="合同测试项目")
        c = cm.create_contract(project_id=proj.id, title="采购合同")

        assert c.id is not None
        assert c.title == "采购合同"
        assert c.status == "draft"
        assert c.type == "contract"
        assert c.project_id == proj.id
        assert c.tenant_id == "test"

        # 持久化校验
        got = cm.get_contract(c.id)
        assert got is not None
        assert got.status == "draft"
        TenantContext.reset()

    # 2. metadata 字段读写
    def test_metadata(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="元数据项目")
        c = cm.create_contract(project_id=proj.id, title="元数据合同")

        # 写入 metadata 字段
        c.contract_id = "CT-2026-001"
        c.party = "供应商A"
        c.amount = 99999.99
        c.terms = "按季度付款"
        c.effective_date = "2026-01-01"
        c.expiry_date = "2026-12-31"
        cm._repo.update(c)

        # 重新读取验证
        got = cm.get_contract(c.id)
        assert got.contract_id == "CT-2026-001"
        assert got.party == "供应商A"
        assert got.amount == pytest.approx(99999.99)
        assert got.terms == "按季度付款"
        assert got.effective_date == "2026-01-01"
        assert got.expiry_date == "2026-12-31"
        TenantContext.reset()

    # 3. 完整流程 draft→pending_approval→active→fulfilled
    def test_transition_submit_approve_fulfill(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="履约流程项目")
        c = cm.create_contract(project_id=proj.id, title="全流程合同")

        c = cm.transition_contract(c.id, "submit")
        assert c.status == "pending_approval"

        c = cm.transition_contract(c.id, "approve")
        assert c.status == "active"

        c = cm.transition_contract(c.id, "fulfill")
        assert c.status == "fulfilled"

        # 持久化校验
        got = cm.get_contract(c.id)
        assert got.status == "fulfilled"
        TenantContext.reset()

    # 4. pending_approval→rejected (terminal)
    def test_transition_reject(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="拒绝项目")
        c = cm.create_contract(project_id=proj.id, title="被拒合同")
        c = cm.transition_contract(c.id, "submit")
        assert c.status == "pending_approval"

        c = cm.transition_contract(c.id, "reject")
        assert c.status == "rejected"
        TenantContext.reset()

    # 5. active→disputed→active
    def test_transition_dispute_resolve(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="争议项目")
        c = cm.create_contract(project_id=proj.id, title="争议合同")
        c = cm.transition_contract(c.id, "submit")
        c = cm.transition_contract(c.id, "approve")
        assert c.status == "active"

        c = cm.transition_contract(c.id, "dispute")
        assert c.status == "disputed"

        c = cm.transition_contract(c.id, "resolve")
        assert c.status == "active"
        TenantContext.reset()

    # 6. active→terminated (terminal)
    def test_transition_terminate(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="终止项目")
        c = cm.create_contract(project_id=proj.id, title="终止合同")
        c = cm.transition_contract(c.id, "submit")
        c = cm.transition_contract(c.id, "approve")
        assert c.status == "active"

        c = cm.transition_contract(c.id, "terminate")
        assert c.status == "terminated"
        TenantContext.reset()

    # 7. 非法迁移抛 ValueError
    def test_invalid_transition(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="非法迁移项目")
        c = cm.create_contract(project_id=proj.id, title="非法合同")

        # draft 状态下不能直接 approve
        with pytest.raises(ValueError):
            cm.transition_contract(c.id, "approve")

        # 不存在的迁移名
        with pytest.raises(ValueError):
            cm.transition_contract(c.id, "nonexistent")

        # 合同不存在
        with pytest.raises(ValueError):
            cm.transition_contract("fake-id", "submit")
        TenantContext.reset()

    # 8. 终态不可迁移
    def test_terminal_no_transition(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="终态项目")

        # fulfilled 终态
        c1 = cm.create_contract(project_id=proj.id, title="已履约合同")
        cm.transition_contract(c1.id, "submit")
        cm.transition_contract(c1.id, "approve")
        cm.transition_contract(c1.id, "fulfill")
        assert cm.get_contract(c1.id).status == "fulfilled"
        with pytest.raises(ValueError):
            cm.transition_contract(c1.id, "terminate")

        # rejected 终态
        c2 = cm.create_contract(project_id=proj.id, title="被拒合同")
        cm.transition_contract(c2.id, "submit")
        cm.transition_contract(c2.id, "reject")
        assert cm.get_contract(c2.id).status == "rejected"
        with pytest.raises(ValueError):
            cm.transition_contract(c2.id, "approve")

        # terminated 终态
        c3 = cm.create_contract(project_id=proj.id, title="终止合同")
        cm.transition_contract(c3.id, "submit")
        cm.transition_contract(c3.id, "approve")
        cm.transition_contract(c3.id, "terminate")
        assert cm.get_contract(c3.id).status == "terminated"
        with pytest.raises(ValueError):
            cm.transition_contract(c3.id, "fulfill")
        TenantContext.reset()

    # 9. compliance_check 返回结果
    def test_compliance_check(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="合规项目")

        # active 但缺少元数据 → 不合规
        c1 = cm.create_contract(project_id=proj.id, title="不合规合同")
        cm.transition_contract(c1.id, "submit")
        cm.transition_contract(c1.id, "approve")

        # active 且元数据完整 → 合规
        c2 = cm.create_contract(project_id=proj.id, title="合规合同")
        cm.transition_contract(c2.id, "submit")
        cm.transition_contract(c2.id, "approve")
        c2.party = "供应商B"
        c2.amount = 50000.0
        c2.effective_date = "2026-01-01"
        c2.expiry_date = "2026-12-31"
        cm._repo.update(c2)

        issues = cm.compliance_check(proj.id)
        assert len(issues) >= 1
        # 不合规合同在列表中
        titles = [i["title"] for i in issues]
        assert "不合规合同" in titles
        # 合规合同不在列表中
        assert "合规合同" not in titles
        TenantContext.reset()

    # 10. project.cancelled 联动终止合同
    def test_project_cancelled(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="联动项目")

        # active 合同
        c1 = cm.create_contract(project_id=proj.id, title="生效合同")
        cm.transition_contract(c1.id, "submit")
        cm.transition_contract(c1.id, "approve")
        assert cm.get_contract(c1.id).status == "active"

        # draft 合同
        c2 = cm.create_contract(project_id=proj.id, title="草稿合同")
        assert cm.get_contract(c2.id).status == "draft"

        # 已履约（终态）合同，不应被修改
        c3 = cm.create_contract(project_id=proj.id, title="已履约合同")
        cm.transition_contract(c3.id, "submit")
        cm.transition_contract(c3.id, "approve")
        cm.transition_contract(c3.id, "fulfill")
        assert cm.get_contract(c3.id).status == "fulfilled"

        # 触发项目取消 → 发布 project.cancelled 事件
        pm.transition_project(proj.id, "cancel")

        # active 合同 → terminated
        assert cm.get_contract(c1.id).status == "terminated"
        # draft 合同 → terminated（非终态都终止）
        assert cm.get_contract(c2.id).status == "terminated"
        # 已履约保持不变
        assert cm.get_contract(c3.id).status == "fulfilled"
        TenantContext.reset()

    # 11. 按状态过滤
    def test_list_filter(self, registry, db):
        TenantContext.set("test")
        pm = registry.get("project")
        cm = registry.get("contract")

        proj = pm.create_project(name="过滤项目")

        # 3 个 draft
        cm.create_contract(project_id=proj.id, title="草稿1")
        cm.create_contract(project_id=proj.id, title="草稿2")
        cm.create_contract(project_id=proj.id, title="草稿3")

        # 2 个 active
        a1 = cm.create_contract(project_id=proj.id, title="生效1")
        cm.transition_contract(a1.id, "submit")
        cm.transition_contract(a1.id, "approve")
        a2 = cm.create_contract(project_id=proj.id, title="生效2")
        cm.transition_contract(a2.id, "submit")
        cm.transition_contract(a2.id, "approve")

        # 1 个 fulfilled
        f1 = cm.create_contract(project_id=proj.id, title="履约1")
        cm.transition_contract(f1.id, "submit")
        cm.transition_contract(f1.id, "approve")
        cm.transition_contract(f1.id, "fulfill")

        all_contracts = cm.list_contracts(proj.id)
        assert len(all_contracts) == 6

        drafts = cm.list_contracts(proj.id, status="draft")
        assert len(drafts) == 3
        assert all(c.status == "draft" for c in drafts)

        actives = cm.list_contracts(proj.id, status="active")
        assert len(actives) == 2
        assert all(c.status == "active" for c in actives)

        fulfilled = cm.list_contracts(proj.id, status="fulfilled")
        assert len(fulfilled) == 1
        assert fulfilled[0].title == "履约1"
        TenantContext.reset()
