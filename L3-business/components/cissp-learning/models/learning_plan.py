"""学习计划领域模型。

状态机：草稿(draft) → 进行中(active) → 暂停(paused) / 完成(completed) → 归档(archived)
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from base.base_model import TenantModel


class PlanStatus(str, Enum):
    """学习计划状态。"""
    DRAFT = "draft"           # 草稿
    ACTIVE = "active"         # 进行中
    PAUSED = "paused"         # 暂停
    COMPLETED = "completed"   # 已完成
    ARCHIVED = "archived"     # 已归档
    CANCELLED = "cancelled"   # 已取消


# 允许的状态转移
STATUS_TRANSITIONS: dict[PlanStatus, set[PlanStatus]] = {
    PlanStatus.DRAFT: {PlanStatus.ACTIVE, PlanStatus.CANCELLED},
    PlanStatus.ACTIVE: {PlanStatus.PAUSED, PlanStatus.COMPLETED, PlanStatus.CANCELLED},
    PlanStatus.PAUSED: {PlanStatus.ACTIVE, PlanStatus.CANCELLED},
    PlanStatus.COMPLETED: {PlanStatus.ARCHIVED, PlanStatus.ACTIVE},
    PlanStatus.ARCHIVED: {PlanStatus.ACTIVE},
    PlanStatus.CANCELLED: set(),
}


class PlanObjective(BaseModel):
    """学习目标。"""

    objective_id: str = ""
    title: str
    description: str = ""
    target_date: Optional[date] = None
    achieved: bool = False
    achieved_date: Optional[date] = None
    evidence: str = ""  # 达成依据（证书/考试分数等）


class PlanMilestone(BaseModel):
    """学习里程碑。"""

    milestone_id: str = ""
    title: str
    description: str = ""
    target_date: date
    knowledge_points: List[str] = Field(default_factory=list)  # 关联知识点 ID 列表
    achieved: bool = False
    achieved_date: Optional[date] = None


class LearningPlan(TenantModel):
    """学习计划聚合根。"""

    # ── 基本信息 ────────────────────────────────────────────────
    plan_name: str
    description: str = ""
    category: str = "certification"  # certification / skill / language / general
    certification: Optional[str] = None  # 如 "CISSP", "PMP"

    # ── 周期 ────────────────────────────────────────────────────
    start_date: date
    end_date: Optional[date] = None

    # ── 创建来源 ────────────────────────────────────────────────
    created_by: str = "self"  # self / coach / system / admin
    owner_id: str = ""        # 所属用户 ID

    # ── 状态 ────────────────────────────────────────────────────
    status: PlanStatus = PlanStatus.DRAFT

    # ── 目标 & 里程碑 ───────────────────────────────────────────
    objectives: List[PlanObjective] = Field(default_factory=list)
    milestones: List[PlanMilestone] = Field(default_factory=list)

    # ── 内容关联 ────────────────────────────────────────────────
    knowledge_point_ids: List[str] = Field(default_factory=list)
    quiz_ids: List[str] = Field(default_factory=list)

    # ── 进度跟踪 ────────────────────────────────────────────────
    total_hours_planned: float = 0.0    # 计划总学时
    total_hours_spent: float = 0.0      # 已花费学时

    tags: List[str] = Field(default_factory=list)
    remark: str = ""

    # ── 状态机方法 ──────────────────────────────────────────────

    def can_transition_to(self, new_status: PlanStatus) -> bool:
        """检查是否可以转移到指定状态。"""
        return new_status in STATUS_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status: PlanStatus) -> None:
        """执行状态转移，非法转移抛出 ValueError。"""
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"Invalid status transition: {self.status.value} → {new_status.value}"
            )
        self.status = new_status

    def start(self) -> None:
        """启动计划（草稿 → 进行中）。"""
        self.transition_to(PlanStatus.ACTIVE)

    def pause(self) -> None:
        """暂停计划（进行中 → 暂停）。"""
        self.transition_to(PlanStatus.PAUSED)

    def resume(self) -> None:
        """恢复计划（暂停 → 进行中）。"""
        self.transition_to(PlanStatus.ACTIVE)

    def complete(self) -> None:
        """完成计划（进行中 → 完成）。"""
        self.transition_to(PlanStatus.COMPLETED)

    def archive(self) -> None:
        """归档计划（完成 → 归档）。"""
        self.transition_to(PlanStatus.ARCHIVED)

    def cancel(self) -> None:
        """取消计划。"""
        self.transition_to(PlanStatus.CANCELLED)

    # ── 计算属性 ────────────────────────────────────────────────

    @property
    def days_elapsed(self) -> int:
        """已过天数。"""
        today = date.today()
        if today < self.start_date:
            return 0
        delta = today - self.start_date
        return delta.days + 1

    @property
    def days_remaining(self) -> Optional[int]:
        """剩余天数。"""
        if not self.end_date:
            return None
        today = date.today()
        if today > self.end_date:
            return 0
        return (self.end_date - today).days

    @property
    def progress_percent(self) -> float:
        """按学时计算的进度百分比。"""
        if self.total_hours_planned <= 0:
            return 0.0
        return round(
            min(100.0, self.total_hours_spent / self.total_hours_planned * 100),
            1,
        )

    @property
    def achieved_milestones_count(self) -> int:
        return sum(1 for m in self.milestones if m.achieved)

    @property
    def total_milestones_count(self) -> int:
        return len(self.milestones)

    @property
    def achieved_objectives_count(self) -> int:
        return sum(1 for o in self.objectives if o.achieved)

    @property
    def total_objectives_count(self) -> int:
        return len(self.objectives)

    # ── 操作方法 ────────────────────────────────────────────────

    def add_milestone(self, milestone: PlanMilestone) -> None:
        if not milestone.milestone_id:
            import uuid
            milestone.milestone_id = uuid.uuid4().hex[:8]
        self.milestones.append(milestone)

    def add_objective(self, objective: PlanObjective) -> None:
        if not objective.objective_id:
            import uuid
            objective.objective_id = uuid.uuid4().hex[:8]
        self.objectives.append(objective)

    def add_hours(self, hours: float) -> None:
        """增加已花费学时。"""
        if hours < 0:
            raise ValueError("hours must be non-negative")
        self.total_hours_spent += hours

    def get_milestone(self, milestone_id: str) -> Optional[PlanMilestone]:
        for m in self.milestones:
            if m.milestone_id == milestone_id:
                return m
        return None

    def get_objective(self, objective_id: str) -> Optional[PlanObjective]:
        for o in self.objectives:
            if o.objective_id == objective_id:
                return o
        return None
