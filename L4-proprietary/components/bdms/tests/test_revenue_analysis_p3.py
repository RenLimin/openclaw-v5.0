"""revenue_analysis Phase 3 — 双口径构建器 + 趋势构建器 + ra_* 落盘单元测试。

覆盖（DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §5/§6/§8.1 + VERIFICATION 红线）：
  - CaliberBuilder：锁定 by_group/by_month、动态权威分类、字符串日期归一化、
    by_group 关联（H 现行键 / I 预算键兜底）、MISSING 不计入口径
  - TrendBuilder：19 行 row_index 映射、R19 特殊单元格、合计行路由、未知行跳过
  - engine.compute_dual_caliber：黄金锚点（锁定 1.3842 亿 / 动态 1.7105 亿 / 差异 .3263 亿）
  - 幂等：同输入连跑 3 次逐字段相等
  - 金额红线：J/K/L 全 0 → trend 金额一律 None，不硬摊
"""

from __future__ import annotations

import datetime
import json

import pytest

from bdms.modules.revenue_analysis.caliber_builder import (
    CaliberBuilder, normalize_due,
)
from bdms.modules.revenue_analysis.trend_builder import TrendBuilder

# ─────────────────────── normalize_due：字符串日期归一化 ───────────────────────

def test_normalize_due_iso_with_time():
    v = normalize_due("2026-12-31 00:00:00")
    assert isinstance(v, datetime.datetime)
    assert v.year == 2026 and v.month == 12 and v.day == 31


def test_normalize_due_plain_iso():
    v = normalize_due("2026-06-25")
    assert isinstance(v, datetime.datetime)
    assert v.month == 6


def test_normalize_due_keeps_non_iso_text():
    assert normalize_due("已提交资料") == "已提交资料"
    assert normalize_due(None) is None
    assert normalize_due(123) == 123


def test_normalize_due_keeps_datetime():
    dt = datetime.datetime(2026, 7, 1, 9, 0)
    assert normalize_due(dt) is dt


# ─────────────────────── CaliberBuilder：锁定 ───────────────────────

def _budget_row(cat, ab, months=None):
    row = {"A": cat, "AB": ab, "G": "", "E": ""}
    for i, k in enumerate(PLAN_KEYS):
        col = chr(ord("P") + i)
        row[col] = (months or {}).get(k, 0.0)
    return row

PLAN_KEYS = ("202601", "202602", "202603")


def test_locked_group_and_month():
    rows = [
        _budget_row("新签", 100.0, {"202601": 40.0, "202602": 60.0}),
        _budget_row("递延", 50.0, {"202601": 50.0}),
        _budget_row("未知分类", 999.0),  # 不入口径
    ]
    snap = CaliberBuilder().build_locked(rows)
    assert snap["total"] == 150.0
    assert snap["by_group"] == {"新签": 100.0, "递延": 50.0}
    assert snap["by_month"]["202601"] == 90.0
    assert snap["by_month"]["202602"] == 60.0
    assert snap["by_month"]["202603"] == 0.0


# ─────────────────────── CaliberBuilder：动态 ───────────────────────

def _draft_row(c, aq, h="", i=""):
    return {"C": c, "AQ": aq, "H": h, "I": i}


def test_dynamic_due_pipeline_split():
    budget = [_budget_row("新签", 0.0), _budget_row("递延", 0.0)]
    budget[0]["G"] = "PERF-N"
    budget[1]["G"] = "PERF-D"
    draft = [
        _draft_row(datetime.datetime(2026, 6, 16), 100.0, "PERF-N"),
        _draft_row("已提交资料", 50.0, "PERF-D"),
        _draft_row("2027-05-01 00:00:00", 30.0, "PERF-N"),  # 跨年不计
        _draft_row(None, 20.0, "PERF-D"),                    # 缺日期不计
        _draft_row("", 10.0, "PERF-N"),                      # AQ 计入但缺日期
    ]
    snap = CaliberBuilder().build_dynamic(budget, draft)
    assert snap["total"] == 150.0
    assert snap["due_total"] == 100.0
    assert snap["pipeline"] == 50.0
    assert snap["other_2027plus"] == 30.0
    assert snap["missing_amount"] == 30.0
    assert snap["missing_rows"] == 2
    assert snap["by_group"] == {"新签": 100.0, "递延": 50.0}
    assert snap["by_month"]["202606"] == 100.0


def test_dynamic_group_fallback_budget_key():
    budget = [_budget_row("新签", 0.0)]
    budget[0]["E"] = "YS-BUDGET-1"  # 预算键，非现行键
    draft = [_draft_row("已提交资料", 77.0, "H-UNKNOWN", "YS-BUDGET-1")]
    snap = CaliberBuilder().build_dynamic(budget, draft)
    assert snap["by_group"]["新签"] == 77.0


def test_dynamic_group_miss_kept_out():
    budget = [_budget_row("新签", 0.0)]
    draft = [_draft_row("已提交资料", 55.0, "NO-MATCH", "NO-BUDGET")]
    snap = CaliberBuilder().build_dynamic(budget, draft)
    assert snap["by_group"] == {"新签": 0.0, "递延": 0.0}
    assert snap["pipeline"] == 55.0  # 金额仍计入 pipeline 桶


def test_dynamic_zero_aq_skipped():
    draft = [_draft_row("已提交资料", 0.0, "X")]
    snap = CaliberBuilder().build_dynamic([], draft)
    assert snap["total"] == 0.0
    assert snap["missing_rows"] == 0


# ─────────────────────── TrendBuilder：行映射 ───────────────────────

def _trend_line(group, label, counts=None):
    c = counts or {}
    return {
        "group": group, "row_label": label,
        "init_count": c.get("init", 0), "init_amount_wan": None,
        "normal_count": c.get("normal", 0), "normal_amount_wan": None,
        "exception_count": c.get("exception", 0), "exception_amount_wan": None,
        "disappear_count": c.get("disappear", 0), "disappear_amount_wan": None,
        "future_count": c.get("future", 0), "future_amount_wan": None,
        "check_count": c.get("init", 0), "check_amount": None,
        "note_unplan": None, "note_planned": None,
        "routing_audit": {"excluded_total_row": 0, "unfilled": 0},
        "amount_pending": "A/B/C 待拍板",
    }


def test_trend_row_index_mapping():
    lines = [
        _trend_line("递延", "已归档但未下单", {"init": 6}),
        _trend_line("递延", "合计", {"init": 6}),
        _trend_line("新签", "本年度正常可确收", {"init": 876}),
        _trend_line("新签", "合计", {"init": 876}),
        _trend_line("全部", "合计", {"init": 882}),
    ]
    rows, cells = TrendBuilder().build(lines)
    idx = {r["row_index"]: r for r in rows}
    assert idx[4]["status"] == "已归档但未下单"
    assert idx[10]["status"] == "合计" and idx[10]["category_group"] == "递延"
    assert idx[15]["init_count"] == 876
    assert idx[17]["category_group"] == "新签"
    assert idx[18]["category_group"] == "全部"
    assert cells == []  # 无 R19


def test_trend_r19_rate_cell():
    line = _trend_line("新签", "新签预计确收率",
                       {"init": 100, "normal": 60})
    line["recognize_rate_count"] = 0.6
    line["recognize_rate_amount"] = None
    rows, cells = TrendBuilder().build([line])
    assert rows[0]["row_index"] == 19
    assert len(cells) == 2
    count_cell = json.loads(cells[0]["value"])
    assert count_cell["kind"] == "recognize_rate_count"
    assert count_cell["value"] == 0.6
    amount_cell = json.loads(cells[1]["value"])
    assert amount_cell["value"] is None  # 金额红线待拍板


def test_trend_unknown_row_skipped():
    rows, cells = TrendBuilder().build([_trend_line("未知", "不存在")])
    assert rows == [] and cells == []


def test_trend_amount_redline_none():
    """202609 J/K/L 全 0 红线：金额列一律 None，不硬摊不造假。"""
    lines = [_trend_line("递延", "已归档但未下单", {"init": 6})]
    rows, _ = TrendBuilder().build(lines)
    assert rows[0]["init_amount_wan"] is None
    assert rows[0]["normal_amount_wan"] is None
    assert rows[0]["exception_amount_wan"] is None
    assert rows[0]["disappear_amount_wan"] is None
    assert rows[0]["future_amount_wan"] is None
    assert rows[0]["check_amount"] is None
    assert rows[0]["amount_pending"] == "A/B/C 待拍板"
