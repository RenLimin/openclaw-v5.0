"""指标记录数据仓库。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from repository.base import BaseRepository
from .models import MetricsRecord, MetricsType, MetricSource


class MetricsRecordRepository(BaseRepository[MetricsRecord]):
    model_cls = MetricsRecord

    @classmethod
    def list_by_profile(
        cls,
        profile_id: str,
        metrics_type: Optional[MetricsType] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[MetricsRecord]:
        """按 profile + 指标类型 + 时间范围查询。"""
        filters = {"profile_id": profile_id}
        if metrics_type:
            filters["metrics_type"] = metrics_type
        items = cls.filter(limit=limit, **filters)
        if start:
            items = [x for x in items if x.measured_at >= start]
        if end:
            items = [x for x in items if x.measured_at <= end]
        items.sort(key=lambda x: x.measured_at)
        return items

    @classmethod
    def latest(cls, profile_id: str, metrics_type: MetricsType) -> Optional[MetricsRecord]:
        """获取某指标最新一条记录。"""
        items = cls.list_by_profile(
            profile_id, metrics_type=metrics_type, limit=1
        )
        return items[-1] if items else None

    @classmethod
    def list_abnormal(cls, profile_id: str) -> List[MetricsRecord]:
        """列出某用户所有异常指标记录。"""
        return cls.filter(profile_id=profile_id, is_abnormal=True)

    @classmethod
    def list_by_source(cls, profile_id: str, source: MetricSource) -> List[MetricsRecord]:
        return cls.filter(profile_id=profile_id, source=source)
