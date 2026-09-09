"""
测试间隔重复算法（简化 SM-2）
"""

from datetime import date, timedelta
import pytest
from cissp_trainer.spaced_repetition import sm2_update, calc_quality, due_priority


class TestSM2:
    """SM-2 算法测试"""

    def test_first_correct_answer(self):
        """首次答对：间隔从 0 → 1 天"""
        result = sm2_update(is_correct=True, today=date(2026, 9, 10))
        assert result.repetition == 1
        assert result.interval == 1
        assert result.next_review_date == date(2026, 9, 11)
        assert result.efactor == 2.5
        assert result.is_new is True

    def test_second_correct_answer(self):
        """第二次答对：间隔从 1 → 3 天"""
        result = sm2_update(
            is_correct=True,
            current_efactor=2.5,
            current_interval=1,
            current_repetition=1,
            today=date(2026, 9, 11),
        )
        assert result.repetition == 2
        assert result.interval == 3
        assert result.next_review_date == date(2026, 9, 14)
        assert result.is_new is False

    def test_third_correct_answer(self):
        """第三次答对：间隔 = 3 * EF"""
        result = sm2_update(
            is_correct=True,
            current_efactor=2.5,
            current_interval=3,
            current_repetition=2,
            today=date(2026, 9, 14),
        )
        assert result.repetition == 3
        assert result.interval == round(3 * 2.5)  # 7.5 → 8
        assert result.next_review_date == date(2026, 9, 14) + timedelta(days=result.interval)

    def test_wrong_answer_resets(self):
        """答错：repetition 归零，间隔 1 天，EF 降低"""
        result = sm2_update(
            is_correct=False,
            current_efactor=2.5,
            current_interval=10,
            current_repetition=5,
            today=date(2026, 9, 10),
        )
        assert result.repetition == 0
        assert result.interval == 1
        assert result.efactor < 2.5
        assert result.efactor >= 1.3  # EF 不低于 1.3
        assert result.next_review_date == date(2026, 9, 11)

    def test_efactor_floor(self):
        """EF 不会低于 1.3"""
        # 连续答错很多次，EF 应该稳定在 1.3
        ef = 2.5
        for _ in range(20):
            r = sm2_update(is_correct=False, current_efactor=ef, current_interval=1, current_repetition=1)
            ef = r.efactor
        assert ef == 1.3

    def test_quality_calculation(self):
        """quality 推导"""
        # 答对普通题
        assert calc_quality(True, difficulty=3, time_spent_sec=20) == 4
        # 答对 + 很快
        assert calc_quality(True, difficulty=3, time_spent_sec=5) == 5
        # 答对 + 难题
        assert calc_quality(True, difficulty=4, time_spent_sec=30) == 5
        # 答错
        assert calc_quality(False, difficulty=3, time_spent_sec=10) == 1

    def test_due_priority(self):
        """到期优先级计算"""
        today = date(2026, 9, 10)

        # 从未复习过 → 最高优先级
        assert due_priority(None, today=today) == 999.0

        # 已逾期 5 天
        overdue5 = today - timedelta(days=5)
        p = due_priority(overdue5, efactor=2.5, today=today)
        assert p > 0
        assert abs(p - 5 / 2.5) < 0.01

        # 还没到期 → 负值
        future = today + timedelta(days=3)
        p2 = due_priority(future, efactor=2.5, today=today)
        assert p2 < 0

        # EF 越低（越难），相同逾期天数优先级越高
        p_low_ef = due_priority(overdue5, efactor=1.5, today=today)
        p_high_ef = due_priority(overdue5, efactor=3.0, today=today)
        assert p_low_ef > p_high_ef
