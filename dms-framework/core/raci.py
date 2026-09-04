"""
core/raci.py — RACI 引擎
三层模型：能力原子(Capability Atoms) → 角色模板(Role Templates) → 项目级分配(Assignment)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 能力原子 — 12 个最小交付能力单元
# ---------------------------------------------------------------------------

CAPABILITY_ATOMS: list[str] = [
    "scope_management",          # 范围管理
    "schedule_management",       # 进度管理
    "risk_management",           # 风险管理
    "stakeholder_management",    # 干系人管理
    "quality_management",        # 质量管理
    "deliverable_management",    # 交付物管理
    "milestone_tracking",        # 里程碑追踪
    "resource_management",       # 资源管理
    "budget_management",         # 预算管理
    "communication_management",  # 沟通管理
    "contract_interface",        # 合同接口
    "sla_tracking",              # SLA 追踪
]

# 能力原子的中文名，用于展示
CAPABILITY_LABELS: dict[str, str] = {
    "scope_management": "范围管理",
    "schedule_management": "进度管理",
    "risk_management": "风险管理",
    "stakeholder_management": "干系人管理",
    "quality_management": "质量管理",
    "deliverable_management": "交付物管理",
    "milestone_tracking": "里程碑追踪",
    "resource_management": "资源管理",
    "budget_management": "预算管理",
    "communication_management": "沟通管理",
    "contract_interface": "合同接口",
    "sla_tracking": "SLA 追踪",
}


# ---------------------------------------------------------------------------
# 角色模板 — 6 个标准角色及各自可承担的能力
# ---------------------------------------------------------------------------

ROLE_TEMPLATES: dict[str, list[str]] = {
    "project_manager": [
        "scope_management", "schedule_management", "risk_management",
        "stakeholder_management", "resource_management", "budget_management",
        "communication_management", "milestone_tracking",
    ],
    "delivery_manager": [
        "deliverable_management", "schedule_management", "quality_management",
        "resource_management", "milestone_tracking", "sla_tracking",
        "risk_management", "communication_management",
    ],
    "product_manager": [
        "scope_management", "stakeholder_management", "deliverable_management",
        "quality_management", "communication_management",
    ],
    "scrum_master": [
        "schedule_management", "resource_management", "communication_management",
        "risk_management", "milestone_tracking",
    ],
    "qa_engineer": [
        "quality_management", "deliverable_management", "sla_tracking",
        "risk_management",
    ],
    "delivery_director": [
        "stakeholder_management", "budget_management", "contract_interface",
        "sla_tracking", "risk_management", "quality_management",
    ],
}

# 角色中文名
ROLE_LABELS: dict[str, str] = {
    "project_manager": "项目经理",
    "delivery_manager": "交付经理",
    "product_manager": "产品经理",
    "scrum_master": "Scrum Master",
    "qa_engineer": "QA 工程师",
    "delivery_director": "交付总监",
}

# RACI 角色定义
RACI_ROLES = {"R", "A", "C", "I"}
RACI_LABELS = {
    "R": "Responsible (执行)",
    "A": "Accountable (负责)",
    "C": "Consulted (咨询)",
    "I": "Informed (知情)",
}


# ---------------------------------------------------------------------------
# Assignment — 分配记录
# ---------------------------------------------------------------------------

@dataclass
class Assignment:
    """RACI 分配记录。

    project_id: 项目 ID（必填）
    work_item_id: 工作项 ID，None 表示项目级分配
    member_id: 成员 ID
    capability: 能力原子名（必须在 CAPABILITY_ATOMS 中）
    raci_role: R | A | C | I
    role_template: 可选，该成员在项目中的角色模板名
    """

    project_id: str
    member_id: str
    capability: str
    raci_role: str
    work_item_id: str | None = None
    role_template: str | None = None
    tenant_id: str = "system"

    def __post_init__(self) -> None:
        if self.capability not in CAPABILITY_ATOMS:
            raise ValueError(f"Invalid capability: {self.capability}")
        if self.raci_role not in RACI_ROLES:
            raise ValueError(f"Invalid raci_role: {self.raci_role}, must be one of {RACI_ROLES}")
        if self.role_template and self.role_template not in ROLE_TEMPLATES:
            raise ValueError(f"Invalid role_template: {self.role_template}")

    @property
    def key(self) -> tuple[str, str | None, str, str, str]:
        return (self.project_id, self.work_item_id, self.member_id, self.capability, self.raci_role)


# ---------------------------------------------------------------------------
# 冲突 / 缺口
# ---------------------------------------------------------------------------

@dataclass
class Conflict:
    """RACI 冲突。"""

    type: str  # "multiple_responsible" | "no_accountable" | "raci_mismatch"
    project_id: str
    work_item_id: str | None
    capability: str
    description: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Gap:
    """RACI 覆盖缺口。"""

    project_id: str
    work_item_id: str | None
    capability: str
    missing_roles: list[str]  # 缺少哪些 RACI 角色
    description: str


# ---------------------------------------------------------------------------
# RACIEngine — RACI 引擎
# ---------------------------------------------------------------------------

class RACIEngine:
    """RACI 引擎：分配管理 + 冲突检测 + 覆盖验证 + 矩阵生成。

    规则：
    1. 每个 (项目, 工作项, 能力) 组合必须有且仅有一个 A (Accountable)
    2. 每个 (项目, 工作项, 能力) 组合至少有一个 R (Responsible)
    3. 一个成员在同一能力上可以同时是 R 和 C 或 I，但不能既是 R 又是 A
    """

    def __init__(self) -> None:
        self._assignments: dict[tuple, Assignment] = {}

    # -- 增删查 ------------------------------------------------------------

    def assign(self, assignment: Assignment) -> None:
        """添加或更新分配。按 key 去重。"""
        self._assignments[assignment.key] = assignment

    def unassign(self, assignment: Assignment) -> bool:
        return self._assignments.pop(assignment.key, None) is not None

    def get_assignments(
        self,
        project_id: str,
        work_item_id: str | None = None,
        capability: str | None = None,
        member_id: str | None = None,
        raci_role: str | None = None,
    ) -> list[Assignment]:
        """多维度查询分配。"""
        result = [a for a in self._assignments.values() if a.project_id == project_id]
        if work_item_id is not None:
            result = [a for a in result if a.work_item_id == work_item_id]
        if capability is not None:
            result = [a for a in result if a.capability == capability]
        if member_id is not None:
            result = [a for a in result if a.member_id == member_id]
        if raci_role is not None:
            result = [a for a in result if a.raci_role == raci_role]
        return result

    def list_all(self) -> list[Assignment]:
        return list(self._assignments.values())

    # -- 冲突检测 ----------------------------------------------------------

    def check_conflicts(self, project_id: str) -> list[Conflict]:
        """检查项目中的 RACI 冲突。

        检查项：
        1. 同一 (work_item, capability) 有多个 A
        2. 同一成员在同一 (work_item, capability) 既是 R 又是 A
        3. 同一 (work_item, capability) 没有 A
        """
        conflicts: list[Conflict] = []
        assignments = self.get_assignments(project_id)

        # 按 (work_item, capability) 分组
        groups: dict[tuple[str | None, str], list[Assignment]] = {}
        for a in assignments:
            key = (a.work_item_id, a.capability)
            groups.setdefault(key, []).append(a)

        for (wi_id, cap), group in groups.items():
            a_roles = [a for a in group if a.raci_role == "A"]
            r_roles = [a for a in group if a.raci_role == "R"]

            # 多个 A
            if len(a_roles) > 1:
                conflicts.append(Conflict(
                    type="multiple_accountable",
                    project_id=project_id,
                    work_item_id=wi_id,
                    capability=cap,
                    description=f"有 {len(a_roles)} 个 Accountable，只能有 1 个",
                    details={"members": [a.member_id for a in a_roles]},
                ))

            # 没有 A
            if len(a_roles) == 0:
                conflicts.append(Conflict(
                    type="no_accountable",
                    project_id=project_id,
                    work_item_id=wi_id,
                    capability=cap,
                    description="没有 Accountable，必须指定 1 个",
                    details={},
                ))

            # 同一人既是 R 又是 A
            r_members = {a.member_id for a in r_roles}
            a_members = {a.member_id for a in a_roles}
            overlap = r_members & a_members
            if overlap:
                conflicts.append(Conflict(
                    type="raci_mismatch",
                    project_id=project_id,
                    work_item_id=wi_id,
                    capability=cap,
                    description=f"成员 {overlap} 同时是 R 和 A，违反 R≠A 原则",
                    details={"members": list(overlap)},
                ))

        return conflicts

    # -- 覆盖验证 ----------------------------------------------------------

    def validate_coverage(
        self,
        project_id: str,
        work_item_id: str | None = None,
        required_capabilities: list[str] | None = None,
    ) -> list[Gap]:
        """验证 RACI 覆盖：每个 (work_item, capability) 至少有 R 和 A。"""
        caps = required_capabilities or CAPABILITY_ATOMS
        gaps: list[Gap] = []

        # 收集所有 work_item_id
        assignments = self.get_assignments(project_id, work_item_id=work_item_id)
        work_items = {a.work_item_id for a in assignments}
        if work_item_id is not None:
            work_items = {work_item_id}
        if not work_items:
            work_items = {None}  # 项目级

        for wi in work_items:
            for cap in caps:
                group = self.get_assignments(project_id, work_item_id=wi, capability=cap)
                has_r = any(a.raci_role == "R" for a in group)
                has_a = any(a.raci_role == "A" for a in group)
                missing = []
                if not has_r:
                    missing.append("R")
                if not has_a:
                    missing.append("A")
                if missing:
                    gaps.append(Gap(
                        project_id=project_id,
                        work_item_id=wi,
                        capability=cap,
                        missing_roles=missing,
                        description=f"缺少 {', '.join(missing)} 角色",
                    ))
        return gaps

    # -- 矩阵生成 ----------------------------------------------------------

    def get_responsibility_matrix(self, project_id: str) -> dict[str, Any]:
        """生成完整的 RACI 矩阵。

        返回结构:
        {
            "project_id": "...",
            "work_items": {
                "<work_item_id or 'project'>": {
                    "<capability>": {
                        "R": ["member1", ...],
                        "A": ["member2", ...],
                        "C": [...],
                        "I": [...],
                    }
                }
            }
        }
        """
        assignments = self.get_assignments(project_id)
        matrix: dict[str, dict[str, dict[str, list[str]]]] = {}

        for a in assignments:
            wi_key = a.work_item_id or "project"
            if wi_key not in matrix:
                matrix[wi_key] = {}
            if a.capability not in matrix[wi_key]:
                matrix[wi_key][a.capability] = {"R": [], "A": [], "C": [], "I": []}
            matrix[wi_key][a.capability][a.raci_role].append(a.member_id)

        return {
            "project_id": project_id,
            "work_items": matrix,
        }

    # -- 角色模板辅助 ------------------------------------------------------

    def assign_by_role(
        self,
        project_id: str,
        member_id: str,
        role_name: str,
        raci_role: str = "R",
        work_item_id: str | None = None,
    ) -> list[Assignment]:
        """按角色模板批量分配：该角色下所有能力都分配给该成员。"""
        if role_name not in ROLE_TEMPLATES:
            raise ValueError(f"Unknown role template: {role_name}")
        created: list[Assignment] = []
        for cap in ROLE_TEMPLATES[role_name]:
            a = Assignment(
                project_id=project_id,
                member_id=member_id,
                capability=cap,
                raci_role=raci_role,
                work_item_id=work_item_id,
                role_template=role_name,
            )
            self.assign(a)
            created.append(a)
        return created
