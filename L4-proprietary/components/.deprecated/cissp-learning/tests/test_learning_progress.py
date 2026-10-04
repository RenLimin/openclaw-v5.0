import pytest

"""学习进度 + 间隔重复测试。"""

from datetime import datetime, timedelta

from models.learning_progress import (
    LearningProgress,
    ReviewResult,
    SpacedRepetition,
    QUALITY_MAP,
)
from repositories.learning_progress_repo import LearningProgressRepository


class TestSpacedRepetition:
    def test_initial_state(self):
        sr = SpacedRepetition()
        assert sr.ease_factor == 2.5
        assert sr.interval_days == 0
        assert sr.repetitions == 0
        assert sr.mastery_level == 0.0

    def test_first_good_review(self):
        sr = SpacedRepetition()
        interval, ef, reps = sr.review(ReviewResult.GOOD)
        assert reps == 1
        assert interval == 1  # 第一次正确：1天
        assert ef > 0  # EF 应该有变化

    def test_second_good_review(self):
        sr = SpacedRepetition()
        sr.review(ReviewResult.GOOD)   # reps=1, interval=1
        interval, ef, reps = sr.review(ReviewResult.GOOD)  # reps=2, interval=6
        assert reps == 2
        assert interval == 6

    def test_third_good_review_interval_grows(self):
        sr = SpacedRepetition()
        sr.review(ReviewResult.GOOD)
        sr.review(ReviewResult.GOOD)
        interval_3, _, reps = sr.review(ReviewResult.GOOD)
        assert reps == 3
        assert interval_3 > 6  # 间隔应该增长

    def test_forgot_resets_interval(self):
        sr = SpacedRepetition()
        sr.review(ReviewResult.GOOD)
        sr.review(ReviewResult.GOOD)
        sr.review(ReviewResult.GOOD)
        assert sr.repetitions == 3

        interval, ef, reps = sr.review(ReviewResult.FORGOT)
        assert reps == 0
        assert interval == 1

    def test_easy_increases_ease(self):
        sr = SpacedRepetition()
        initial_ef = sr.ease_factor
        sr.review(ReviewResult.PERFECT)
        assert sr.ease_factor > initial_ef

    def test_hard_decreases_ease(self):
        sr = SpacedRepetition()
        initial_ef = sr.ease_factor
        sr.review(ReviewResult.HARD)
        assert sr.ease_factor < initial_ef

    def test_ease_min_bounds(self):
        sr = SpacedRepetition(ease_factor=1.3)
        # 连续多次困难复习，EF 不会低于 1.3
        for _ in range(10):
            sr.review(ReviewResult.HARD)
        assert sr.ease_factor >= 1.3

    def test_next_review_date(self):
        sr = SpacedRepetition()
        sr.review(ReviewResult.GOOD)
        expected = datetime.utcnow() + timedelta(days=1)
        # 日期应该是明天（误差 1 分钟内）
        assert abs((sr.next_review_date - expected).total_seconds()) < 60

    def test_mastery_increases_with_reps(self):
        sr = SpacedRepetition()
        assert sr.mastery_level == 0.0
        sr.review(ReviewResult.GOOD)
        m1 = sr.mastery_level
        sr.review(ReviewResult.GOOD)
        m2 = sr.mastery_level
        sr.review(ReviewResult.GOOD)
        m3 = sr.mastery_level
        assert m1 < m2 < m3
        assert 0.0 <= m3 <= 1.0

    def test_quality_map_has_all_results(self):
        for r in ReviewResult:
            assert r in QUALITY_MAP
            assert 0 <= QUALITY_MAP[r] <= 5


class TestLearningProgressModel:
    def test_create_progress(self):
        lp = LearningProgress(
            user_id="u1",
            knowledge_point_id="kp1",
            plan_id="plan1",
        )
        assert lp.user_id == "u1"
        assert lp.knowledge_point_id == "kp1"
        assert lp.mastery == 0.0
        assert lp.is_mastered is False
        assert lp.total_reviews == 0

    def test_record_study(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        lp.record_study(30)
        assert lp.total_study_time_minutes == 30
        assert lp.study_sessions == 1
        assert lp.first_study_at is not None
        assert lp.last_study_at is not None

        lp.record_study(15)
        assert lp.total_study_time_minutes == 45
        assert lp.study_sessions == 2

    def test_record_study_zero_or_negative(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        lp.record_study(0)
        assert lp.study_sessions == 0
        lp.record_study(-5)
        assert lp.study_sessions == 0

    def test_review_increases_correct_count(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        lp.review(ReviewResult.GOOD)
        assert lp.total_reviews == 1
        assert lp.correct_reviews == 1
        assert lp.repetitions == 1

    def test_review_forgot_no_correct(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        lp.review(ReviewResult.FORGOT)
        assert lp.total_reviews == 1
        assert lp.correct_reviews == 0

    def test_review_accuracy(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        assert lp.review_accuracy == 0.0
        lp.review(ReviewResult.GOOD)
        lp.review(ReviewResult.FORGOT)
        lp.review(ReviewResult.EASY)
        assert lp.review_accuracy == pytest.approx(2 / 3, rel=1e-2)

    def test_is_due_for_review(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        assert lp.is_due_for_review is False  # 未设置 next_review_at

        lp.review(ReviewResult.GOOD)  # 下次复习 = 1 天后
        assert lp.is_due_for_review is False  # 还没到期

        # 手动设为已过期
        lp.next_review_at = datetime.utcnow() - timedelta(days=1)
        assert lp.is_due_for_review is True

    def test_days_until_review(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        assert lp.days_until_review == -1  # 无日期

        lp.review(ReviewResult.GOOD)  # 1 天后
        assert lp.days_until_review >= 0

    def test_multiple_reviews_build_mastery(self):
        lp = LearningProgress(user_id="u1", knowledge_point_id="kp1")
        for _ in range(5):
            lp.review(ReviewResult.GOOD)
        assert lp.mastery > 0.5
        assert lp.repetitions == 5


class TestLearningProgressRepository:
    def test_create_and_get(self):
        lp = LearningProgressRepository.create(
            user_id="u1",
            knowledge_point_id="kp1",
        )
        fetched = LearningProgressRepository.get_by_id(lp.id)
        assert fetched is not None
        assert fetched.user_id == "u1"

    def test_get_by_user_and_kp(self):
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp1")
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp2")
        LearningProgressRepository.create(user_id="u2", knowledge_point_id="kp1")

        lp = LearningProgressRepository.get_by_user_and_kp("u1", "kp1")
        assert lp is not None
        assert lp.user_id == "u1"
        assert lp.knowledge_point_id == "kp1"

        assert LearningProgressRepository.get_by_user_and_kp("u1", "kp99") is None

    def test_record_study_creates_if_not_exists(self):
        lp = LearningProgressRepository.record_study("u1", "kp1", 30)
        assert lp.user_id == "u1"
        assert lp.total_study_time_minutes == 30
        assert lp.study_sessions == 1

        # 再记录一次
        lp2 = LearningProgressRepository.record_study("u1", "kp1", 15)
        assert lp2.total_study_time_minutes == 45
        assert lp2.study_sessions == 2

    def test_review_kp_creates_if_not_exists(self):
        lp = LearningProgressRepository.review_kp("u1", "kp1", ReviewResult.GOOD)
        assert lp.total_reviews == 1
        assert lp.correct_reviews == 1
        assert lp.repetitions == 1

    def test_list_due_reviews(self):
        # 创建一个已到期的
        lp1 = LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp1")
        LearningProgressRepository.update(
            lp1.id,
            next_review_at=datetime.utcnow() - timedelta(days=1),
        )
        # 创建一个未到期的
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp2")

        due = LearningProgressRepository.list_due_reviews("u1")
        assert len(due) == 1
        assert due[0].knowledge_point_id == "kp1"

    def test_list_mastered(self):
        lp = LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp1")
        LearningProgressRepository.update(lp.id, is_mastered=True, mastery=0.95)
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp2")

        mastered = LearningProgressRepository.list_mastered("u1")
        assert len(mastered) == 1

    def test_total_study_minutes(self):
        LearningProgressRepository.create(
            user_id="u1", knowledge_point_id="kp1", total_study_time_minutes=30
        )
        LearningProgressRepository.create(
            user_id="u1", knowledge_point_id="kp2", total_study_time_minutes=20
        )
        LearningProgressRepository.create(
            user_id="u2", knowledge_point_id="kp1", total_study_time_minutes=100
        )
        assert LearningProgressRepository.total_study_minutes("u1") == 50

    def test_mastered_count(self):
        lp1 = LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp1")
        LearningProgressRepository.update(lp1.id, is_mastered=True)
        lp2 = LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp2")
        LearningProgressRepository.update(lp2.id, is_mastered=True)
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp3")

        assert LearningProgressRepository.mastered_count("u1") == 2

    def test_list_by_user(self):
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp1")
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp2")
        LearningProgressRepository.create(user_id="u2", knowledge_point_id="kp1")
        assert len(LearningProgressRepository.list_by_user("u1")) == 2

    def test_list_by_plan(self):
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp1", plan_id="p1")
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp2", plan_id="p1")
        LearningProgressRepository.create(user_id="u1", knowledge_point_id="kp3", plan_id="p2")
        assert len(LearningProgressRepository.list_by_plan("p1")) == 2
