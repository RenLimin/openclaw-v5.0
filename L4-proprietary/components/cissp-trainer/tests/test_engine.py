"""
测试学习引擎核心（出题 + 答题 + 统计）
"""

import pytest
from datetime import date, timedelta
from cissp_trainer.engine import (
    pick_questions, answer_question,
    get_overall_stats, get_domain_stats,
    get_weak_knowledge_points, get_progress_curve,
)
from cissp_trainer.models import Question, KnowledgePoint


class TestPickQuestions:
    """出题模块测试"""

    def test_pick_random(self, db_session, seed_questions):
        """随机抽题"""
        qs = pick_questions(db_session, count=5, mode="random")
        assert len(qs) == 5
        assert all(isinstance(q, Question) for q in qs)

    def test_pick_by_domain(self, db_session, seed_questions):
        """按领域抽题"""
        qs = pick_questions(db_session, count=10, domain=1, mode="random")
        assert len(qs) == 5  # 域1只有5题
        assert all(q.domain == 1 for q in qs)

    def test_pick_by_difficulty(self, db_session, seed_questions):
        """按难度抽题"""
        qs = pick_questions(db_session, count=5, difficulty=3, mode="random")
        assert len(qs) > 0
        assert all(q.difficulty == 3 for q in qs)

    def test_pick_count_more_than_pool(self, db_session, seed_questions):
        """请求数量超过题库，返回全部"""
        qs = pick_questions(db_session, count=100, domain=2, mode="random")
        assert len(qs) == 3  # 域2只有3题

    def test_pick_exam_mode_by_domain_weight(self, db_session, seed_questions):
        """模拟考试模式：按域权重分布"""
        qs = pick_questions(db_session, count=10, mode="exam")
        assert len(qs) == 10
        # 至少覆盖 2 个以上域
        domains = set(q.domain for q in qs)
        assert len(domains) >= 2

    def test_pick_empty_pool(self, db_session):
        """空题库返回空列表"""
        qs = pick_questions(db_session, count=10, domain=99, mode="random")
        assert qs == []

    def test_pick_review_mode_priority(self, db_session, seed_questions):
        """复习模式：到期的优先"""
        # 先做几道题，让它们有不同的下次复习时间
        qs = pick_questions(db_session, count=5, domain=1, mode="random")
        for q in qs[:3]:
            answer_question(db_session, q.id, q.correct_answer)
        db_session.commit()

        # 复习模式抽题
        review_qs = pick_questions(db_session, count=3, mode="review")
        assert len(review_qs) == 3


class TestAnswerQuestion:
    """答题模块测试"""

    def test_correct_answer_single(self, db_session, seed_questions):
        """单选题答对"""
        q = pick_questions(db_session, count=1, domain=1, mode="random")[0]
        result = answer_question(db_session, q.id, q.correct_answer)
        assert result["is_correct"] is True
        assert result["correct_answer"] == q.correct_answer
        assert result["next_review_date"] is not None
        # 题统计更新
        assert q.times_shown == 1
        assert q.times_correct == 1

    def test_wrong_answer_single(self, db_session, seed_questions):
        """单选题答错"""
        q = pick_questions(db_session, count=1, domain=1, mode="random")[0]
        # 找一个错误答案
        wrong_ans = "B" if q.correct_answer == "A" else "A"
        result = answer_question(db_session, q.id, wrong_ans)
        assert result["is_correct"] is False
        assert q.times_shown == 1
        assert q.times_correct == 0

    def test_correct_answer_multiple(self, db_session, seed_questions):
        """多选题答对"""
        q = pick_questions(db_session, count=1, domain=1, mode="random")[0]
        # 找一道多选题
        from cissp_trainer.models import Question
        mq = db_session.query(Question).filter_by(question_type="multiple").first()
        if mq:
            result = answer_question(db_session, mq.id, mq.correct_answer)
            assert result["is_correct"] is True

    def test_knowledge_point_updated(self, db_session, seed_questions):
        """答题后知识点掌握度被更新"""
        q = pick_questions(db_session, count=1, domain=1, mode="random")[0]
        tag_name = q.tags[0]

        # 答题前
        kp_before = (
            db_session.query(KnowledgePoint)
            .filter_by(name=tag_name, domain=q.domain)
            .first()
        )
        assert kp_before is not None
        mastery_before = kp_before.mastery_level
        review_before = kp_before.review_count
        correct_before = kp_before.correct_count

        # 答对
        answer_question(db_session, q.id, q.correct_answer)
        db_session.expire_all()  # 确保重新从 DB 加载

        kp_after = (
            db_session.query(KnowledgePoint)
            .filter_by(name=tag_name, domain=q.domain)
            .first()
        )
        # 答对后掌握度应该上升
        assert kp_after.mastery_level > mastery_before
        assert kp_after.review_count == review_before + 1
        assert kp_after.correct_count == correct_before + 1

    def test_invalid_question_id(self, db_session):
        """无效的题目 ID 抛异常"""
        with pytest.raises(ValueError):
            answer_question(db_session, 9999, "A")

    def test_truefalse_correct(self, db_session, seed_questions):
        """判断题答对"""
        from cissp_trainer.models import Question
        q = db_session.query(Question).filter_by(question_type="truefalse").first()
        assert q is not None
        result = answer_question(db_session, q.id, q.correct_answer)
        assert result["is_correct"] is True


class TestStatistics:
    """统计模块测试"""

    def test_overall_stats_empty(self, db_session, seed_questions):
        """空数据时的总体统计"""
        stats = get_overall_stats(db_session)
        assert stats["total_questions"] > 0
        assert stats["total_study_records"] == 0
        assert stats["overall_accuracy"] == 0.0
        assert stats["today_studied"] == 0

    def test_overall_stats_after_answers(self, db_session, seed_questions):
        """答题后总体统计更新"""
        qs = pick_questions(db_session, count=10, mode="random")
        # 7 对 3 错
        for i, q in enumerate(qs):
            if i < 7:
                answer_question(db_session, q.id, q.correct_answer)
            else:
                wrong = "B" if q.correct_answer == "A" else "A"
                answer_question(db_session, q.id, wrong)
        db_session.commit()

        stats = get_overall_stats(db_session)
        assert stats["total_study_records"] == 10
        assert stats["total_correct"] == 7
        assert stats["overall_accuracy"] == pytest.approx(0.7, 0.01)
        assert stats["today_studied"] == 10

    def test_domain_stats(self, db_session, seed_questions):
        """各领域统计"""
        # 域1做几道题
        qs = pick_questions(db_session, count=3, domain=1, mode="random")
        for q in qs:
            answer_question(db_session, q.id, q.correct_answer)
        db_session.commit()

        domain_stats = get_domain_stats(db_session)
        assert len(domain_stats) == 8
        # 域1
        d1 = [d for d in domain_stats if d["domain"] == 1][0]
        assert d1["question_count"] == 5
        assert d1["study_count"] == 3
        assert d1["correct_count"] == 3
        assert d1["accuracy"] == pytest.approx(1.0, 0.01)
        # 域2（没做过题）
        d2 = [d for d in domain_stats if d["domain"] == 2][0]
        assert d2["study_count"] == 0
        assert d2["accuracy"] == 0.0

    def test_weak_knowledge_points(self, db_session, seed_questions):
        """薄弱知识点排名"""
        # 反复答错同一道题，让它的知识点变弱
        q = pick_questions(db_session, count=1, domain=1, mode="random")[0]
        weak_tag = q.tags[0]
        for _ in range(5):
            wrong = "B" if q.correct_answer == "A" else "A"
            answer_question(db_session, q.id, wrong)
        db_session.commit()

        weak_kps = get_weak_knowledge_points(db_session, top_n=5)
        # 至少有一个
        assert len(weak_kps) > 0
        # 掌握度都应该小于 1.0
        assert all(kp.mastery_level < 1.0 for kp in weak_kps)
        # 按掌握度升序排列
        for i in range(len(weak_kps) - 1):
            assert weak_kps[i].mastery_level <= weak_kps[i + 1].mastery_level

    def test_progress_curve(self, db_session, seed_questions):
        """学习进度曲线"""
        curve = get_progress_curve(db_session, days=7)
        assert len(curve) == 7
        assert all("date" in d and "total" in d for d in curve)

    def test_weak_mode_picking(self, db_session, seed_questions):
        """薄弱知识点模式出题"""
        # 反复答错域1的题
        qs = pick_questions(db_session, count=3, domain=1, mode="random")
        for q in qs:
            for _ in range(3):
                wrong = "B" if q.correct_answer == "A" else "A"
                answer_question(db_session, q.id, wrong)
        db_session.commit()

        # 薄弱模式抽题
        weak_qs = pick_questions(db_session, count=5, mode="weak")
        assert len(weak_qs) == 5
