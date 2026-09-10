"""
CISSP Trainer 数据模型

使用 SQLAlchemy ORM，底层 SQLite。
三张核心表：questions / study_records / knowledge_points
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Date, DateTime,
    Float, JSON, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ── 枚举常量 ──────────────────────────────────────────────

DOMAIN_NAMES = {
    1: "安全与风险管理",
    2: "资产安全",
    3: "安全架构与工程",
    4: "通信与网络安全",
    5: "身份与访问管理",
    6: "安全评估与测试",
    7: "安全运营",
    8: "软件开发安全",
}

QUESTION_TYPES = ("single", "multiple", "truefalse")  # 单选 / 多选 / 判断
DIFFICULTY_MIN = 1
DIFFICULTY_MAX = 5


# ── 知识点 ────────────────────────────────────────────────

class KnowledgePoint(Base):
    """知识点 — 掌握度追踪的基本单元"""

    __tablename__ = "knowledge_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    domain = Column(Integer, nullable=False, index=True)  # 1-8
    description = Column(Text, default="")

    # 掌握程度: 0.0 (完全不会) ~ 1.0 (完全掌握)
    mastery_level = Column(Float, default=0.0, nullable=False)

    # 统计
    total_questions = Column(Integer, default=0)       # 相关题目数
    correct_count = Column(Integer, default=0)         # 累计正确数
    wrong_count = Column(Integer, default=0)           # 累计错误数
    review_count = Column(Integer, default=0)          # 复习次数

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    last_reviewed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("name", "domain", name="uq_kp_name_domain"),
    )

    def __repr__(self):
        return f"<KP #{self.id} [{self.domain}] {self.name} mastery={self.mastery_level:.2f}>"


# ── 题目 ──────────────────────────────────────────────────

class Question(Base):
    """题目"""

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(128), unique=True, nullable=True)  # 外部导入 ID

    # 分类
    domain = Column(Integer, nullable=False, index=True)   # 1-8
    difficulty = Column(Integer, default=3, nullable=False)  # 1-5
    question_type = Column(String(20), default="single", nullable=False)  # single/multiple/truefalse

    # 内容
    stem = Column(Text, nullable=False)                    # 题干
    options = Column(JSON, nullable=False)                 # {"A": "...", "B": "...", ...}
    correct_answer = Column(String(10), nullable=False)    # "A" / "A,B" / "True"
    explanation = Column(Text, default="")                 # 解析

    # 元数据
    source = Column(String(255), default="")               # 来源
    tags = Column(JSON, default=list)                      # 知识点标签列表 [kp_name, ...]
    main_topic = Column(String(20), default="")            # 主项编号，如 "1.3"

    # 间隔重复字段（SM-2 用在题-用户关系上，这里不存；通过 study_records 计算）
    # 统计
    times_shown = Column(Integer, default=0)
    times_correct = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_question_domain_diff", "domain", "difficulty"),
    )

    @property
    def correct_rate(self) -> float:
        if self.times_shown == 0:
            return 0.0
        return self.times_correct / self.times_shown

    @property
    def domain_name(self) -> str:
        return DOMAIN_NAMES.get(self.domain, f"域{self.domain}")

    def __repr__(self):
        return f"<Q #{self.id} [{self.domain}] D{self.difficulty}>"


# ── 学习记录 ──────────────────────────────────────────────

class StudyRecord(Base):
    """学习/答题记录 — 每一次答题都记一条"""

    __tablename__ = "study_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    study_date = Column(Date, default=date.today, nullable=False, index=True)

    # 答题情况
    user_answer = Column(String(20), nullable=False)
    is_correct = Column(Boolean, nullable=False, index=True)
    time_spent_sec = Column(Integer, default=0)             # 用时（秒）

    # SM-2 间隔重复相关
    quality = Column(Integer, default=3)                    # 自评质量 0-5
    efactor = Column(Float, default=2.5)                    # 易度因子
    interval = Column(Integer, default=0)                   # 当前间隔（天）
    repetition = Column(Integer, default=0)                 # 连续正确次数
    next_review_date = Column(Date, nullable=True, index=True)  # 下次复习日期

    # 记录时间
    created_at = Column(DateTime, default=datetime.utcnow)

    question = relationship("Question", backref="study_records")

    __table_args__ = (
        Index("ix_sr_qid_date", "question_id", "study_date"),
    )

    def __repr__(self):
        return (f"<StudyRecord q#{self.question_id} "
                f"{'✓' if self.is_correct else '✗'} "
                f"next={self.next_review_date}>")


# ═══════════════════════════════════════════════════════════
#  v2 新增：学习路径 / 模拟考试 / 知识图谱
# ═══════════════════════════════════════════════════════════


# ── 学习路径 ──────────────────────────────────────────────

class LearningPath(Base):
    """学习路径模板（预设路径）"""

    __tablename__ = "learning_paths"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    slug = Column(String(64), unique=True, nullable=False, index=True)  # 短标识，如 beginner / advanced / sprint
    description = Column(Text, default="")
    goal = Column(String(255), default="")                    # 目标描述
    estimated_days = Column(Integer, default=30)              # 预计天数
    daily_question_target = Column(Integer, default=10)       # 每日目标题数
    difficulty_min = Column(Integer, default=1)
    difficulty_max = Column(Integer, default=5)
    prerequisites = Column(JSON, default=list)                # 前置路径 slug 列表
    milestones = Column(JSON, default=list)                   # 里程碑定义 [{name, domains, mastery_threshold, description}, ...]
    knowledge_point_sequence = Column(JSON, default=list)     # 知识点序列 [[domain, kp_name], ...]

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<LearningPath #{self.id} {self.slug} ({self.estimated_days}d)>"


class UserPathProgress(Base):
    """用户学习路径进度"""

    __tablename__ = "user_path_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    path_id = Column(Integer, ForeignKey("learning_paths.id"), nullable=False, index=True)
    user_id = Column(String(64), default="default", nullable=False, index=True)

    status = Column(String(20), default="in_progress")  # not_started / in_progress / completed / paused
    current_milestone_index = Column(Integer, default=0)
    completion_percent = Column(Float, default=0.0)

    start_date = Column(Date, default=date.today)
    expected_end_date = Column(Date, nullable=True)
    completed_date = Column(Date, nullable=True)

    total_questions_done = Column(Integer, default=0)
    total_correct = Column(Integer, default=0)
    streak_days = Column(Integer, default=0)
    last_study_date = Column(Date, nullable=True)

    # 每日计划缓存
    daily_plan_cache = Column(JSON, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    path = relationship("LearningPath", backref="user_progresses")

    __table_args__ = (
        UniqueConstraint("user_id", "path_id", name="uq_user_path"),
    )

    def __repr__(self):
        return f"<UserPathProgress path={self.path_id} status={self.status} {self.completion_percent:.0f}%>"


# ── 模拟考试 ──────────────────────────────────────────────

class ExamSession(Base):
    """模拟考试会话"""

    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), default="default", nullable=False, index=True)

    title = Column(String(255), default="CISSP 模拟考试")
    total_questions = Column(Integer, default=100)
    duration_minutes = Column(Integer, default=180)   # 默认 3 小时

    status = Column(String(20), default="pending")    # pending / in_progress / paused / submitted / timeout
    score = Column(Float, nullable=True)              # 百分制
    passed = Column(Boolean, nullable=True)           # 是否通过（>=70%）
    domain_scores = Column(JSON, default=dict)        # {domain_id: {"correct": n, "total": n, "score": float}}

    started_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    time_remaining_sec = Column(Integer, nullable=True)  # 暂停时剩余秒数

    # 题目顺序
    question_ids = Column(JSON, default=list)         # [q_id, q_id, ...]  按考试顺序
    current_index = Column(Integer, default=0)

    total_correct = Column(Integer, default=0)
    total_answered = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ExamSession #{self.id} {self.status} score={self.score}>"


class ExamAnswer(Base):
    """考试答题记录（每题一条）"""

    __tablename__ = "exam_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exam_id = Column(Integer, ForeignKey("exam_sessions.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    question_index = Column(Integer, default=0)         # 在试卷中的序号（0-based）

    user_answer = Column(String(20), default="")        # 用户答案
    is_correct = Column(Boolean, nullable=True)
    time_spent_sec = Column(Integer, default=0)
    is_flagged = Column(Boolean, default=False)         # 标记题（回头检查）

    answered_at = Column(DateTime, nullable=True)

    exam = relationship("ExamSession", backref="answers")
    question = relationship("Question")

    __table_args__ = (
        UniqueConstraint("exam_id", "question_id", name="uq_exam_question"),
        Index("ix_exam_answer_index", "exam_id", "question_index"),
    )

    def __repr__(self):
        return f"<ExamAnswer exam#{self.exam_id} q#{self.question_id} {'✓' if self.is_correct else '✗'}>"


# ── 知识图谱 ──────────────────────────────────────────────

class KnowledgeEdge(Base):
    """知识点之间的关联边（有向图：前置 → 后继）"""

    __tablename__ = "knowledge_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_kp_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False, index=True)
    target_kp_id = Column(Integer, ForeignKey("knowledge_points.id"), nullable=False, index=True)

    # 关系类型: prerequisite（前置依赖） / related（相关/并列） / part_of（组成部分）
    edge_type = Column(String(20), default="prerequisite", index=True)
    weight = Column(Float, default=1.0)  # 关联强度 0-1

    description = Column(String(255), default="")

    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("KnowledgePoint", foreign_keys=[source_kp_id], backref="out_edges")
    target = relationship("KnowledgePoint", foreign_keys=[target_kp_id], backref="in_edges")

    __table_args__ = (
        UniqueConstraint("source_kp_id", "target_kp_id", "edge_type", name="uq_kp_edge"),
    )

    def __repr__(self):
        return f"<KnowledgeEdge #{self.source_kp_id} -> #{self.target_kp_id} ({self.edge_type})>"
