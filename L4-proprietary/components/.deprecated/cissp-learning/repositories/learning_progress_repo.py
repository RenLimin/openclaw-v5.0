"""学习进度数据仓库。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from base.base_repository import BaseRepository
from models.learning_progress import LearningProgress, ReviewResult


class LearningProgressRepository(BaseRepository[LearningProgress]):
    model_cls = LearningProgress

    @classmethod
    def get_by_user_and_kp(
        cls, user_id: str, knowledge_point_id: str
    ) -> Optional[LearningProgress]:
        results = cls.filter(
            user_id=user_id,
            knowledge_point_id=knowledge_point_id,
            limit=1,
        )
        return results[0] if results else None

    @classmethod
    def list_by_user(cls, user_id: str) -> List[LearningProgress]:
        return cls.filter(user_id=user_id)

    @classmethod
    def list_by_plan(cls, plan_id: str) -> List[LearningProgress]:
        return cls.filter(plan_id=plan_id)

    @classmethod
    def list_due_reviews(cls, user_id: str) -> List[LearningProgress]:
        """列出所有到期需要复习的知识点。"""
        items = cls.filter(user_id=user_id)
        now = datetime.utcnow()
        return [
            lp for lp in items
            if lp.next_review_at is not None and lp.next_review_at <= now
        ]

    @classmethod
    def list_mastered(cls, user_id: str) -> List[LearningProgress]:
        return cls.filter(user_id=user_id, is_mastered=True)

    @classmethod
    def list_completed(cls, user_id: str) -> List[LearningProgress]:
        return cls.filter(user_id=user_id, is_completed=True)

    @classmethod
    def record_study(
        cls, user_id: str, knowledge_point_id: str, minutes: int
    ) -> LearningProgress:
        """记录学习时间，不存在则创建。"""
        progress = cls.get_by_user_and_kp(user_id, knowledge_point_id)
        if progress is None:
            progress = cls.create(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            )
        progress.record_study(minutes)
        return cls.update(
            progress.id,
            total_study_time_minutes=progress.total_study_time_minutes,
            study_sessions=progress.study_sessions,
            first_study_at=progress.first_study_at,
            last_study_at=progress.last_study_at,
        )

    @classmethod
    def review_kp(
        cls, user_id: str, knowledge_point_id: str, result: ReviewResult
    ) -> LearningProgress:
        """对知识点执行一次间隔重复复习。"""
        progress = cls.get_by_user_and_kp(user_id, knowledge_point_id)
        if progress is None:
            progress = cls.create(
                user_id=user_id,
                knowledge_point_id=knowledge_point_id,
            )
        progress.review(result)
        return cls.update(
            progress.id,
            ease_factor=progress.ease_factor,
            interval_days=progress.interval_days,
            repetitions=progress.repetitions,
            next_review_at=progress.next_review_at,
            last_review_result=progress.last_review_result,
            total_reviews=progress.total_reviews,
            correct_reviews=progress.correct_reviews,
            mastery=progress.mastery,
            is_mastered=progress.is_mastered,
        )

    @classmethod
    def total_study_minutes(cls, user_id: str) -> int:
        """统计用户总学习时长（分钟）。"""
        items = cls.filter(user_id=user_id)
        return sum(lp.total_study_time_minutes for lp in items)

    @classmethod
    def mastered_count(cls, user_id: str) -> int:
        """统计用户已掌握的知识点数量。"""
        return sum(1 for lp in cls.filter(user_id=user_id) if lp.is_mastered)
