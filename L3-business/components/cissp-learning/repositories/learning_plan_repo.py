"""学习计划数据仓库。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from base.base_repository import BaseRepository
from models.learning_plan import LearningPlan, PlanStatus


class LearningPlanRepository(BaseRepository[LearningPlan]):
    model_cls = LearningPlan

    @classmethod
    def list_by_owner(
        cls,
        owner_id: str,
        status: Optional[PlanStatus] = None,
    ) -> List[LearningPlan]:
        filters = {"owner_id": owner_id}
        if status:
            filters["status"] = status
        return cls.filter(**filters)

    @classmethod
    def list_active(cls, owner_id: str) -> List[LearningPlan]:
        """获取进行中的计划。"""
        items = cls.list_by_owner(owner_id, status=PlanStatus.ACTIVE)
        today = date.today()
        return [
            p for p in items
            if p.start_date <= today
            and (p.end_date is None or p.end_date >= today)
        ]

    @classmethod
    def current_plan(cls, owner_id: str, category: str) -> Optional[LearningPlan]:
        """获取某分类的当前进行中的计划。"""
        active = cls.list_active(owner_id)
        for p in active:
            if p.category == category:
                return p
        return None

    @classmethod
    def list_by_status(cls, status: PlanStatus) -> List[LearningPlan]:
        return cls.filter(status=status)

    @classmethod
    def start_plan(cls, plan_id: str) -> LearningPlan:
        """启动计划（DRAFT → ACTIVE）。"""
        plan = cls.get_by_id(plan_id)
        if not plan:
            raise ValueError(f"LearningPlan id={plan_id} not found")
        plan.start()
        return cls.update(plan_id, status=plan.status)

    @classmethod
    def pause_plan(cls, plan_id: str) -> LearningPlan:
        plan = cls.get_by_id(plan_id)
        if not plan:
            raise ValueError(f"LearningPlan id={plan_id} not found")
        plan.pause()
        return cls.update(plan_id, status=plan.status)

    @classmethod
    def resume_plan(cls, plan_id: str) -> LearningPlan:
        plan = cls.get_by_id(plan_id)
        if not plan:
            raise ValueError(f"LearningPlan id={plan_id} not found")
        plan.resume()
        return cls.update(plan_id, status=plan.status)

    @classmethod
    def complete_plan(cls, plan_id: str) -> LearningPlan:
        plan = cls.get_by_id(plan_id)
        if not plan:
            raise ValueError(f"LearningPlan id={plan_id} not found")
        plan.complete()
        return cls.update(plan_id, status=plan.status)

    @classmethod
    def archive_plan(cls, plan_id: str) -> LearningPlan:
        plan = cls.get_by_id(plan_id)
        if not plan:
            raise ValueError(f"LearningPlan id={plan_id} not found")
        plan.archive()
        return cls.update(plan_id, status=plan.status)

    @classmethod
    def cancel_plan(cls, plan_id: str) -> LearningPlan:
        plan = cls.get_by_id(plan_id)
        if not plan:
            raise ValueError(f"LearningPlan id={plan_id} not found")
        plan.cancel()
        return cls.update(plan_id, status=plan.status)
