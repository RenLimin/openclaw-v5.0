# -*- coding: utf-8 -*-
"""其他数据模型测试：ProjectMember, Stakeholder, ResponsibilityAssignment, ChangeLog。"""

from project_member.project_member_model import ProjectMember
from stakeholder.stakeholder_model import Stakeholder
from responsibility.assignment_model import ResponsibilityAssignment
from change_log.change_log_model import ChangeLog


class TestProjectMember:
    """ProjectMember 模型测试。"""

    def test_basic_fields(self):
        m = ProjectMember(
            project_id="p1",
            member_id="u1",
            member_name="张三",
            role_template="project-manager",
        )
        assert m.project_id == "p1"
        assert m.member_id == "u1"
        assert m.member_name == "张三"
        assert m.role_template == "project-manager"

    def test_dict_inherits_base(self):
        m = ProjectMember(project_id="p1", member_id="u1", member_name="李四")
        d = m.dict()
        assert d["project_id"] == "p1"
        assert d["member_name"] == "李四"
        assert "id" in d


class TestStakeholder:
    """Stakeholder 模型测试。"""

    def test_basic_fields(self):
        s = Stakeholder(
            project_id="p1",
            name="王五",
            role="业务负责人",
            org="产品部",
            influence="high",
            interest="high",
        )
        assert s.project_id == "p1"
        assert s.name == "王五"
        assert s.influence == "high"
        assert s.interest == "high"

    def test_default_influence_interest(self):
        s = Stakeholder(project_id="p1", name="默认")
        assert s.influence == "medium"
        assert s.interest == "medium"

    def test_dict_serialization(self):
        s = Stakeholder(project_id="p1", name="赵六", notes="重要干系人")
        d = s.dict()
        assert d["name"] == "赵六"
        assert d["notes"] == "重要干系人"


class TestResponsibilityAssignment:
    """ResponsibilityAssignment 模型测试。"""

    def test_basic_fields(self):
        ra = ResponsibilityAssignment(
            project_id="p1",
            member_id="u1",
            capability="scope_management",
            raci_role="A",
            work_item_id="wi-1",
        )
        assert ra.project_id == "p1"
        assert ra.capability == "scope_management"
        assert ra.raci_role == "A"
        assert ra.work_item_id == "wi-1"

    def test_project_level_assignment(self):
        """项目级分配时 work_item_id 可为空。"""
        ra = ResponsibilityAssignment(
            project_id="p1",
            member_id="u1",
            capability="budget_management",
            raci_role="R",
        )
        assert ra.work_item_id is None


class TestChangeLog:
    """ChangeLog 模型测试。"""

    def test_basic_fields(self):
        cl = ChangeLog(
            entity_type="Project",
            entity_id="p1",
            action="status_change",
            field_name="status",
            old_value="initiated",
            new_value="active",
            actor_id="u1",
        )
        assert cl.entity_type == "Project"
        assert cl.action == "status_change"
        assert cl.old_value == "initiated"
        assert cl.new_value == "active"

    def test_dict_serialization(self):
        cl = ChangeLog(entity_type="WorkItem", entity_id="wi-1", action="create")
        d = cl.dict()
        assert d["entity_type"] == "WorkItem"
        assert d["action"] == "create"
        assert "id" in d
