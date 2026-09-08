"""知识点数据仓库。"""

from __future__ import annotations

from typing import List, Optional

from base.base_repository import BaseRepository
from models.knowledge_point import KnowledgePoint, CISSPDomain, KnowledgeLevel


class KnowledgePointRepository(BaseRepository[KnowledgePoint]):
    model_cls = KnowledgePoint

    @classmethod
    def list_by_domain(cls, domain: CISSPDomain) -> List[KnowledgePoint]:
        return cls.filter(domain=domain)

    @classmethod
    def list_roots(cls) -> List[KnowledgePoint]:
        """获取所有根节点（depth=0 或 parent_id=None）。"""
        return cls.filter(depth=0)

    @classmethod
    def list_children(cls, parent_id: str) -> List[KnowledgePoint]:
        """获取直接子节点。"""
        return cls.filter(parent_id=parent_id)

    @classmethod
    def list_by_level(cls, level: KnowledgeLevel) -> List[KnowledgePoint]:
        return cls.filter(level=level)

    @classmethod
    def search_by_title(cls, keyword: str) -> List[KnowledgePoint]:
        """按标题关键字搜索。"""
        items = cls.list(limit=1000)
        keyword_lower = keyword.lower()
        return [
            kp for kp in items
            if keyword_lower in kp.title.lower()
        ]

    @classmethod
    def get_children_recursive(cls, parent_id: str) -> List[KnowledgePoint]:
        """递归获取所有后代节点。"""
        all_items = cls.list(limit=10000)
        parent = cls.get_by_id(parent_id)
        if not parent:
            return []
        prefix = parent.path + "/" if parent.path else ""
        return [
            kp for kp in all_items
            if kp.path and (
                kp.path == parent.path + "/" + kp.title
                or kp.path.startswith(prefix)
            )
        ]

    @classmethod
    def list_by_path_prefix(cls, path_prefix: str) -> List[KnowledgePoint]:
        """按路径前缀获取所有后代。"""
        all_items = cls.list(limit=10000)
        return [
            kp for kp in all_items
            if kp.path and kp.path.startswith(path_prefix)
        ]
