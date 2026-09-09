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
