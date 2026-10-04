"""测验测试。"""

import pytest

from models.quiz import (
    Quiz,
    QuizQuestion,
    QuestionType,
    QuizAttempt,
)
from repositories.quiz_repo import QuizRepository


class TestQuizQuestion:
    def test_single_choice_correct(self):
        q = QuizQuestion(
            question_id="q1",
            type=QuestionType.SINGLE_CHOICE,
            content="CISSP 有几个域？",
            options=["6", "7", "8", "9"],
            correct_answer=["2"],  # 索引从0，选"8"即索引2
            score=1.0,
        )
        assert q.validate_answer(["2"]) is True
        assert q.validate_answer(["0"]) is False

    def test_multiple_choice_correct(self):
        q = QuizQuestion(
            question_id="q2",
            type=QuestionType.MULTIPLE_CHOICE,
            content="以下哪些是对称加密算法？",
            options=["AES", "RSA", "DES", "ECC"],
            correct_answer=["0", "2"],
            score=2.0,
        )
        assert q.validate_answer(["0", "2"]) is True
        assert q.validate_answer(["0", "1"]) is False
        # 顺序无关
        assert q.validate_answer(["2", "0"]) is True

    def test_true_false_correct(self):
        q = QuizQuestion(
            question_id="q3",
            type=QuestionType.TRUE_FALSE,
            content="AES 是对称加密算法。",
            correct_answer=["true"],
            score=1.0,
        )
        assert q.validate_answer(["true"]) is True
        assert q.validate_answer(["false"]) is False

    def test_check_answer_returns_score(self):
        q = QuizQuestion(
            question_id="q1",
            type=QuestionType.SINGLE_CHOICE,
            content="测试题",
            options=["A", "B"],
            correct_answer=["0"],
            score=5.0,
        )
        correct, score = q.check_answer(["0"])
        assert correct is True
        assert score == 5.0

        correct, score = q.check_answer(["1"])
        assert correct is False
        assert score == 0.0


class TestQuizModel:
    def test_create_quiz(self):
        quiz = Quiz(
            title="CISSP 第一域测验",
            description="安全与风险管理",
            category="exam",
            creator_id="teacher-001",
            passing_score=70.0,
            time_limit_minutes=60,
        )
        assert quiz.title == "CISSP 第一域测验"
        assert quiz.total_questions == 0
        assert quiz.total_score == 0.0
        assert quiz.is_published is False

    def test_add_question(self):
        quiz = Quiz(title="测验", creator_id="u1")
        quiz.add_question(QuizQuestion(
            type=QuestionType.SINGLE_CHOICE,
            content="问题1",
            options=["a", "b"],
            correct_answer=["0"],
            score=1.0,
        ))
        assert quiz.total_questions == 1
        assert quiz.total_score == 1.0

    def test_add_question_auto_id(self):
        quiz = Quiz(title="测验", creator_id="u1")
        quiz.add_question(QuizQuestion(content="题", options=["a", "b"], correct_answer=["0"]))
        assert quiz.questions[0].question_id != ""

    def test_remove_question(self):
        quiz = Quiz(title="测验", creator_id="u1")
        quiz.add_question(QuizQuestion(
            question_id="q1", content="题1", options=["a"], correct_answer=["0"]
        ))
        assert quiz.remove_question("q1") is True
        assert quiz.total_questions == 0
        assert quiz.remove_question("nonexist") is False

    def test_get_question(self):
        quiz = Quiz(title="测验", creator_id="u1")
        quiz.add_question(QuizQuestion(
            question_id="q1", content="题1", options=["a"], correct_answer=["0"]
        ))
        q = quiz.get_question("q1")
        assert q is not None
        assert q.content == "题1"
        assert quiz.get_question("q99") is None

    def test_grade_all_correct(self):
        quiz = Quiz(title="测验", creator_id="u1", passing_score=60.0)
        quiz.add_question(QuizQuestion(
            question_id="q1",
            type=QuestionType.SINGLE_CHOICE,
            content="题1",
            options=["a", "b"],
            correct_answer=["0"],
            score=1.0,
        ))
        quiz.add_question(QuizQuestion(
            question_id="q2",
            type=QuestionType.SINGLE_CHOICE,
            content="题2",
            options=["x", "y"],
            correct_answer=["1"],
            score=1.0,
        ))
        result = quiz.grade({"q1": ["0"], "q2": ["1"]})
        assert isinstance(result, QuizAttempt)
        assert result.score == 2.0
        assert result.total_score == 2.0
        assert result.correct_count == 2
        assert result.total_count == 2
        assert result.is_passed is True

    def test_grade_partial(self):
        quiz = Quiz(title="测验", creator_id="u1", passing_score=50.0)
        quiz.add_question(QuizQuestion(
            question_id="q1", content="题1", options=["a", "b"],
            correct_answer=["0"], score=10.0,
        ))
        quiz.add_question(QuizQuestion(
            question_id="q2", content="题2", options=["a", "b"],
            correct_answer=["0"], score=10.0,
        ))
        result = quiz.grade({"q1": ["0"], "q2": ["1"]})
        assert result.score == 10.0
        assert result.correct_count == 1
        assert result.is_passed is True  # 10/20 = 50% == passing_score

    def test_grade_updates_stats(self):
        quiz = Quiz(title="测验", creator_id="u1")
        quiz.add_question(QuizQuestion(
            question_id="q1", content="题", options=["a", "b"],
            correct_answer=["0"], score=1.0,
        ))
        assert quiz.attempt_count == 0

        quiz.grade({"q1": ["0"]})
        assert quiz.attempt_count == 1
        assert quiz.average_score == 1.0
        assert quiz.pass_count == 1

        quiz.grade({"q1": ["1"]})
        assert quiz.attempt_count == 2
        assert quiz.average_score == 0.5

    def test_publish(self):
        quiz = Quiz(title="测验", creator_id="u1")
        quiz.add_question(QuizQuestion(
            question_id="q1", content="题", options=["a"], correct_answer=["0"]
        ))
        quiz.publish()
        assert quiz.is_published is True

    def test_publish_empty_quiz_raises(self):
        quiz = Quiz(title="空测验", creator_id="u1")
        with pytest.raises(ValueError, match="at least one question"):
            quiz.publish()

    def test_pass_percentage(self):
        quiz = Quiz(title="测验", creator_id="u1", passing_score=0.5)
        quiz.add_question(QuizQuestion(
            question_id="q1", content="题", options=["a", "b"],
            correct_answer=["0"], score=1.0,
        ))
        quiz.grade({"q1": ["0"]})  # 通过
        quiz.grade({"q1": ["1"]})  # 不通过
        assert quiz.pass_percentage == 50.0


class TestQuizRepository:
    def test_create_and_get(self):
        q = QuizRepository.create(
            title="测验1", creator_id="u1", passing_score=60.0,
        )
        fetched = QuizRepository.get_by_id(q.id)
        assert fetched is not None
        assert fetched.title == "测验1"

    def test_list_by_creator(self):
        QuizRepository.create(title="t1", creator_id="u1")
        QuizRepository.create(title="t2", creator_id="u1")
        QuizRepository.create(title="t3", creator_id="u2")
        assert len(QuizRepository.list_by_creator("u1")) == 2

    def test_list_published(self):
        QuizRepository.create(title="已发布", creator_id="u1", is_published=True)
        QuizRepository.create(title="未发布", creator_id="u1", is_published=False)
        published = QuizRepository.list_published()
        assert len(published) == 1
        assert published[0].title == "已发布"

    def test_publish_via_repo(self):
        q = QuizRepository.create(title="测验", creator_id="u1")
        QuizRepository.add_question(
            q.id,
            QuizQuestion(content="题", options=["a", "b"], correct_answer=["0"]),
        )
        published = QuizRepository.publish(q.id)
        assert published.is_published is True

    def test_search_by_title(self):
        QuizRepository.create(title="CISSP 第一域测验", creator_id="u1")
        QuizRepository.create(title="网络安全测验", creator_id="u1")
        QuizRepository.create(title="CISSP 模拟考", creator_id="u1")
        results = QuizRepository.search_by_title("CISSP")
        assert len(results) == 2
