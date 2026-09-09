"""
间隔重复算法 — 简化版 SM-2

基于 SuperMemo SM-2 算法，做了以下简化：
- quality 用答题结果推导（答对=4，答错=1），不用用户手动自评
- 首次答错直接重置 repetition=0，下次间隔 1 天
- efactor 不低于 1.3（和 SM-2 一致）

算法流程：
  1. 计算 quality（0-5）
  2. 更新 efactor: EF = EF + (0.1 - (5-q) * (0.08 + (5-q)*0.02))
  3. 如果 quality < 3: repetition = 0, interval = 1
  4. 如果 repetition = 0: interval = 1
     如果 repetition = 1: interval = 3
     否则: interval = round(interval * EF)
  5. repetition += 1
  6. next_review_date = today + interval 天
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class SRResult:
    """间隔重复计算结果"""
    quality: int
    efactor: float
    interval: int
    repetition: int
    next_review_date: date
    is_new: bool  # 是否是首次学习


def calc_quality(is_correct: bool, difficulty: int = 3, time_spent_sec: int = 0) -> int:
    """
    根据答题情况推导 quality（0-5）

    - 答对：默认 4 分；很快答出 +1；困难题答对 +1（最多 5）
    - 答错：默认 1 分；完全不会 0 分
    """
    if is_correct:
        q = 4
        # 快速作答加分（< 10 秒）
        if time_spent_sec > 0 and time_spent_sec < 10:
            q += 1
        # 难题答对加分
        if difficulty >= 4:
            q += 1
        return min(5, q)
    else:
        # 答错
        return 1


def sm2_update(
    is_correct: bool,
    current_efactor: float = 2.5,
    current_interval: int = 0,
    current_repetition: int = 0,
    today: date | None = None,
    difficulty: int = 3,
    time_spent_sec: int = 0,
) -> SRResult:
    """
    执行一次 SM-2 更新

    参数：
      is_correct: 是否答对
      current_efactor: 当前易度因子（默认 2.5）
      current_interval: 当前间隔天数（默认 0）
      current_repetition: 当前连续正确次数（默认 0）
      today: 今天日期（默认 date.today()）
      difficulty: 题目难度 1-5
      time_spent_sec: 答题用时秒

    返回：SRResult
    """
    today = today or date.today()
    is_new = current_repetition == 0 and current_interval == 0

    quality = calc_quality(is_correct, difficulty, time_spent_sec)

    # 更新 EF
    ef = current_efactor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ef = max(1.3, ef)  # EF 不低于 1.3

    if quality < 3:
        # 答错/没记住：重置
        repetition = 0
        interval = 1
    else:
        repetition = current_repetition
        if repetition == 0:
            interval = 1
        elif repetition == 1:
            interval = 3
        else:
            interval = max(1, round(current_interval * ef))
        repetition += 1

    next_review = today + timedelta(days=interval)

    return SRResult(
        quality=quality,
        efactor=round(ef, 3),
        interval=interval,
        repetition=repetition,
        next_review_date=next_review,
        is_new=is_new,
    )


def due_priority(next_review_date: date | None, efactor: float = 2.5,
                 today: date | None = None) -> float:
    """
    计算题目到期优先级（值越大越应该复习）

    公式：已逾期天数 / efactor
    - 还没到期：负值（越远越低）
    - 已逾期：正值（越久越高）
    - EF 越低（越难记）：优先级越高
    """
    today = today or date.today()
    if next_review_date is None:
        return 999.0  # 从未复习过，最高优先级

    days_overdue = (today - next_review_date).days
    ef = max(1.3, efactor)
    return days_overdue / ef
