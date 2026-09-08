"""测验领域模型。

支持单选/多选/判断三种题型，自动评分。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from base.base_model import TenantModel


class QuestionType(str, Enum):
    """题目类型。"""
    SINGLE_CHOICE = "single_choice"    # 单选题
    MULTIPLE_CHOICE = "multiple_choice"  # 多选题
    TRUE_FALSE = "true_false"          # 判断题


class QuizQuestion(BaseModel):
    """测验题目（值对象）。"""

    question_id: str = ""
    type: QuestionType = QuestionType.SINGLE_CHOICE
    content: str = ""                   # 题干
    options: List[str] = Field(default_factory=list)  # 选项列表
    correct_answer: List[str] = Field(default_factory=list)  # 正确答案（选项索引或 "true"/"false"）
    explanation: str = ""               # 答案解析
    score: float = 1.0                  # 分值
    difficulty: int = 2                 # 难度 1-5
    knowledge_point_id: Optional[str] = None  # 关联知识点

    def validate_answer(self, user_answer: List[str]) -> bool:
        """判断用户答案是否正确。

        单选：答案集合只有一个元素且匹配
        多选：答案集合完全匹配
        判断：答案为 ["true"] 或 ["false"]
        """
        # 标准化答案（排序后比较）
        correct = sorted(a.strip().lower() for a in self.correct_answer)
        user = sorted(a.strip().lower() for a in user_answer)
        return correct == user

    def check_answer(self, user_answer: List[str]) -> tuple[bool, float]:
        """检查答案并返回 (是否正确, 得分)。"""
        if self.validate_answer(user_answer):
            return True, self.score
        return False, 0.0


class QuizAttempt(BaseModel):
    """测验答题记录（值对象，用于存储答题历史）。"""

    attempt_id: str = ""
    user_id: str = ""
    started_at: datetime = Field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    answers: dict[str, List[str]] = Field(default_factory=dict)  # {question_id: answer_list}
    score: float = 0.0
    total_score: float = 0.0
    correct_count: int = 0
    total_count: int = 0
    is_passed: bool = False
    time_spent_seconds: int = 0


class Quiz(TenantModel):
    """测验聚合根。"""

    # ── 基本信息 ────────────────────────────────────────────────
    title: str
    description: str = ""
    category: str = "practice"   # practice / exam / quiz / assignment

    # ── 关联 ────────────────────────────────────────────────────
    knowledge_point_ids: List[str] = Field(default_factory=list)
    plan_id: Optional[str] = None
    creator_id: str = ""

    # ── 题目 ────────────────────────────────────────────────────
    questions: List[QuizQuestion] = Field(default_factory=list)

    # ── 配置 ────────────────────────────────────────────────────
    passing_score: float = 60.0  # 及格分数
    time_limit_minutes: int = 0  # 0 表示不限时
    shuffle_questions: bool = False
    shuffle_options: bool = False
    max_attempts: int = 0        # 0 表示不限次数

    # ── 统计 ────────────────────────────────────────────────────
    attempt_count: int = 0
    average_score: float = 0.0
    pass_count: int = 0

    # ── 状态 ────────────────────────────────────────────────────
    is_published: bool = False
    tags: List[str] = Field(default_factory=list)

    # ── 计算属性 ────────────────────────────────────────────────

    @property
    def total_questions(self) -> int:
        return len(self.questions)

    @property
    def total_score(self) -> float:
        return round(sum(q.score for q in self.questions), 2)

    @property
    def pass_percentage(self) -> float:
        """及格率（基于累计统计）。"""
        if self.attempt_count == 0:
            return 0.0
        return round(self.pass_count / self.attempt_count * 100, 1)

    # ── 题目管理 ────────────────────────────────────────────────

    def add_question(self, question: QuizQuestion) -> None:
        if not question.question_id:
            import uuid
            question.question_id = uuid.uuid4().hex[:8]
        self.questions.append(question)

    def remove_question(self, question_id: str) -> bool:
        for i, q in enumerate(self.questions):
            if q.question_id == question_id:
                self.questions.pop(i)
                return True
        return False

    def get_question(self, question_id: str) -> Optional[QuizQuestion]:
        for q in self.questions:
            if q.question_id == question_id:
                return q
        return None

    # ── 评分 ────────────────────────────────────────────────────

    def grade(self, answers: dict[str, List[str]]) -> QuizAttempt:
        """自动评分。

        Args:
            answers: {question_id: [answer1, answer2, ...]}

        Returns:
            QuizAttempt 包含得分和统计
        """
        import uuid
        total_score = self.total_score
        score = 0.0
        correct_count = 0

        for q in self.questions:
            user_answer = answers.get(q.question_id, [])
            is_correct, earned = q.check_answer(user_answer)
            if is_correct:
                correct_count += 1
            score += earned

        score = round(score, 2)
        # passing_score 为百分比（0-100），与总分比较后判定
        pass_threshold = total_score * self.passing_score / 100.0 if total_score > 0 else 0
        is_passed = score >= pass_threshold

        # 更新累计统计
        self.attempt_count += 1
        self.average_score = round(
            (self.average_score * (self.attempt_count - 1) + score) / self.attempt_count,
            2,
        )
        if is_passed:
            self.pass_count += 1

        return QuizAttempt(
            attempt_id=uuid.uuid4().hex,
            submitted_at=datetime.utcnow(),
            answers=answers,
            score=score,
            total_score=total_score,
            correct_count=correct_count,
            total_count=self.total_questions,
            is_passed=is_passed,
        )

    def publish(self) -> None:
        """发布测验。"""
        if not self.questions:
            raise ValueError("Quiz must have at least one question")
        self.is_published = True

    def unpublish(self) -> None:
        """取消发布。"""
        self.is_published = False
