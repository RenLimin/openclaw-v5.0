"""classifier — 底稿 col2「交付预计完成时间」十类分类。

分类按优先级互斥穷尽（DESIGN-DETAIL §2.2），金额不在这里处理：

  1 DUE_2026    : 日期 year=2026（计入，按日期月份）
  2 FUTURE_YEAR : 日期 year>=2027（不计）
  3 IN_PIPELINE : 文本含「已提交资料」（计入，归 pipeline 桶）
  4 ALREADY_DONE: 文本含「100%确收」（不计）
  5 EXCEPTION   : 文本含「异常」
  6 TERMINATED  : 文本含「终止」
  7 ADJUSTED    : 文本含「调整」
  8 NOT_STARTED : 文本含「未立项」「未预计」
  9 ZERO_AMOUNT : 文本含「金额为0」
  兜底 MISSING_DATE: 空/不可解析

关键词与年份边界均为模块级配置常量，口径变更只改本文件顶部。
"""

from __future__ import annotations

import datetime
import re
from typing import Optional

# ─── 配置常量（口径唯一调整点）───

FORECAST_YEAR = 2026          # 动态预估年份（DUE 边界）
FUTURE_YEAR_THRESHOLD = 2027  # >= 该年为 FUTURE_YEAR

# 文本关键词（按优先级）；NOT_STARTED 支持多个同义词
KW_IN_PIPELINE = "已提交资料"
KW_ALREADY_DONE = "100%确收"
KW_EXCEPTION = "异常"
KW_TERMINATED = "终止"
KW_ADJUSTED = "调整"
KW_NOT_STARTED = ("未立项", "未预计")
KW_ZERO_AMOUNT = "金额为0"

# 十类标签
DUE_2026 = "DUE_2026"
FUTURE_YEAR = "FUTURE_YEAR"
IN_PIPELINE = "IN_PIPELINE"
ALREADY_DONE = "ALREADY_DONE"
EXCEPTION = "EXCEPTION"
TERMINATED = "TERMINATED"
ADJUSTED = "ADJUSTED"
NOT_STARTED = "NOT_STARTED"
ZERO_AMOUNT = "ZERO_AMOUNT"
MISSING_DATE = "MISSING_DATE"

# 优先级顺序（index 即优先级，0 最高）
CATEGORIES = (
    DUE_2026, FUTURE_YEAR, IN_PIPELINE, ALREADY_DONE, EXCEPTION,
    TERMINATED, ADJUSTED, NOT_STARTED, ZERO_AMOUNT, MISSING_DATE,
)

# 计入动态口径的类别
COUNTED_CATEGORIES = frozenset({DUE_2026, IN_PIPELINE})

# 形如 "2026年7月" / "2026-7-15" / "2026/07" 的纯文本日期
_TEXT_DATE_PATTERNS = (
    re.compile(r"^\s*(\d{4})\s*[年\-/]\s*(\d{1,2})\s*[月\-/]?\s*(\d{1,2})?\s*日?\s*$"),
)


def parse_due_date(value: object) -> Optional[datetime.date]:
    """把 col2 原文解析为 date；无法解析返回 None（fail-closed）。

    支持：datetime/date、"2026年7月"、"2026-07-15"、"2026/7"。
    文本标签（已提交资料等）与 None/空串/布尔 → None。
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    for pat in _TEXT_DATE_PATTERNS:
        m = pat.match(s)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            d = int(m.group(3)) if m.group(3) else 1
            try:
                return datetime.date(y, mo, d)
            except ValueError:
                return None
    return None


def classify_due(value: object) -> tuple[str, Optional[int]]:
    """按优先级分类 col2 原文。

    Returns:
        (category, month)：month 仅 DUE_2026 时为 1..12，其余 None。
        纯函数：无 IO/时间/随机。
    """
    # 1-2 日期分支（含 "2026年7月" 类文本日期）
    d = parse_due_date(value)
    if d is not None:
        if d.year == FORECAST_YEAR:
            return DUE_2026, d.month
        if d.year >= FUTURE_YEAR_THRESHOLD:
            return FUTURE_YEAR, None
        # 可解析但落在 2025 及以前：无对应业务口径，fail-closed
        return MISSING_DATE, None

    # 3-9 文本关键词分支（顺序即优先级）
    if isinstance(value, str):
        s = value
        if KW_IN_PIPELINE in s:
            return IN_PIPELINE, None
        if KW_ALREADY_DONE in s:
            return ALREADY_DONE, None
        if KW_EXCEPTION in s:
            return EXCEPTION, None
        if KW_TERMINATED in s:
            return TERMINATED, None
        if KW_ADJUSTED in s:
            return ADJUSTED, None
        if any(k in s for k in KW_NOT_STARTED):
            return NOT_STARTED, None
        if KW_ZERO_AMOUNT in s:
            return ZERO_AMOUNT, None

    # 兜底：空/None/布尔/不可解析
    return MISSING_DATE, None
