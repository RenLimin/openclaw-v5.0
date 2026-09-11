# -*- coding: utf-8 -*-
"""RACI 职责矩阵引擎测试。"""

import pytest
from raci import RACIEngine, Capability, RoleTemplate, Assignment


class TestRACIEngineDefaults:
    """RACI 引擎默认数据测试。"""

    def setup_method(self):
        self.engine = RACIEngine()

    def test_default_capabilities_count(self):
        """应预注册 12 个能力原子。"""
        assert len(self.engine.list_capabilities()) == 12

    def test_default_role_templates_count(self):
        """应预注册 6 个角色模板。"""
        assert len(self.engine.list_role_templates()) == 6

    def test_known_capability_ids(self):
        """应包含核心能力 ID。"""
        for cap_id in [
            "scope_management", "schedule_management", "risk_management",
            "budget_management", "quality_management", "sla_tracking",
        ]:
            assert self.engine.get_capability(cap_id) is not None

    def test_known_role_template_names(self):
        """应包含核心角色模板名称。"""
        for name in [
            "project-manager", "delivery-manager", "product-manager",
            "scrum-master", "qa-engineer", "delivery-director",
        ]:
            assert self.engine.get_role_template(name) is not None

    def test_capability_fields(self):
        """能力原子应包含完整字段。"""
        cap = self.engine.get_capability("scope_management")
        assert cap.name == "范围管理"
        assert cap.description

    def test_role_template_capabilities_reference_valid(self):
        """角色模板引用的能力 ID 应存在于能力注册表中。"""
        for tmpl in self.engine.list_role_templates():
            for cap_id in tmpl.capabilities:
                assert self.engine.get_capability(cap_id) is not None


class TestRACIEngineCapabilityManagement:
    """能力注册管理测试。"""

    def setup_method(self):
        self.engine = RACIEngine()

    def test_register_new_capability(self):
        """应能注册新能力。"""
        new_cap = Capability(id="custom_cap", name="自定义能力", description="测试")
        self.engine.register_capability(new_cap)
        assert self.engine.get_capability("custom_cap") is not None
        assert self.engine.get_capability("custom_cap").name == "自定义能力"

    def test_register_overwrites_existing(self):
        """重复注册应覆盖。"""
        cap = Capability(id="scope_management", name="新名称", description="新描述")
        self.engine.register_capability(cap)
        assert self.engine.get_capability("scope_management").name == "新名称"

    def test_register_role_template(self):
        """应能注册新角色模板。"""
        tmpl = RoleTemplate(
            name="custom-role",
            description="自定义角色",
            capabilities=["scope_management"],
        )
        self.engine.register_role_template(tmpl)
        assert self.engine.get_role_template("custom-role") is not None


class TestRACIEngineAssignment:
    """职责分配测试。"""

    def setup_method(self):
        self.engine = RACIEngine()

    def test_assign_valid_raci_roles(self):
        """应支持 R/A/C/I 四种角色。"""
        for role in ["R", "A", "C", "I"]:
            a = Assignment(
                id=f"a-{role}",
                project_id="p1",
                member_id="u1",
                capability="scope_management",
                raci_role=role,
            )
            self.engine.assign(a)
        assert len(self.engine.get_assignments("p1")) == 4

    def test_assign_invalid_raci_role_raises(self):
        """非法 RACI 角色应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Invalid RACI role"):
            a = Assignment(
                id="bad",
                project_id="p1",
                member_id="u1",
                capability="scope_management",
                raci_role="X",
            )
            self.engine.assign(a)

    def test_get_assignments_by_project(self):
        """应按项目 ID 过滤分配。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="A",
        ))
        self.engine.assign(Assignment(
            id="a2", project_id="p2", member_id="u2",
            capability="scope_management", raci_role="A",
        ))
        assert len(self.engine.get_assignments("p1")) == 1
        assert len(self.engine.get_assignments("p2")) == 1

    def test_get_assignments_by_work_item(self):
        """应按工作项 ID 过滤分配。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="A",
            work_item_id="wi-1",
        ))
        self.engine.assign(Assignment(
            id="a2", project_id="p1", member_id="u2",
            capability="scope_management", raci_role="A",
            work_item_id="wi-2",
        ))
        assert len(self.engine.get_assignments("p1", work_item_id="wi-1")) == 1

    def test_project_level_assignment_no_work_item(self):
        """项目级分配（无 work_item_id）应被检索到。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="budget_management", raci_role="A",
        ))
        # 不带 work_item_id 过滤应返回
        result = self.engine.get_assignments("p1")
        assert len(result) == 1
        # 带 work_item_id 过滤应不返回
        result = self.engine.get_assignments("p1", work_item_id="wi-1")
        assert len(result) == 0


class TestRACIEngineValidation:
    """RACI 验证规则测试。"""

    def setup_method(self):
        self.engine = RACIEngine()

    def test_valid_assignment_passes(self):
        """合规的分配应通过验证。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="A",
        ))
        self.engine.assign(Assignment(
            id="a2", project_id="p1", member_id="u2",
            capability="scope_management", raci_role="R",
        ))
        valid, issues = self.engine.validate("p1")
        assert valid is True
        assert len(issues) == 0

    def test_missing_a_detected(self):
        """缺少 A 角色时应被检测到。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="R",
        ))
        valid, issues = self.engine.validate("p1")
        assert valid is False
        assert any("Missing Accountable" in i for i in issues)

    def test_missing_r_detected(self):
        """缺少 R 角色时应被检测到。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="A",
        ))
        valid, issues = self.engine.validate("p1")
        assert valid is False
        assert any("Missing Responsible" in i for i in issues)

    def test_multiple_a_conflict(self):
        """同一能力多个 A 应被检测为冲突。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="A",
        ))
        self.engine.assign(Assignment(
            id="a2", project_id="p1", member_id="u2",
            capability="scope_management", raci_role="A",
        ))
        valid, issues = self.engine.validate("p1")
        assert valid is False
        assert any("Multiple Accountable" in i for i in issues)

    def test_same_person_r_and_a_warning(self):
        """同一人同时是 R 和 A 应产生警告。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="A",
        ))
        self.engine.assign(Assignment(
            id="a2", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="R",
        ))
        valid, issues = self.engine.validate("p1")
        assert any("Same person" in i for i in issues)

    def test_check_conflicts_alias(self):
        """check_conflicts 应返回问题列表。"""
        self.engine.assign(Assignment(
            id="a1", project_id="p1", member_id="u1",
            capability="scope_management", raci_role="R",
        ))
        conflicts = self.engine.check_conflicts("p1")
        assert len(conflicts) > 0

    def test_empty_project_validation(self):
        """空项目（无分配）应通过验证。"""
        valid, issues = self.engine.validate("empty-project")
        assert valid is True
