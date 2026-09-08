"""健康计划数据仓库。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from repository.base import BaseRepository
from .models import HealthPlan, PlanStatus, PlanType


class HealthPlanRepository(BaseRepository[HealthPlan]):
    model_cls = HealthPlan

    @classmethod
    def list_by_profile(
        cls,
        profile_id: str,
        status: Optional[PlanStatus] = None,
        plan_type: Optional[PlanType] = None,
    ) -> List[HealthPlan]:
        filters = {"profile_id": profile_id}
        if status:
            filters["status"] = status
        if plan_type:
            filters["plan_type"] = plan_type
        items = cls.filter(**filters)
        items.sort(key=lambda x: x.start_date, reverse=True)
        return items

    @classmethod
    def list_active(cls, profile_id: str) -> List[HealthPlan]:
        """获取进行中的计划。"""
        items = cls.list_by_profile(profile_id, status=PlanStatus.ACTIVE)
        today = date.today()
        return [
            p for p in items
            if p.start_date <= today and (p.end_date is None or p.end_date >= today)
        ]

    @classmethod
    def current_plan(cls, profile_id: str, plan_type: PlanType) -> Optional[HealthPlan]:
        """获取某类型的当前进行中的计划。"""
        active = cls.list_active(profile_id)
        for p in active:
            if p.plan_type == plan_type:
                return p
        return None

    @classmethod
    def list_by_type(cls, profile_id: str, plan_type: PlanType) -> List[HealthPlan]:
        return cls.list_by_profile(profile_id, plan_type=plan_type)

    @classmethod
    def start_plan(cls, plan_id: str) -> HealthPlan:
        """启动计划。"""
        return cls.update(plan_id, status=PlanStatus.ACTIVE)

    @classmethod
    def complete_plan(cls, plan_id: str) -> HealthPlan:
        """标记计划完成。"""
        return cls.update(plan_id, status=PlanStatus.COMPLETED)

    @classmethod
    def pause_plan(cls, plan_id: str) -> HealthPlan:
        """暂停计划。"""
        return cls.update(plan_id, status=PlanStatus.PAUSED)
