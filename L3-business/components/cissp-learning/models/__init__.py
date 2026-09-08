"""学习管理领域模型。

5 个聚合根：
- LearningPlan: 学习计划（状态机）
- KnowledgePoint: 知识点（CISSP八大域，树形层级）
- Note: 笔记（Markdown，字数统计）
- Quiz: 测验（单选/多选/判断，自动评分）
- LearningProgress: 学习进度（间隔重复复习）
"""

from .learning_plan import LearningPlan, PlanStatus, PlanMilestone, PlanObjective
from .knowledge_point import KnowledgePoint, CISSPDomain, KnowledgeLevel
from .note import Note
from .quiz import Quiz, QuizQuestion, QuestionType, QuizAttempt
from .learning_progress import LearningProgress, ReviewResult, SpacedRepetition

__all__ = [
    "LearningPlan", "PlanStatus", "PlanMilestone", "PlanObjective",
    "KnowledgePoint", "CISSPDomain", "KnowledgeLevel",
    "Note",
    "Quiz", "QuizQuestion", "QuestionType", "QuizAttempt",
    "LearningProgress", "ReviewResult", "SpacedRepetition",
]
