"""pivot_builder — 通用 group-by 透视（纯函数，无副作用）。

契约：IMPLEMENTATION-PLAN-REVENUE-ANALYSIS v1.1 §4.3。
供 _build_diff / _build_restructure 复用，避免重复聚合逻辑。

行序规则（202606 实证）：Excel 透视默认按行标签 Unicode 码点升序，
空白标签（(空白)）置尾——复刻该行为保证与黄金报表逐行一致。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

from typing import Any, Callable, Optional


def pivot(
    rows: list[dict],
    key_fn: Callable[[dict], Any],
    value_fn: Callable[[dict], float],
    filter_fn: Optional[Callable[[dict], bool]] = None,
) -> dict[Any, float]:
    """通用 group-by 透视：按 key_fn 分组，对 value_fn 求和。

    filter_fn 为 None 时不过滤。返回 {key: 聚合值}。
    """
    out: dict[Any, float] = {}
    for r in rows:
        if filter_fn is not None and not filter_fn(r):
            continue
        k = key_fn(r)
        out[k] = out.get(k, 0.0) + value_fn(r)
    return out


def sorted_keys(keys, blank_label: str = "(空白)") -> list:
    """行标签排序：Unicode 码点升序，空白标签置尾（复刻 Excel 透视默认序）。"""
    non_blank = sorted(k for k in keys if k != blank_label)
    if blank_label in keys:
        non_blank.append(blank_label)
    return non_blank
