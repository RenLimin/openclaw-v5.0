"""学习进度领域模型。

间隔重复复习（Spaced Repetition）算法（简化版 SM-2）。
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from base.base_model import TenantModel


class ReviewResult(str, Enum):
    """复习结果（用户自评质量 0-5）。"""
    FORGOT = "forgot"           # 完全忘记（0）
    HARD = "hard"               # 困难（2）
    GOOD = "good"               # 良好（3）
    EASY = "easy"               # 简单（4）
    PERFECT = "perfect"         # 完美（5）


# ReviewResult → 质量分（0-5）
QUALITY_MAP: dict[ReviewResult, int] = {
    ReviewResult.FORGOT: 0,
    ReviewResult.HARD: 2,
    ReviewResult.GOOD: 3,
    ReviewResult.EASY: 4,
    ReviewResult.PERFECT: 5,
}


class SpacedRepetition:
    """简化版 SM-2 间隔重复算法。

    参数：
    - ease_factor (EF): 难度系数，初始 2.5，范围 [1.3, 3.0]
    - interval: 距下次复习的间隔（天）
    - repetitions: 连续正确次数

    规则：
    - 质量 >= 3: 间隔 = interval * EF, repetitions += 1
    - 质量 < 3:  间隔 = 1, repetitions = 0
    - EF 更新: EF = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    """

    MIN_EASE = 1.3
    MAX_EASE = 3.0

    def __init__(
        self,
        ease_factor: float = 2.5,
        interval_days: int = 0,
        repetitions: int = 0,
    ) -> None:
        self.ease_factor = ease_factor
        self.interval_days = interval_days
        self.repetitions = repetitions

    def review(self, result: ReviewResult) -> tuple[int, float, int]:
        """执行一次复习，返回 (新间隔天数, 新 EF, 新重复次数)。

        标准 SM-2 算法：EF 始终更新，答对增长间隔，答错重置。
        """
        quality = QUALITY_MAP[result]

        # 始终更新 EF（标准 SM-2）
        delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        new_ef = max(self.MIN_EASE, min(self.MAX_EASE, self.ease_factor + delta))

        if quality >= 3:
            # 答对：增长间隔
            if self.repetitions == 0:
                new_interval = 1
            elif self.repetitions == 1:
                new_interval = 6
            else:
                new_interval = math.ceil(self.interval_days * self.ease_factor)
            new_reps = self.repetitions + 1
        else:
            # 答错：重置间隔和重复次数，但 EF 仍更新
            new_interval = 1
            new_reps = 0

        self.interval_days = new_interval
        self.ease_factor = round(new_ef, 3)
        self.repetitions = new_reps

        return new_interval, self.ease_factor, new_reps

    @property
    def next_review_date(self) -> datetime:
        """下次复习日期。"""
        return datetime.utcnow() + timedelta(days=self.interval_days)

    @property
    def mastery_level(self) -> float:
        """掌握程度（0-1），基于 repetitions 和 interval。"""
        if self.repetitions == 0:
            return 0.0
        # 结合重复次数和间隔估算
        score = min(1.0, (self.repetitions * 0.15) + (self.interval_days / 100))
        return round(min(1.0, score), 3)


class LearningProgress(TenantModel):
    """学习进度聚合根。

    记录用户对某个知识点的学习进度，支持间隔重复复习。
    """

    # ── 关联 ────────────────────────────────────────────────────
    user_id: str = ""
    knowledge_point_id: str = ""
    plan_id: Optional[str] = None

    # ── 学习进度 ────────────────────────────────────────────────
    total_study_time_minutes: int = 0  # 累计学习时长（分钟）
    study_sessions: int = 0            # 学习次数
    first_study_at: Optional[datetime] = None
    last_study_at: Optional[datetime] = None

    # ── 间隔重复 ────────────────────────────────────────────────
    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    next_review_at: Optional[datetime] = None
    last_review_result: Optional[ReviewResult] = None
    total_reviews: int = 0
    correct_reviews: int = 0

    # ── 掌握程度 ────────────────────────────────────────────────
    mastery: float = 0.0  # 0.0 - 1.0

    # ── 状态 ────────────────────────────────────────────────────
    is_completed: bool = False
    is_mastered: bool = False

    # ── 学习行为 ────────────────────────────────────────────────

    def record_study(self, minutes: int) -> None:
        """记录一次学习。"""
        if minutes <= 0:
            return
        now = datetime.utcnow()
        self.total_study_time_minutes += minutes
        self.study_sessions += 1
        if self.first_study_at is None:
            self.first_study_at = now
        self.last_study_at = now
        self.updated_at = now

    def review(self, result: ReviewResult) -> None:
        """执行一次间隔重复复习。"""
        sr = SpacedRepetition(
            ease_factor=self.ease_factor,
            interval_days=self.interval_days,
            repetitions=self.repetitions,
        )
        sr.review(result)

        self.ease_factor = sr.ease_factor
        self.interval_days = sr.interval_days
        self.repetitions = sr.repetitions
        self.next_review_at = sr.next_review_date
        self.last_review_result = result
        self.total_reviews += 1
        if result in (ReviewResult.GOOD, ReviewResult.EASY, ReviewResult.PERFECT):
            self.correct_reviews += 1

        self.mastery = sr.mastery_level
        if self.mastery >= 0.9:
            self.is_mastered = True

        self.updated_at = datetime.utcnow()

    # ── 计算属性 ────────────────────────────────────────────────

    @property
    def review_accuracy(self) -> float:
        """复习正确率（0-1）。"""
        if self.total_reviews == 0:
            return 0.0
        return round(self.correct_reviews / self.total_reviews, 3)

    @property
    def is_due_for_review(self) -> bool:
        """是否到期需要复习。"""
        if self.next_review_at is None:
            return False
        return datetime.utcnow() >= self.next_review_at

    @property
    def days_until_review(self) -> int:
        """距下次复习还有几天（负数表示已逾期）。"""
        if self.next_review_at is None:
            return -1
        delta = self.next_review_at - datetime.utcnow()
        return delta.days
