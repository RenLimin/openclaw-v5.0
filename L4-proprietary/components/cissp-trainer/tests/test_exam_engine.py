"""
模拟考试引擎测试
"""

import pytest
from datetime import datetime, timedelta
from cissp_trainer.exam_engine import (
    create_exam, start_exam, get_current_question, answer_current,
    pause_exam, resume_exam, submit_exam, get_exam_history,
    get_score_curve, get_exam_detail, compare_with_previous,
    goto_question, flag_question,
    PASS_THRESHOLD,
)


class TestCreateExam:
    """创建考试测试"""

    def test_create_exam_success(self, db_session, seed_questions):
        """可以成功创建考试"""
        result = create_exam(db_session, question_count=10)
        assert result["success"] is True
        assert result["total_questions"] == 10
        assert "exam_id" in result

    def test_create_exam_count_limited_by_pool(self, db_session, seed_questions):
        """题库不够时按实际题量"""
        result = create_exam(db_session, question_count=1000)
        assert result["success"] is True
        assert result["total_questions"] < 1000

    def test_create_exam_with_domain_filter(self, db_session, seed_questions):
        """可以按领域筛选"""
        result = create_exam(db_session, question_count=5, domain_filter=[1])
        assert result["success"] is True
        # 验证所有题都是域 1 的
        from cissp_trainer.models import ExamSession, Question
        exam = db_session.get(ExamSession, result["exam_id"])
        for qid in exam.question_ids:
            q = db_session.get(Question, qid)
            assert q.domain == 1

    def test_create_exam_duration(self, db_session, seed_questions):
        """考试时长设置正确"""
        result = create_exam(db_session, question_count=5, duration_minutes=60)
        assert result["success"] is True
        assert result["time_remaining_sec"] == 60 * 60

    def test_create_exam_empty_pool(self, db_session):
        """空题库时创建失败"""
        result = create_exam(db_session, question_count=10)
        assert result["success"] is False
        assert "没有符合条件的题目" in result["error"]


class TestExamFlow:
    """考试流程测试"""

    def test_start_exam(self, db_session, seed_questions):
        """可以开始考试"""
        cr = create_exam(db_session, question_count=5)
        result = start_exam(db_session, cr["exam_id"])
        assert result["success"] is True
        assert result["status"] == "in_progress"

    def test_start_nonexistent_exam(self, db_session):
        """开始不存在的考试返回错误"""
        result = start_exam(db_session, 9999)
        assert result["success"] is False

    def test_get_current_question(self, db_session, seed_questions):
        """可以获取当前题目"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])
        q = get_current_question(db_session, cr["exam_id"])
        assert q is not None
        assert q["index"] == 1
        assert q["total"] == 5
        assert "stem" in q
        assert "options" in q

    def test_answer_advances_index(self, db_session, seed_questions):
        """答题后自动前进到下一题"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])

        result = answer_current(db_session, cr["exam_id"], "A", time_spent_sec=10)
        assert result["success"] is True
        assert result["answered_index"] == 1

        q = get_current_question(db_session, cr["exam_id"])
        assert q["index"] == 2

    def test_goto_question(self, db_session, seed_questions):
        """可以跳转到指定题目"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])

        result = goto_question(db_session, cr["exam_id"], 2)
        assert result["success"] is True
        assert result["current_index"] == 2

        q = get_current_question(db_session, cr["exam_id"])
        assert q["index"] == 3  # 1-based

    def test_goto_invalid_index(self, db_session, seed_questions):
        """跳转无效题号返回错误"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])

        result = goto_question(db_session, cr["exam_id"], 999)
        assert result["success"] is False

    def test_flag_question(self, db_session, seed_questions):
        """可以标记题目"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])

        result = flag_question(db_session, cr["exam_id"])
        assert result["success"] is True
        assert result["flagged"] is True

        # 再次调用取消标记
        result2 = flag_question(db_session, cr["exam_id"])
        assert result2["flagged"] is False


class TestPauseResume:
    """暂停/继续测试"""

    def test_pause_exam(self, db_session, seed_questions):
        """可以暂停考试"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])

        # 先答一题，扣点时间
        answer_current(db_session, cr["exam_id"], "A", time_spent_sec=30)

        result = pause_exam(db_session, cr["exam_id"])
        assert result["success"] is True
        assert result["status"] == "paused"
        assert "time_remaining_sec" in result

    def test_resume_exam(self, db_session, seed_questions):
        """可以继续考试"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])
        pause_exam(db_session, cr["exam_id"])

        result = resume_exam(db_session, cr["exam_id"])
        assert result["success"] is True
        assert result["status"] == "in_progress"

    def test_resume_not_paused(self, db_session, seed_questions):
        """未暂停的考试不能继续"""
        cr = create_exam(db_session, question_count=5)
        start_exam(db_session, cr["exam_id"])

        result = resume_exam(db_session, cr["exam_id"])
        assert result["success"] is False


class TestSubmitAndScoring:
    """交卷与评分测试"""

    def test_submit_exam_scores_correctly(self, db_session, seed_questions):
        """交卷后能正确评分"""
        cr = create_exam(db_session, question_count=5)
        exam_id = cr["exam_id"]
        start_exam(db_session, exam_id)

        # 答完全部题，全对
        for i in range(5):
            q = get_current_question(db_session, exam_id)
            correct_ans = _get_correct_answer(db_session, q["question_id"])
            answer_current(db_session, exam_id, correct_ans, time_spent_sec=5)

        result = submit_exam(db_session, exam_id)
        assert result["success"] is True
        assert result["total_correct"] == 5
        assert result["score"] == 100.0
        assert result["passed"] is True

    def test_submit_partial_answers(self, db_session, seed_questions):
        """未答完也能交卷，未答题算错"""
        cr = create_exam(db_session, question_count=5)
        exam_id = cr["exam_id"]
        start_exam(db_session, exam_id)

        # 只答 2 题，都对
        for i in range(2):
            q = get_current_question(db_session, exam_id)
            correct_ans = _get_correct_answer(db_session, q["question_id"])
            answer_current(db_session, exam_id, correct_ans, time_spent_sec=5)

        result = submit_exam(db_session, exam_id)
        assert result["success"] is True
        assert result["total_correct"] == 2
        assert result["score"] == 40.0
        assert result["passed"] is False

    def test_submit_wrong_answers(self, db_session, seed_questions):
        """答错扣分正确"""
        cr = create_exam(db_session, question_count=5)
        exam_id = cr["exam_id"]
        start_exam(db_session, exam_id)

        # 全部答错
        for i in range(5):
            answer_current(db_session, exam_id, "ZZZZ", time_spent_sec=1)

        result = submit_exam(db_session, exam_id)
        assert result["success"] is True
        assert result["total_correct"] == 0
        assert result["score"] == 0.0
        assert result["passed"] is False
        assert result["wrong_count"] == 5

    def test_pass_threshold(self, db_session, seed_questions):
        """及格线正确（70%）"""
        assert PASS_THRESHOLD == 0.70

    def test_domain_scores(self, db_session, seed_questions):
        """有分领域的分数统计"""
        cr = create_exam(db_session, question_count=10)
        exam_id = cr["exam_id"]
        start_exam(db_session, exam_id)

        for i in range(10):
            q = get_current_question(db_session, exam_id)
            answer_current(db_session, exam_id, q["options"] and "A" or "A", time_spent_sec=1)

        result = submit_exam(db_session, exam_id)
        assert "domain_scores" in result
        assert len(result["domain_scores"]) > 0
        for ds in result["domain_scores"]:
            assert "domain" in ds
            assert "score" in ds
            assert "correct" in ds
            assert "total" in ds

    def test_submit_syncs_study_records(self, db_session, seed_questions):
        """交卷后会同步到学习记录（影响掌握度）"""
        from cissp_trainer.models import StudyRecord
        before = db_session.query(StudyRecord).count()

        cr = create_exam(db_session, question_count=5)
        exam_id = cr["exam_id"]
        start_exam(db_session, exam_id)
        for i in range(5):
            q = get_current_question(db_session, exam_id)
            correct_ans = _get_correct_answer(db_session, q["question_id"])
            answer_current(db_session, exam_id, correct_ans, time_spent_sec=1)
        submit_exam(db_session, exam_id)

        after = db_session.query(StudyRecord).count()
        assert after > before


class TestExamHistory:
    """考试历史记录测试"""

    def test_empty_history(self, db_session, seed_questions):
        """初始时没有考试记录"""
        history = get_exam_history(db_session)
        assert history == []

    def test_history_after_submit(self, db_session, seed_questions):
        """交卷后历史记录里能看到"""
        cr = create_exam(db_session, question_count=3)
        exam_id = cr["exam_id"]
        start_exam(db_session, exam_id)
        for i in range(3):
            answer_current(db_session, exam_id, "A", time_spent_sec=1)
        submit_exam(db_session, exam_id)

        history = get_exam_history(db_session)
        assert len(history) == 1
        assert history[0]["exam_id"] == exam_id
        assert history[0]["score"] is not None

    def test_score_curve(self, db_session, seed_questions):
        """成绩曲线包含多次考试"""
        # 第一次考试
        cr1 = create_exam(db_session, question_count=3)
        start_exam(db_session, cr1["exam_id"])
        for i in range(3):
            answer_current(db_session, cr1["exam_id"], "A", time_spent_sec=1)
        submit_exam(db_session, cr1["exam_id"])

        # 第二次考试
        cr2 = create_exam(db_session, question_count=3)
        start_exam(db_session, cr2["exam_id"])
        for i in range(3):
            q = get_current_question(db_session, cr2["exam_id"])
            correct_ans = _get_correct_answer(db_session, q["question_id"])
            answer_current(db_session, cr2["exam_id"], correct_ans, time_spent_sec=1)
        submit_exam(db_session, cr2["exam_id"])

        curve = get_score_curve(db_session)
        assert len(curve) == 2
        # 第二次应该比第一次分高
        assert curve[1]["score"] >= curve[0]["score"]

    def test_exam_detail(self, db_session, seed_questions):
        """考试详情包含错题解析"""
        cr = create_exam(db_session, question_count=3)
        exam_id = cr["exam_id"]
        start_exam(db_session, exam_id)
        for i in range(3):
            answer_current(db_session, exam_id, "ZZZZZ", time_spent_sec=1)
        submit_exam(db_session, exam_id)

        detail = get_exam_detail(db_session, exam_id)
        assert detail is not None
        assert detail["score"] == 0.0
        assert len(detail["wrong_questions"]) == 3

    def test_compare_with_previous(self, db_session, seed_questions):
        """可以与上一次考试对比"""
        # 第一次
        cr1 = create_exam(db_session, question_count=3)
        start_exam(db_session, cr1["exam_id"])
        for i in range(3):
            answer_current(db_session, cr1["exam_id"], "A", time_spent_sec=1)
        submit_exam(db_session, cr1["exam_id"])

        # 第二次
        cr2 = create_exam(db_session, question_count=3)
        start_exam(db_session, cr2["exam_id"])
        for i in range(3):
            q = get_current_question(db_session, cr2["exam_id"])
            correct_ans = _get_correct_answer(db_session, q["question_id"])
            answer_current(db_session, cr2["exam_id"], correct_ans, time_spent_sec=1)
        submit_exam(db_session, cr2["exam_id"])

        comp = compare_with_previous(db_session, cr2["exam_id"])
        assert "previous" in comp
        assert "change" in comp
        assert comp["trend"] in ("上升", "下降", "持平")
        assert comp["change"] > 0  # 第二次全对，应该上升


def _get_correct_answer(session, question_id):
    """获取题目的正确答案"""
    from cissp_trainer.models import Question
    q = session.get(Question, question_id)
    return q.correct_answer if q else "A"
