#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RACI Engine — 职责矩阵引擎
三层模型: Capability → RoleTemplate → Assignment
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
import logging

logger = logging.getLogger(__name__)

@dataclass
class Capability:
    """能力原子 —— 最小粒度的职责单元"""
    id: str
    name: str
    description: str

@dataclass
class RoleTemplate:
    """角色模板 —— 预定义的能力组合"""
    name: str
    description: str
    capabilities: List[str] = field(default_factory=list)  # 能力 ID 列表

@dataclass
class Assignment:
    """职责分配 —— 具体项目中的实际分配"""
    id: str
    project_id: str
    member_id: str
    capability: str
    raci_role: str  # R/A/C/I
    work_item_id: Optional[str] = None
    notes: Optional[str] = None

class RACIEngine:
    """RACI 职责矩阵引擎"""

    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._role_templates: Dict[str, RoleTemplate] = {}
        self._assignments: List[Assignment] = []
        # 预定义 12 个能力原子
        self._register_default_capabilities()
        # 预定义 6 个角色模板
        self._register_default_role_templates()

    def _register_default_capabilities(self) -> None:
        """注册默认的 12 个能力原子"""
        default_caps = [
            Capability(
                id="scope_management",
                name="范围管理",
                description="范围定义、WBS、变更控制"
            ),
            Capability(
                id="schedule_management",
                name="进度计划",
                description="进度计划、关键路径、里程碑"
            ),
            Capability(
                id="risk_management",
                name="风险管理",
                description="风险识别、评估、应对"
            ),
            Capability(
                id="stakeholder_management",
                name="干系人管理",
                description="干系人识别、沟通计划"
            ),
            Capability(
                id="quality_management",
                name="质量管理",
                description="质量标准、验收、回顾"
            ),
            Capability(
                id="deliverable_management",
                name="交付物管理",
                description="交付物定义、跟踪、验收"
            ),
            Capability(
                id="milestone_tracking",
                name="里程碑跟踪",
                description="里程碑设定、监控、报告"
            ),
            Capability(
                id="resource_management",
                name="资源管理",
                description="资源分配、工作量、冲突"
            ),
            Capability(
                id="budget_management",
                name="预算管理",
                description="预算编制、成本跟踪、变更"
            ),
            Capability(
                id="communication_management",
                name="沟通管理",
                description="会议、报告、升级"
            ),
            Capability(
                id="contract_interface",
                name="合同接口",
                description="合同条款、付款节点、索赔"
            ),
            Capability(
                id="sla_tracking",
                name="SLA 跟踪",
                description="SLA 定义、监控、违约预警"
            )
        ]
        for cap in default_caps:
            self.register_capability(cap)

    def _register_default_role_templates(self) -> None:
        """注册默认的 6 个角色模板"""
        default_templates = [
            RoleTemplate(
                name="project-manager",
                description="端到端项目交付",
                capabilities=[
                    "scope_management",
                    "schedule_management",
                    "risk_management",
                    "stakeholder_management",
                    "resource_management",
                    "budget_management",
                    "communication_management",
                    "contract_interface"
                ]
            ),
            RoleTemplate(
                name="delivery-manager",
                description="里程碑/交付物跟踪",
                capabilities=[
                    "schedule_management",
                    "deliverable_management",
                    "milestone_tracking",
                    "sla_tracking"
                ]
            ),
            RoleTemplate(
                name="product-manager",
                description="需求定义、验收",
                capabilities=[
                    "scope_management",
                    "stakeholder_management",
                    "quality_management"
                ]
            ),
            RoleTemplate(
                name="scrum-master",
                description="敏捷过程管理",
                capabilities=[
                    "schedule_management",
                    "quality_management",
                    "communication_management"
                ]
            ),
            RoleTemplate(
                name="qa-engineer",
                description="质量保障",
                capabilities=["quality_management"]
            ),
            RoleTemplate(
                name="delivery-director",
                description="项目组合监控",
                capabilities=[
                    "schedule_management",
                    "resource_management",
                    "budget_management",
                    "communication_management"
                ]
            )
        ]
        for tmpl in default_templates:
            self.register_role_template(tmpl)

    def register_capability(self, capability: Capability) -> None:
        """注册一个新能力"""
        if capability.id in self._capabilities:
            logger.warning(f"Capability {capability.id} already registered, overwriting")
        self._capabilities[capability.id] = capability
        logger.info(f"Registered capability: {capability.id}")

    def register_role_template(self, template: RoleTemplate) -> None:
        """注册一个新角色模板"""
        if template.name in self._role_templates:
            logger.warning(f"Role template {template.name} already registered, overwriting")
        self._role_templates[template.name] = template
        logger.info(f"Registered role template: {template.name}")

    def get_capability(self, cap_id: str) -> Optional[Capability]:
        """获取能力定义"""
        return self._capabilities.get(cap_id)

    def get_role_template(self, name: str) -> Optional[RoleTemplate]:
        """获取角色模板"""
        return self._role_templates.get(name)

    def list_capabilities(self) -> List[Capability]:
        """列出所有已注册能力"""
        return list(self._capabilities.values())

    def list_role_templates(self) -> List[RoleTemplate]:
        """列出所有已注册角色模板"""
        return list(self._role_templates.values())

    def assign(self, assignment: Assignment) -> None:
        """分配一个职责"""
        # 检查能力存在
        if not self.get_capability(assignment.capability):
            logger.warning(f"Assigning unknown capability: {assignment.capability}")
        # 检查 RACI 角色合法
        if assignment.raci_role not in ["R", "A", "C", "I"]:
            raise ValueError(f"Invalid RACI role: {assignment.raci_role}, must be one of R/A/C/I")
        self._assignments.append(assignment)
        logger.info(f"Assigned {assignment.capability} to {assignment.member_id} as {assignment.raci_role}")

    def get_assignments(self, project_id: str, work_item_id: Optional[str] = None) -> List[Assignment]:
        """获取项目/工作项的所有分配"""
        result = []
        for a in self._assignments:
            if a.project_id != project_id:
                continue
            if work_item_id is not None and a.work_item_id != work_item_id:
                continue
            result.append(a)
        return result

    def validate(self, project_id: str) -> Tuple[bool, List[str]]:
        """验证项目分配，返回 (是否有效, 问题列表)"""
        issues = []
        assignments = self.get_assignments(project_id)

        # 规则 1: 每工作项每能力有且仅有 1 个 A
        seen: Set[Tuple[Optional[str], str]] = set()
        for a in assignments:
            key = (a.work_item_id, a.capability)
            if a.raci_role == "A":
                if key in seen:
                    issues.append(f"Conflict: Multiple Accountable (A) for capability {a.capability} on work item {a.work_item_id}")
                seen.add(key)

        # 检查缺失 A
        capability_counts: Dict[Tuple[Optional[str], str], int] = {}
        for a in assignments:
            key = (a.work_item_id, a.capability)
            capability_counts[key] = capability_counts.get(key, 0) + 1
        for key, count in capability_counts.items():
            wi_id, cap = key
            has_a = any(1 for a in assignments if (a.work_item_id == wi_id and a.capability == cap and a.raci_role == "A"))
            if not has_a:
                issues.append(f"Missing Accountable (A) for capability {cap} on work item {wi_id}")

        # 规则 2: 每能力至少有一个 R
        for key, count in capability_counts.items():
            wi_id, cap = key
            has_r = any(1 for a in assignments if (a.work_item_id == wi_id and a.capability == cap and a.raci_role == "R"))
            if not has_r:
                issues.append(f"Missing Responsible (R) for capability {cap} on work item {wi_id}")

        # 规则 3: 同一人不能同时是 R 和 A（建议，但不禁止）
        for wi_id, cap in capability_counts.keys():
            a_assignments = [a for a in assignments if a.work_item_id == wi_id and a.capability == cap and a.raci_role == "A"]
            r_assignments = [a for a in assignments if a.work_item_id == wi_id and a.capability == cap and a.raci_role == "R"]
            for a in a_assignments:
                for r in r_assignments:
                    if a.member_id == r.member_id:
                        issues.append(f"Warning: Same person is both Responsible (R) and Accountable (A) for {cap} on {wi_id}")

        return (len(issues) == 0, issues)

    def check_conflicts(self, project_id: str) -> List[str]:
        """检查冲突，返回问题列表"""
        _, issues = self.validate(project_id)
        return issues
