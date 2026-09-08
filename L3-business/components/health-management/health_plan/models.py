"""健康计划领域模型。

健康计划是基于风险评估/体检结果制定的干预方案，
包含多个任务（饮食/运动/用药/复查等）和里程碑。
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from repository.base import TenantModel


class PlanType(str, Enum):
    """计划类型。"""
    WEIGHT_LOSS = "weight_loss"           # 减重
    BLOOD_PRESSURE_CONTROL = "bp_control"  # 血压控制
    BLOOD_SUGAR_CONTROL = "bs_control"     # 血糖控制
    CHOLESTEROL_CONTROL = "lipid_control"  # 血脂控制
    FITNESS_IMPROVEMENT = "fitness"        # 体能提升
    SLEEP_IMPROVEMENT = "sleep_improvement"  # 睡眠改善
    STRESS_MANAGEMENT = "stress"           # 压力管理
    POST_SURGERY_RECOVERY = "post_surgery"  # 术后恢复
    CHRONIC_DISEASE_MANAGEMENT = "chronic"  # 慢病管理
    PREVENTIVE_CARE = "preventive"         # 预防保健
    CUSTOM = "custom"                      # 自定义


class PlanStatus(str, Enum):
    DRAFT = "draft"           # 草稿
    ACTIVE = "active"         # 进行中
    PAUSED = "paused"         # 暂停
    COMPLETED = "completed"   # 已完成
    CANCELLED = "cancelled"   # 已取消
    EXPIRED = "expired"       # 已过期


class TaskStatus(str, Enum):
    PENDING = "pending"       # 待开始
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"   # 已完成
    SKIPPED = "skipped"       # 已跳过
    OVERDUE = "overdue"       # 已逾期
    FAILED = "failed"         # 未达成


class PlanTask(BaseModel):
    """计划中的单个任务。"""

    task_id: str = ""
    title: str
    category: str = ""            # 饮食/运动/用药/体检/生活方式
    description: str = ""
    frequency: str = "daily"      # daily / weekly / monthly / one_time
    target_value: Optional[float] = None
    target_unit: Optional[str] = None
    priority: int = 3             # 1-5

    start_date: Optional[date] = None
    end_date: Optional[date] = None

    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0         # 0-100 完成度
    completion_date: Optional[date] = None

    related_risk_type: Optional[str] = None  # 关联的风险类型
    references: List[str] = Field(default_factory=list)
    notes: str = ""


class PlanMilestone(BaseModel):
    """计划里程碑。"""

    milestone_id: str = ""
    title: str
    target_date: date
    description: str = ""
    achieved: bool = False
    achieved_date: Optional[date] = None
    evidence: str = ""             # 达成依据（如体重/血压值）


class HealthPlan(TenantModel):
    """健康计划主记录。"""

    profile_id: str
    plan_name: str
    plan_type: PlanType = PlanType.CUSTOM

    # ── 周期 ────────────────────────────────────────────────────
    start_date: date
    end_date: Optional[date] = None
    duration_days: Optional[int] = None

    # ── 来源 ────────────────────────────────────────────────────
    source_risk_assessment_id: Optional[str] = None
    source_checkup_id: Optional[str] = None
    created_by: str = "system"      # system / doctor / self / coach
    doctor_name: Optional[str] = None

    # ── 目标 ────────────────────────────────────────────────────
    overall_goal: str = ""
    goals: List[str] = Field(default_factory=list)

    # ── 状态 ────────────────────────────────────────────────────
    status: PlanStatus = PlanStatus.DRAFT

    # ── 任务 & 里程碑 ───────────────────────────────────────────
    tasks: List[PlanTask] = Field(default_factory=list)
    milestones: List[PlanMilestone] = Field(default_factory=list)

    # ── 效果跟踪 ────────────────────────────────────────────────
    baseline_metrics: dict = Field(default_factory=dict)  # 基线指标
    target_metrics: dict = Field(default_factory=dict)    # 目标指标
    current_metrics: dict = Field(default_factory=dict)   # 当前指标

    tags: List[str] = Field(default_factory=list)
    notes: str = ""

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
    def overall_progress(self) -> float:
        """整体进度（按任务完成度均值计算）。"""
        if not self.tasks:
            return 0.0
        return round(sum(t.progress for t in self.tasks) / len(self.tasks), 1)

    @property
    def completed_tasks_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == TaskStatus.COMPLETED)

    @property
    def total_tasks_count(self) -> int:
        return len(self.tasks)

    @property
    def achieved_milestones_count(self) -> int:
        return sum(1 for m in self.milestones if m.achieved)

    def get_task(self, task_id: str) -> Optional[PlanTask]:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def add_task(self, task: PlanTask) -> None:
        if not task.task_id:
            import uuid
            task.task_id = uuid.uuid4().hex[:8]
        self.tasks.append(task)

    def update_task_progress(self, task_id: str, progress: float) -> bool:
        task = self.get_task(task_id)
        if not task:
            return False
        task.progress = max(0.0, min(100.0, progress))
        if progress >= 100.0:
            task.status = TaskStatus.COMPLETED
            task.completion_date = date.today()
        elif progress > 0:
            task.status = TaskStatus.IN_PROGRESS
        return True
