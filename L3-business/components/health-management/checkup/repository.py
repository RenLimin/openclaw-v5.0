"""体检记录数据仓库。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from repository.base import BaseRepository
from .models import CheckupRecord, CheckupStatus


class CheckupRecordRepository(BaseRepository[CheckupRecord]):
    model_cls = CheckupRecord

    @classmethod
    def list_by_profile(
        cls,
        profile_id: str,
        status: Optional[CheckupStatus] = None,
    ) -> List[CheckupRecord]:
        filters = {"profile_id": profile_id}
        if status:
            filters["status"] = status
        items = cls.filter(**filters)
        items.sort(key=lambda x: x.checkup_date, reverse=True)
        return items

    @classmethod
    def latest(cls, profile_id: str) -> Optional[CheckupRecord]:
        """获取最近一次已完成的体检。"""
        items = cls.list_by_profile(profile_id, status=CheckupStatus.COMPLETED)
        if not items:
            items = cls.list_by_profile(profile_id, status=CheckupStatus.REPORT_READY)
        return items[0] if items else None

    @classmethod
    def list_by_year(cls, profile_id: str, year: int) -> List[CheckupRecord]:
        items = cls.list_by_profile(profile_id)
        return [x for x in items if x.checkup_date.year == year]

    @classmethod
    def list_by_hospital(cls, profile_id: str, hospital: str) -> List[CheckupRecord]:
        return cls.filter(profile_id=profile_id, hospital=hospital)

    @classmethod
    def find_abnormal_history(
        cls, profile_id: str, item_code: str
    ) -> List[CheckupRecord]:
        """查找某指标异常的历史体检记录。"""
        items = cls.list_by_profile(profile_id)
        return [
            r for r in items
            if any(i.item_code == item_code and i.is_abnormal for i in r.items)
        ]
