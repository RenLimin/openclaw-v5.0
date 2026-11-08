"""engine — 双口径纯计算引擎。

输入：report_parser 产出的 ObligationRow 序列（不读文件/DB）。
输出：ForecastResult（frozen dataclass）。

口径（DESIGN-DETAIL §2，金额单位元）：
  - 锁定：每行 locked_year（col27），按 category_group 拆，按 locked_monthly 拆月；
  - 实际：Σ actual_ytd（col32..40）；
  - 动态：dyn_counted（DUE_2026 按 dyn_month，IN_PIPELINE 归 pipeline 桶）；
  - gap = 动态 − 锁定。

硬性：纯函数 —— 不读文件/DB、不取系统时间、无随机；同输入连跑 3 次逐字段相等。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .classifier import DUE_2026, IN_PIPELINE
from .report_parser import ObligationRow

GROUP_NEW = "新签"
GROUP_DEFERRED = "递延"
GROUPS = (GROUP_NEW, GROUP_DEFERRED)
MONTHS = tuple(range(1, 13))
MONTH_KEYS = tuple(f"{m:02d}" for m in MONTHS)


@dataclass(frozen=True)
class ForecastResult:
    """双口径聚合结果（DESIGN-DETAIL §3）。"""

    period: str
    forecast_year: int
    # 锁定
    locked_total: float
    locked_by_group: dict[str, float]
    locked_monthly: dict[str, float]              # "01".."12"
    # 实际
    actual_ytd_total: float
    actual_by_group: dict[str, float]
    # 动态
    dynamic_total: float
    dynamic_by_group: dict[str, float]
    dynamic_due_monthly: dict[str, float]         # DUE_2026 逐月
    dynamic_pipeline: float                       # IN_PIPELINE 独立桶
    dynamic_due_total: float
    # 差异
    gap_dynamic_minus_locked: float
    # 计数
    line_count: int


def forecast(
    rows: Sequence[ObligationRow],
    *,
    period: str = "202609",
    forecast_year: int = 2026,
) -> ForecastResult:
    """对规范化行做双口径聚合。纯函数。

    去重说明：每行是一条底稿履约义务。锁定/实际口径按 budget_id
    （预算执行表主键 col4）去重——实测 327 条底稿行重复引用已有预算项，
    去重后与预算执行表本体合计逐分相等；动态口径按底稿行各计 col42。
    """
    locked_by_group: dict[str, float] = {g: 0.0 for g in GROUPS}
    actual_by_group: dict[str, float] = {g: 0.0 for g in GROUPS}
    dynamic_by_group: dict[str, float] = {g: 0.0 for g in GROUPS}
    # 同一预算履约项（col4 带 YS，预算执行表主键）可能被多条底稿行引用，
    # 锁定/实际口径对每个预算项只计一次；动态口径按底稿行各计 col42。
    seen_budget_ids: set[str] = set()
    locked_monthly: dict[str, float] = {k: 0.0 for k in MONTH_KEYS}
    dynamic_due_monthly: dict[str, float] = {k: 0.0 for k in MONTH_KEYS}

    locked_total = 0.0
    actual_total = 0.0
    dynamic_total = 0.0
    dynamic_pipeline = 0.0
    dynamic_due_total = 0.0

    seen_rows: Iterable[ObligationRow] = rows
    for row in seen_rows:
        # 仅关联上预算执行表、且该预算项首次出现的行进锁定/实际口径
        if row.matched_budget and row.budget_id not in seen_budget_ids:
            seen_budget_ids.add(row.budget_id)
            g = row.category_group
            if g in locked_by_group:
                locked_by_group[g] += row.locked_year
                actual_by_group[g] += row.actual_ytd
                for i, amt in enumerate(row.locked_monthly):
                    locked_monthly[MONTH_KEYS[i]] += amt
            locked_total += row.locked_year
            actual_total += row.actual_ytd

        # 动态口径（dyn_in_plan 已在 parser 中排除未关联行）
        if row.dyn_in_plan:
            g = row.category_group
            if g in dynamic_by_group:
                dynamic_by_group[g] += row.dyn_counted
            if row.dyn_category == DUE_2026 and row.dyn_month in MONTHS:
                dynamic_due_monthly[f"{row.dyn_month:02d}"] += row.dyn_counted
                dynamic_due_total += row.dyn_counted
            elif row.dyn_category == IN_PIPELINE:
                dynamic_pipeline += row.dyn_counted
            dynamic_total += row.dyn_counted

    return ForecastResult(
        period=period,
        forecast_year=forecast_year,
        locked_total=locked_total,
        locked_by_group=locked_by_group,
        locked_monthly=locked_monthly,
        actual_ytd_total=actual_total,
        actual_by_group=actual_by_group,
        dynamic_total=dynamic_total,
        dynamic_by_group=dynamic_by_group,
        dynamic_due_monthly=dynamic_due_monthly,
        dynamic_pipeline=dynamic_pipeline,
        dynamic_due_total=dynamic_due_total,
        gap_dynamic_minus_locked=dynamic_total - locked_total,
        line_count=len(rows),
    )
