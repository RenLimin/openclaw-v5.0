"""笔记数据仓库。"""

from __future__ import annotations

from typing import List, Optional

from base.base_repository import BaseRepository
from models.note import Note


class NoteRepository(BaseRepository[Note]):
    model_cls = Note

    @classmethod
    def list_by_owner(cls, owner_id: str, only_published: bool = False) -> List[Note]:
        filters = {"owner_id": owner_id}
        if only_published:
            filters["is_draft"] = False
        return cls.filter(**filters)

    @classmethod
    def list_by_knowledge_point(
        cls, knowledge_point_id: str, only_published: bool = False
    ) -> List[Note]:
        filters = {"knowledge_point_id": knowledge_point_id}
        if only_published:
            filters["is_draft"] = False
        return cls.filter(**filters)

    @classmethod
    def list_by_plan(cls, plan_id: str) -> List[Note]:
        return cls.filter(plan_id=plan_id)

    @classmethod
    def search_by_content(cls, keyword: str) -> List[Note]:
        """全文搜索标题和内容。"""
        items = cls.list(limit=1000)
        keyword_lower = keyword.lower()
        return [
            note for note in items
            if keyword_lower in note.title.lower()
            or keyword_lower in note.content.lower()
        ]

    @classmethod
    def list_drafts(cls, owner_id: str) -> List[Note]:
        return cls.filter(owner_id=owner_id, is_draft=True)

    @classmethod
    def count_words_by_owner(cls, owner_id: str) -> int:
        """统计某用户所有笔记的总字数。"""
        notes = cls.filter(owner_id=owner_id, is_draft=False)
        return sum(n.word_count for n in notes)

    @classmethod
    def publish(cls, note_id: str) -> Note:
        note = cls.get_by_id(note_id)
        if not note:
            raise ValueError(f"Note id={note_id} not found")
        note.publish()
        return cls.update(note_id, is_draft=note.is_draft, content=note.content)
