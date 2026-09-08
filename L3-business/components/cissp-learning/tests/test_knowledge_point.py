"""知识点测试。"""

from models.knowledge_point import (
    KnowledgePoint,
    CISSPDomain,
    KnowledgeLevel,
)
from repositories.knowledge_point_repo import KnowledgePointRepository


class TestKnowledgePointModel:
    def test_create_kp(self):
        kp = KnowledgePoint(
            title="信息安全治理",
            description="信息安全治理的基本原则",
            content="## 信息安全治理\n\n治理是...",
            domain=CISSPDomain.SECURITY_RISK_MANAGEMENT,
            level=KnowledgeLevel.NOT_STARTED,
        )
        assert kp.title == "信息安全治理"
        assert kp.domain == CISSPDomain.SECURITY_RISK_MANAGEMENT
        assert kp.level == KnowledgeLevel.NOT_STARTED
        assert kp.is_root() is True
        assert kp.is_leaf is True

    def test_tree_structure(self):
        kp = KnowledgePoint(
            title="子知识点",
            parent_id="parent-001",
            path="security_risk_management/governance/sub",
            depth=2,
        )
        assert kp.is_root() is False
        assert kp.depth == 2
        assert kp.parent_id == "parent-001"

    def test_is_descendant_of(self):
        kp = KnowledgePoint(
            title="孙子节点",
            path="root/parent/child",
            depth=2,
        )
        assert kp.is_descendant_of("root/parent") is True
        assert kp.is_descendant_of("root") is True
        assert kp.is_descendant_of("other") is False

    def test_update_level(self):
        kp = KnowledgePoint(title="测试")
        assert kp.level == KnowledgeLevel.NOT_STARTED
        kp.update_level(KnowledgeLevel.UNDERSTAND)
        assert kp.level == KnowledgeLevel.UNDERSTAND

    def test_increment_view(self):
        kp = KnowledgePoint(title="测试")
        assert kp.view_count == 0
        kp.increment_view()
        kp.increment_view()
        assert kp.view_count == 2

    def test_cissp_domains_count(self):
        """CISSP 应为 8 大域。"""
        assert len(CISSPDomain) == 8

    def test_knowledge_levels(self):
        assert len(KnowledgeLevel) == 5


class TestKnowledgePointRepository:
    def test_create_and_get(self):
        kp = KnowledgePointRepository.create(
            title="访问控制",
            domain=CISSPDomain.IDENTITY_ACCESS_MANAGEMENT,
            category="core",
        )
        fetched = KnowledgePointRepository.get_by_id(kp.id)
        assert fetched is not None
        assert fetched.title == "访问控制"
        assert fetched.domain == CISSPDomain.IDENTITY_ACCESS_MANAGEMENT

    def test_list_by_domain(self):
        KnowledgePointRepository.create(
            title="治理1", domain=CISSPDomain.SECURITY_RISK_MANAGEMENT,
        )
        KnowledgePointRepository.create(
            title="治理2", domain=CISSPDomain.SECURITY_RISK_MANAGEMENT,
        )
        KnowledgePointRepository.create(
            title="资产安全", domain=CISSPDomain.ASSET_SECURITY,
        )
        results = KnowledgePointRepository.list_by_domain(
            CISSPDomain.SECURITY_RISK_MANAGEMENT
        )
        assert len(results) == 2

    def test_list_roots(self):
        KnowledgePointRepository.create(
            title="根节点1", depth=0, parent_id=None,
        )
        KnowledgePointRepository.create(
            title="子节点", depth=1, parent_id="p1",
        )
        roots = KnowledgePointRepository.list_roots()
        assert len(roots) == 1
        assert roots[0].title == "根节点1"

    def test_list_children(self):
        parent = KnowledgePointRepository.create(
            title="父节点", depth=0,
        )
        KnowledgePointRepository.create(
            title="子节点1", depth=1, parent_id=parent.id,
        )
        KnowledgePointRepository.create(
            title="子节点2", depth=1, parent_id=parent.id,
        )
        children = KnowledgePointRepository.list_children(parent.id)
        assert len(children) == 2

    def test_search_by_title(self):
        KnowledgePointRepository.create(title="加密算法基础")
        KnowledgePointRepository.create(title="网络协议安全")
        KnowledgePointRepository.create(title="加密技术进阶")
        results = KnowledgePointRepository.search_by_title("加密")
        assert len(results) == 2

    def test_list_by_level(self):
        KnowledgePointRepository.create(
            title="已掌握", level=KnowledgeLevel.EXPERT,
        )
        KnowledgePointRepository.create(
            title="学习中", level=KnowledgeLevel.UNDERSTAND,
        )
        expert = KnowledgePointRepository.list_by_level(KnowledgeLevel.EXPERT)
        assert len(expert) == 1
        assert expert[0].title == "已掌握"

    def test_tenant_isolation(self, switch_tenant, tenant_b):
        KnowledgePointRepository.create(title="租户A的知识点")
        with switch_tenant(tenant_b):
            assert KnowledgePointRepository.count() == 0
            KnowledgePointRepository.create(title="租户B的知识点")
            assert KnowledgePointRepository.count() == 1
        # 回到租户A
        assert KnowledgePointRepository.count() == 1
