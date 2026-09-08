"""测验数据仓库。"""

from __future__ import annotations

from typing import List, Optional

from base.base_repository import BaseRepository
from models.quiz import Quiz


class QuizRepository(BaseRepository[Quiz]):
    model_cls = Quiz

    @classmethod
    def list_by_creator(cls, creator_id: str, only_published: bool = False) -> List[Quiz]:
        filters = {"creator_id": creator_id}
        if only_published:
            filters["is_published"] = True
        return cls.filter(**filters)

    @classmethod
    def list_by_plan(cls, plan_id: str) -> List[Quiz]:
        return cls.filter(plan_id=plan_id)

    @classmethod
    def list_by_knowledge_point(cls, knowledge_point_id: str) -> List[Quiz]:
        """列出包含某知识点的测验。"""
        all_quizzes = cls.list(limit=1000)
        return [
            q for q in all_quizzes
            if knowledge_point_id in q.knowledge_point_ids
        ]

    @classmethod
    def list_published(cls) -> List[Quiz]:
        return cls.filter(is_published=True)

    @classmethod
    def search_by_title(cls, keyword: str) -> List[Quiz]:
        items = cls.list(limit=1000)
        keyword_lower = keyword.lower()
        return [
            q for q in items
            if keyword_lower in q.title.lower()
        ]

    @classmethod
    def publish(cls, quiz_id: str) -> Quiz:
        quiz = cls.get_by_id(quiz_id)
        if not quiz:
            raise ValueError(f"Quiz id={quiz_id} not found")
        quiz.publish()
        return cls.update(quiz_id, is_published=quiz.is_published)

    @classmethod
    def unpublish(cls, quiz_id: str) -> Quiz:
        quiz = cls.get_by_id(quiz_id)
        if not quiz:
            raise ValueError(f"Quiz id={quiz_id} not found")
        quiz.unpublish()
        return cls.update(quiz_id, is_published=quiz.is_published)

    @classmethod
    def add_question(cls, quiz_id: str, question) -> Quiz:
        quiz = cls.get_by_id(quiz_id)
        if not quiz:
            raise ValueError(f"Quiz id={quiz_id} not found")
        quiz.add_question(question)
        return cls.update(quiz_id, questions=quiz.questions)

    @classmethod
    def remove_question(cls, quiz_id: str, question_id: str) -> Quiz:
        quiz = cls.get_by_id(quiz_id)
        if not quiz:
            raise ValueError(f"Quiz id={quiz_id} not found")
        quiz.remove_question(question_id)
        return cls.update(quiz_id, questions=quiz.questions)
