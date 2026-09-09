"""
测试数据模型与数据库层
"""

import pytest
from cissp_trainer.models import Question, KnowledgePoint, StudyRecord, DOMAIN_NAMES


class TestModels:
    """模型基本功能测试"""

    def test_create_question(self, db_session):
        """创建一道单选题"""
        q = Question(
            external_id="test-001",
            domain=1,
            difficulty=3,
            question_type="single",
            stem="CIA 三元组是？",
            options={"A": "机密性完整性可用性", "B": "其他"},
            correct_answer="A",
            explanation="CIA = Confidentiality, Integrity, Availability",
            tags=["CIA三元组", "安全基础"],
            source="test",
        )
        db_session.add(q)
        db_session.commit()

        retrieved = db_session.query(Question).filter_by(external_id="test-001").first()
        assert retrieved is not None
        assert retrieved.id is not None
        assert retrieved.domain == 1
        assert retrieved.difficulty == 3
        assert retrieved.question_type == "single"
        assert retrieved.stem == "CIA 三元组是？"
        assert retrieved.options["A"] == "机密性完整性可用性"
        assert retrieved.correct_answer == "A"
        assert len(retrieved.tags) == 2
        assert retrieved.times_shown == 0
        assert retrieved.correct_rate == 0.0
        assert retrieved.domain_name == "安全与风险管理"

    def test_create_knowledge_point(self, db_session):
        """创建知识点"""
        kp = KnowledgePoint(
            name="CIA三元组",
            domain=1,
            description="信息安全三大目标",
            mastery_level=0.5,
        )
        db_session.add(kp)
        db_session.commit()

        retrieved = db_session.query(KnowledgePoint).filter_by(name="CIA三元组").first()
        assert retrieved is not None
        assert retrieved.domain == 1
        assert retrieved.mastery_level == 0.5
        assert retrieved.total_questions == 0

    def test_study_record_relation(self, db_session):
        """学习记录与题目的关联"""
        q = Question(
            domain=1, difficulty=1, question_type="single",
            stem="测试题", options={"A": "对", "B": "错"},
            correct_answer="A", tags=["测试"],
        )
        db_session.add(q)
        db_session.flush()

        record = StudyRecord(
            question_id=q.id,
            user_answer="A",
            is_correct=True,
            efactor=2.5,
            interval=1,
            repetition=1,
        )
        db_session.add(record)
        db_session.commit()

        assert len(q.study_records) == 1
        assert q.study_records[0].is_correct is True
        assert record.question.id == q.id

    def test_domain_names_all_8(self):
        """8 个领域名称完整"""
        assert len(DOMAIN_NAMES) == 8
        for i in range(1, 9):
            assert i in DOMAIN_NAMES
            assert len(DOMAIN_NAMES[i]) > 0
