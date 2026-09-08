"""用药记录数据仓库。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from repository.base import BaseRepository
from .models import MedicationRecord, MedicationStatus, MedicationFrequency


class MedicationRecordRepository(BaseRepository[MedicationRecord]):
    model_cls = MedicationRecord

    @classmethod
    def list_by_profile(
        cls,
        profile_id: str,
        status: Optional[MedicationStatus] = None,
    ) -> List[MedicationRecord]:
        filters = {"profile_id": profile_id}
        if status:
            filters["status"] = status
        return cls.filter(**filters)

    @classmethod
    def list_active(cls, profile_id: str) -> List[MedicationRecord]:
        """获取当前正在进行的用药记录。"""
        items = cls.list_by_profile(profile_id, status=MedicationStatus.ACTIVE)
        today = date.today()
        return [
            m for m in items
            if m.start_date <= today and (m.end_date is None or m.end_date >= today)
        ]

    @classmethod
    def list_by_category(cls, profile_id: str, category: str) -> List[MedicationRecord]:
        return cls.filter(profile_id=profile_id, drug_category=category)

    @classmethod
    def find_by_prescription_no(cls, prescription_no: str) -> Optional[MedicationRecord]:
        results = cls.filter(prescription_no=prescription_no, limit=1)
        return results[0] if results else None

    @classmethod
    def mark_discontinued(cls, item_id: str, reason: str = "") -> MedicationRecord:
        """标记为已停药。"""
        updates = {"status": MedicationStatus.DISCONTINUED}
        if reason:
            updates["notes"] = reason
        return cls.update(item_id, **updates)
