"""健康风险评估数据仓库。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from repository.base import BaseRepository
from .models import RiskAssessment, RiskLevel, RiskType


class RiskAssessmentRepository(BaseRepository[RiskAssessment]):
    model_cls = RiskAssessment

    @classmethod
    def list_by_profile(
        cls,
        profile_id: str,
        risk_type: Optional[RiskType] = None,
        limit: int = 100,
    ) -> List[RiskAssessment]:
        filters = {"profile_id": profile_id}
        if risk_type:
            filters["risk_type"] = risk_type
        items = cls.filter(limit=limit, **filters)
        items.sort(key=lambda x: x.assessment_date, reverse=True)
        return items

    @classmethod
    def latest(
        cls, profile_id: str, risk_type: RiskType
    ) -> Optional[RiskAssessment]:
        """获取某类型的最新评估。"""
        items = cls.list_by_profile(profile_id, risk_type=risk_type, limit=1)
        return items[0] if items else None

    @classmethod
    def list_by_level(
        cls, profile_id: str, level: RiskLevel
    ) -> List[RiskAssessment]:
        return cls.filter(profile_id=profile_id, risk_level=level)

    @classmethod
    def list_high_risk(cls, profile_id: str) -> List[RiskAssessment]:
        """获取所有高风险及以上的评估。"""
        items = cls.filter(profile_id=profile_id)
        high_levels = {RiskLevel.HIGH, RiskLevel.VERY_HIGH}
        return [r for r in items if r.risk_level in high_levels]

    @classmethod
    def history_trend(
        cls, profile_id: str, risk_type: RiskType, limit: int = 10
    ) -> List[RiskAssessment]:
        """获取某类型的历史评估（按时间正序），用于趋势分析。"""
        items = cls.list_by_profile(profile_id, risk_type=risk_type, limit=limit)
        items.sort(key=lambda x: x.assessment_date)
        return items
