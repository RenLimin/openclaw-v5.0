"""caliber_builder — 双口径构建器（锁定/动态）。

契约：DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §6（黄金锚点 202609）：
  - 锁定 = 预算执行表 AB「2026年预计」按 A 分类（新签/递延）求和，按月 ΣP..AA；
  - 动态 = 底稿 AQ「2026年及以后计划确收」按 C 列权威分类（复用 revenue_forecast
    classifier），DUE_2026 按月份归月，IN_PIPELINE 独立桶；
  - 动态 by_group 经 履约ID 关联预算执行表分类（H→G，兜底 I→E）。

分叉修复（2026-11-10 实测）：
  - 宽表 JSON 序列化把 datetime 变成 "YYYY-MM-DD HH:MM:SS" 字符串，
    权威 classifier 对其 fail-closed → MISSING_DATE；
    本 builder 先归一化字符串 ISO 日期 → datetime 再走 classify_due，
    归位后 DUE 86,936,513.95 / PIPE 84,112,097.86 与黄金锚点逐分一致。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from bdms.modules.revenue_forecast.classifier import (
    classify_due, DUE_2026, IN_PIPELINE,
)

# ─── 常量 ───

GROUPS = ("新签", "递延")
# by_month 键契约（DESIGN-DETAIL §8.1）：完整 YYYYMM
MONTH_KEYS = tuple(f"2026{m:02d}" for m in range(1, 13))
MONTH_YEAR = 2026

# 字符串 ISO 日期格式（含时间戳变体）
_ISO_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
)


def normalize_due(value: object) -> object:
    """把字符串 ISO 日期（可含时间）归一化为 datetime，其余原样返回。

    宽表行 JSON 落盘时 datetime → "2026-12-31 00:00:00"，
    权威 classify_due 只认 datetime/date 或中文文本日期，字符串会 fail-closed；
    归一化后恢复可解析性，保证 DUE_2026 归月准确。
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    for fmt in _ISO_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return value


class CaliberBuilder:
    """双口径构建器：宽表行 → 锁定/动态口径快照（ra_caliber 数据源）。"""

    # ─── 锁定 ───

    def build_locked(self, budget_rows: list[dict]) -> dict:
        """锁定口径：预算执行表 AB 按分类求和 + 按月 ΣP..AA。"""
        by_group = {g: 0.0 for g in GROUPS}
        by_month = {k: 0.0 for k in MONTH_KEYS}
        for r in budget_rows:
            cat = r.get("A") or ""
            if cat not in by_group:
                continue
            by_group[cat] += self._num(r.get("AB"))
            for i, k in enumerate(MONTH_KEYS):
                col = chr(ord("P") + i)  # P..AA = 202601..202612
                by_month[k] += self._num(r.get(col))
        return {
            "caliber": "locked",
            "by_group": {k: round(v, 2) for k, v in by_group.items()},
            "by_month": {k: round(v, 2) for k, v in by_month.items()},
            "total": round(by_group["新签"] + by_group["递延"], 2),
        }

    # ─── 动态 ───

    def build_dynamic(self, budget_rows: list[dict], draft_rows: list[dict]) -> dict:
        """动态口径：底稿 AQ 按 C 列权威分类；DUE_2026 归月；by_group 关联预算表。

        动态 by_group 关联规则（202609 实测 0 未匹配）：
          - 底稿 H（履约ID）→ 预算执行表 G（现行键）
          - 兜底 底稿 I（对应预算履约ID）→ 预算执行表 E（履约ID（预算））
        """
        budget_cat: dict[str, str] = {}
        for r in budget_rows:
            g = (r.get("G") or "").strip()
            e = (r.get("E") or "").strip()
            cat = r.get("A") or ""
            if g and g not in budget_cat:
                budget_cat[g] = cat
            if e and e not in budget_cat:
                budget_cat[e] = cat

        by_group = {g: 0.0 for g in GROUPS}
        due_monthly = {k: 0.0 for k in MONTH_KEYS}
        pipeline = 0.0
        due_total = 0.0
        other_amount = 0.0
        missing_amount = 0.0
        missing_rows = 0

        for r in draft_rows:
            aq = self._num(r.get("AQ"))
            if aq == 0:
                continue
            cat, month = classify_due(normalize_due(r.get("C") or ""))
            if cat == DUE_2026:
                due_total += aq
                if month is not None:
                    due_monthly[f"{MONTH_YEAR}{month:02d}"] += aq
                grp = self._group_of(r, budget_cat)
                if grp in by_group:
                    by_group[grp] += aq
            elif cat == IN_PIPELINE:
                pipeline += aq
                grp = self._group_of(r, budget_cat)
                if grp in by_group:
                    by_group[grp] += aq
            elif cat == "MISSING_DATE":
                missing_amount += aq
                missing_rows += 1
            else:
                other_amount += aq

        total = round(due_total + pipeline, 2)
        return {
            "caliber": "dynamic",
            "by_group": {k: round(v, 2) for k, v in by_group.items()},
            "by_month": {k: round(v, 2) for k, v in due_monthly.items()},
            "total": total,
            "due_total": round(due_total, 2),
            "pipeline": round(pipeline, 2),
            "other_2027plus": round(other_amount, 2),
            "missing_amount": round(missing_amount, 2),
            "missing_rows": missing_rows,
        }

    def build(self, budget_rows: list[dict], draft_rows: list[dict]) -> dict:
        """双口径完整快照（ra_caliber 两行 + 差异）。"""
        locked = self.build_locked(budget_rows)
        dynamic = self.build_dynamic(budget_rows, draft_rows)
        return {
            "period_locked": locked,
            "period_dynamic": dynamic,
            "difference": round(dynamic["total"] - locked["total"], 2),
            "note": (
                "动态口径按底稿 C 列权威分类（DUE_2026 归月 / IN_PIPELINE 独立桶）；"
                f"跨年及其他 {dynamic['other_2027plus']:.2f} 元、缺日期 "
                f"{dynamic['missing_amount']:.2f} 元（{dynamic['missing_rows']} 行）不计入口径，"
                "明细见风险/排除清单。"
            ),
        }

    def _group_of(self, row: dict, budget_cat: dict[str, str]) -> Optional[str]:
        """底稿行 → 预算执行表分类：先 H 命中现行键，未命中再 I 兜底预算键。"""
        h = (row.get("H") or "").strip()
        if h:
            grp = budget_cat.get(h)
            if grp:
                return grp
        i = (row.get("I") or "").strip()
        if i:
            grp = budget_cat.get(i)
            if grp:
                return grp
        return None

    @staticmethod
    def _num(v: Any) -> float:
        try:
            return float(v) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0
