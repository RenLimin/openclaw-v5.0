"""健康档案数据仓库。"""

from __future__ import annotations

from typing import List, Optional

from repository.base import BaseRepository
from .models import HealthProfile, Gender


class HealthProfileRepository(BaseRepository[HealthProfile]):
    model_cls = HealthProfile

    @classmethod
    def get_by_profile_id(cls, profile_id: str) -> Optional[HealthProfile]:
        results = cls.filter(profile_id=profile_id, limit=1)
        return results[0] if results else None

    @classmethod
    def search_by_name(cls, name_keyword: str) -> List[HealthProfile]:
        items = cls.list(limit=1000)
        return [
            p for p in items
            if name_keyword.lower() in p.name.lower()
        ]

    @classmethod
    def list_by_gender(cls, gender: Gender) -> List[HealthProfile]:
        return cls.filter(gender=gender)

    @classmethod
    def list_active(cls) -> List[HealthProfile]:
        return cls.filter(is_active=True)
