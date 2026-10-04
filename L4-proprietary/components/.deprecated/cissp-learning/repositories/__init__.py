"""学习管理数据仓储层。

5 个仓储对应 5 个聚合根：
- LearningPlanRepository
- KnowledgePointRepository
- NoteRepository
- QuizRepository
- LearningProgressRepository
"""

from .learning_plan_repo import LearningPlanRepository
from .knowledge_point_repo import KnowledgePointRepository
from .note_repo import NoteRepository
from .quiz_repo import QuizRepository
from .learning_progress_repo import LearningProgressRepository

__all__ = [
    "LearningPlanRepository",
    "KnowledgePointRepository",
    "NoteRepository",
    "QuizRepository",
    "LearningProgressRepository",
]
