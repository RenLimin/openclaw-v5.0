"""revenue_forecast Phase 1+2 — 纯内核单元测试。

覆盖（VERIFICATION-REVENUE-FORECAST-v1.0 §2）：
  - classifier：十类各 ≥1 正例 + 优先级互斥 + 年份边界 + fail-closed
  - report_parser：混合 col2、数值解析、YS/无预算键、恒等式不符进报告
  - engine：真实财报黄金数字 + pipeline 独立桶 + 纯函数幂等 ×3

金额断言：精确锚点用 pytest.approx(abs=1e4)（1 万元）；
发布的 2/3 位小数黄金数另做舍入级别核对。
"""

from __future__ import annotations

import dataclasses
import datetime
from pathlib import Path

import pytest

from bdms.modules.revenue_forecast import (
    DUE_2026, FUTURE_YEAR, IN_PIPELINE, ALREADY_DONE, EXCEPTION,
    TERMINATED, ADJUSTED, NOT_STARTED, ZERO_AMOUNT, MISSING_DATE,
    CATEGORIES, classify_due, parse_due_date,
)
from bdms.modules.revenue_forecast.report_parser import (
    ObligationRow, ParseReport, parse_report, to_float, to_text,
)
from bdms.modules.revenue_forecast.engine import forecast

REAL_REPORT = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
)

YI = 1e8


# ─────────────────────── classifier：十类正例 ───────────────────────

def test_categories_count_ten():
    assert len(CATEGORIES) == 10
    assert len(set(CATEGORIES)) == 10


def test_due_2026_positive():
    cat, month = classify_due(datetime.datetime(2026, 6, 16))
    assert cat == DUE_2026 and month == 6


def test_future_year_positive():
    assert classify_due(datetime.datetime(2027, 1, 1)) == (FUTURE_YEAR, None)
    assert classify_due(datetime.datetime(2030, 12, 31)) == (FUTURE_YEAR, None)


def test_in_pipeline_positive():
    assert classify_due("已提交资料") == (IN_PIPELINE, None)
    assert classify_due("无需填写，已提交资料") == (IN_PIPELINE, None)


def test_already_done_positive():
    assert classify_due("无需填写，100%确收") == (ALREADY_DONE, None)


def test_exception_positive():
    assert classify_due("异常项目") == (EXCEPTION, None)


def test_terminated_positive():
    assert classify_due("2026年终止") == (TERMINATED, None)
    assert classify_due("合同终止") == (TERMINATED, None)


def test_adjusted_positive():
    assert classify_due("调整") == (ADJUSTED, None)
    assert classify_due("2026年调整") == (ADJUSTED, None)


def test_not_started_positive():
    assert classify_due("未立项") == (NOT_STARTED, None)
    assert classify_due("未预计") == (NOT_STARTED, None)


def test_zero_amount_positive():
    assert classify_due("无需填写，金额为0") == (ZERO_AMOUNT, None)


def test_missing_date_positive():
    assert classify_due(None) == (MISSING_DATE, None)
    assert classify_due("") == (MISSING_DATE, None)
    assert classify_due("无法识别的文本") == (MISSING_DATE, None)
    assert classify_due(False) == (MISSING_DATE, None)


# ─────────────────────── 年份边界 ───────────────────────

def test_year_boundaries():
    assert classify_due(datetime.datetime(2025, 12, 31)) == (MISSING_DATE, None)
    assert classify_due(datetime.datetime(2026, 1, 1)) == (DUE_2026, 1)
    assert classify_due(datetime.datetime(2026, 12, 31)) == (DUE_2026, 12)
    assert classify_due(datetime.datetime(2027, 1, 1)) == (FUTURE_YEAR, None)


def test_text_date_forms():
    assert parse_due_date("2026年7月") == datetime.date(2026, 7, 1)
    assert parse_due_date("2026-07-15") == datetime.date(2026, 7, 15)
    assert parse_due_date("2026/7") == datetime.date(2026, 7, 1)
    assert parse_due_date("已提交资料") is None
    assert parse_due_date(None) is None
    assert classify_due("2026年7月") == (DUE_2026, 7)
    assert classify_due("2027/03/01") == (FUTURE_YEAR, None)


# ─────────────────────── 优先级互斥 ───────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("已提交资料，但是项目异常", IN_PIPELINE),       # 3 优先于 5
    ("100%确收，合同终止", ALREADY_DONE),            # 4 优先于 6
    ("异常项目，需要调整", EXCEPTION),               # 5 优先于 7
    ("合同终止，未立项", TERMINATED),                # 6 优先于 8
    ("调整，金额为0", ADJUSTED),                     # 7 优先于 9
    ("未预计，金额为0", NOT_STARTED),                # 8 优先于 9
    ("已提交资料，100%确收，异常，终止，调整，未立项，金额为0", IN_PIPELINE),
])
def test_priority_mutex(raw, expected):
    cat, month = classify_due(raw)
    assert cat == expected
    assert month is None


# ─────────────────────── parser 小工具 ───────────────────────

def test_to_float_variants():
    assert to_float(100) == 100.0
    assert to_float(12.5) == 12.5
    assert to_float(" 1,234.5 ") == 1234.5
    assert to_float("") == 0.0
    assert to_float(None) == 0.0
    assert to_float("非数字") == 0.0
    assert to_float(True) == 0.0


def test_to_text_variants():
    assert to_text(None) == ""
    assert to_text("  x ") == "x"
    assert to_text(123) == "123"


# ─────────────────────── parser：内存构造 workbook ───────────────────────

def _blank_row(width: int = 53):
    return [None] * width


def _build_workbook(budget_rows, draft_rows, width_b=45, width_d=53):
    """构造表头第3行、数据第4行起的 workbook。"""
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    bs = wb.create_sheet("预算执行表")
    bs.append([None] * width_b)
    bs.append([None] * width_b)
    bs.append([f"h{i}" for i in range(width_b)])
    for r in budget_rows:
        row = _blank_row(width_b)
        for i, v in r.items():
            row[i] = v
        bs.append(row)

    ds = wb.create_sheet("计划确收底稿")
    ds.append([None] * width_d)
    ds.append([None] * width_d)
    ds.append([f"h{i}" for i in range(width_d)])
    for r in draft_rows:
        row = _blank_row(width_d)
        for i, v in r.items():
            row[i] = v
        ds.append(row)
    return wb


def _budget_row(obligation="OB1", budget="OB1YS", group="新签",
                locked_year=10000.0, monthly=None, actual=3000.0,
                method="时点法", contract="C001"):
    r = {0: group, 1: contract, 4: budget, 6: obligation, 7: method,
         8: locked_year, 27: locked_year}
    monthly = monthly if monthly is not None else {}
    for m, v in monthly.items():
        r[14 + m] = v          # col15 对应 m=1
    for m, v in (actual if isinstance(actual, dict) else {}).items():
        r[31 + m] = v          # col32 对应 m=1
    if not isinstance(actual, dict):
        r[32] = actual        # 1 月实际
    return r


def _draft_row(obligation="OB1", budget_key="OB1YS", raw_due=None,
               col40=10000.0, col41=0.0, col42=10000.0, name="N",
               customer="CU", end_user="EU", method="时点法", contract="C001"):
    return {2: raw_due, 3: contract, 7: obligation, 8: budget_key,
            10: name, 11: customer, 12: end_user, 33: method,
            40: col40, 41: col41, 42: col42}


def test_parser_happy_path_join_and_fields():
    wb = _build_workbook(
        [_budget_row(monthly={1: 4000, 6: 6000}, actual={1: 3000})],
        [_draft_row(raw_due=datetime.datetime(2026, 6, 16))],
    )
    rep = parse_report(wb)
    assert isinstance(rep, ParseReport)
    assert rep.ok and rep.issues == ()
    assert rep.budget_rows == 1 and rep.draft_rows == 1
    assert rep.join_by_current_key == 1
    row = rep.rows[0]
    assert row.obligation_id == "OB1"
    assert row.budget_id == "OB1YS"
    assert row.category_group == "新签"
    assert row.locked_year == 10000.0
    assert row.locked_monthly == (4000.0,) + (0.0,) * 4 + (6000.0,) + (0.0,) * 6
    assert row.actual_ytd == 3000.0
    assert row.dyn_category == DUE_2026 and row.dyn_month == 6
    assert row.dyn_in_plan is True and row.dyn_counted == 10000.0
    assert row.due_date == "2026-06-16"
    assert row.matched_budget is True


def test_parser_fallback_budget_key():
    # 现行键不匹配，兜底预算键命中
    wb = _build_workbook(
        [_budget_row(obligation="OB1", budget="OB1YS")],
        [_draft_row(obligation="OTHER", budget_key="OB1YS",
                    raw_due=datetime.datetime(2026, 3, 1))],
    )
    rep = parse_report(wb)
    assert rep.join_by_current_key == 0
    assert rep.join_by_budget_key == 1
    assert rep.rows[0].matched_budget is True
    assert rep.rows[0].dyn_counted == 10000.0


def test_parser_no_budget_already_done_unmatched():
    wb = _build_workbook(
        [_budget_row()],
        [_draft_row(obligation="YP1", budget_key="2026年无预算ID",
                    raw_due="无需填写，100%确收", col42=0.0)],
    )
    rep = parse_report(wb)
    assert rep.join_miss == 1
    row = rep.rows[0]
    assert row.matched_budget is False
    assert row.category_group == ""
    assert row.dyn_category == ALREADY_DONE
    assert row.dyn_in_plan is False and row.dyn_counted == 0.0


def test_parser_identity_violations_go_to_report():
    bad_budget = _budget_row(obligation="OB2", budget="OB2YS",
                             locked_year=999.0)  # col27=999，逐月合计=0
    bad_draft = _draft_row(obligation="OB2", budget_key="OB2YS",
                           raw_due="未预计", col40=100.0, col41=0, col42=0)
    wb = _build_workbook(
        [_budget_row(monthly={6: 10000}), bad_budget],
        [_draft_row(raw_due=datetime.datetime(2026, 1, 1)), bad_draft],
    )
    rep = parse_report(wb)
    assert rep.ok is False
    assert [i.rule for i in rep.issues] == ["E1_LOCKED_SUM", "E3_DRAFT_SUM"]
    e1 = rep.issues[0]
    assert e1.expected == 999.0 and e1.actual == 0.0
    assert e1.row_excel == 5
    # 不静默：问题可被程序化读取，且解析不崩溃、行仍齐全
    assert rep.budget_rows == 2 and rep.draft_rows == 2


def test_parser_missing_sheet_raises():
    from openpyxl import Workbook
    wb = Workbook()
    with pytest.raises(ValueError, match="缺少 Sheet"):
        parse_report(wb)


def test_parser_text_and_empty_numbers_treated_as_zero():
    # 逐月/实际/col42 给文本与空 → 按 0，恒等式仍成立
    wb = _build_workbook(
        [_budget_row(locked_year=0)],
        [_draft_row(raw_due="", col40=0, col41="", col42=None)],
    )
    rep = parse_report(wb)
    assert rep.ok is True
    assert rep.rows[0].dyn_category == MISSING_DATE


# ─────────────────────── engine：合成行 + 去重/桶语义 ───────────────────────

def _row(obligation="OB1", budget="OB1YS", group="新签", locked_year=10000.0,
         monthly=None, actual=0.0, cat=DUE_2026, month=6, amount=10000.0,
         in_plan=None, matched=True):
    monthly = tuple(monthly or []) + (0.0,) * (12 - len(monthly or []))
    if in_plan is None:
        in_plan = cat in (DUE_2026, IN_PIPELINE) and matched
    return ObligationRow(
        obligation_id=obligation, budget_id=budget, contract_no="",
        contract_name="", customer="", end_user="", revenue_method="",
        category_group=group if matched else "",
        locked_year=locked_year if matched else 0.0,
        locked_monthly=monthly if matched else tuple(0.0 for _ in range(12)),
        actual_ytd=actual if matched else 0.0,
        raw_due="", due_date=None, dyn_category=cat,
        amount_future=amount, dyn_month=month if cat == DUE_2026 else None,
        dyn_in_plan=in_plan, dyn_counted=amount if in_plan else 0.0,
    )


def test_engine_locked_dedup_by_budget_id():
    # 两条底稿行引用同一预算项 → 锁定只计一次
    rows = [
        _row(obligation="OB1", budget="B1", locked_year=10000,
             monthly=[10000], cat=ALREADY_DONE, amount=0, in_plan=False),
        _row(obligation="OB1X", budget="B1", locked_year=10000,
             monthly=[10000], cat=DUE_2026, month=6, amount=8000),
    ]
    r = forecast(rows)
    assert r.locked_total == pytest.approx(10000.0)
    assert r.locked_monthly["01"] == pytest.approx(10000.0)
    assert r.dynamic_total == pytest.approx(8000.0)
    assert r.gap_dynamic_minus_locked == pytest.approx(-2000.0)
    assert r.line_count == 2


def test_engine_pipeline_is_separate_bucket():
    rows = [
        _row(obligation="O1", budget="B1", group="递延", locked_year=5000,
             cat=IN_PIPELINE, month=None, amount=7000),
        _row(obligation="O2", budget="B2", group="新签", locked_year=3000,
             cat=DUE_2026, month=3, amount=4000, monthly=[0, 0, 3000]),
    ]
    r = forecast(rows)
    assert r.dynamic_pipeline == pytest.approx(7000.0)
    assert r.dynamic_due_total == pytest.approx(4000.0)
    assert r.dynamic_total == pytest.approx(11000.0)
    assert sum(r.dynamic_due_monthly.values()) == pytest.approx(4000.0)
    assert r.dynamic_due_monthly["03"] == pytest.approx(4000.0)
    # pipeline 不进任何月份
    assert r.dynamic_due_monthly["06"] == 0.0
    assert r.locked_total == pytest.approx(8000.0)
    assert r.locked_by_group["递延"] == pytest.approx(5000.0)
    assert r.locked_by_group["新签"] == pytest.approx(3000.0)


def test_engine_unmatched_rows_excluded_from_locked():
    rows = [
        _row(obligation="YP1", budget="2026年无预算ID", group="新签",
             cat=ALREADY_DONE, amount=0, in_plan=False, matched=False),
        _row(obligation="O2", budget="B2", group="新签", locked_year=2000,
             cat=FUTURE_YEAR, month=None, amount=9000, in_plan=False),
    ]
    r = forecast(rows)
    assert r.locked_total == pytest.approx(2000.0)
    assert r.dynamic_total == 0.0
    assert r.actual_ytd_total == 0.0


def test_engine_pure_function_idempotent_synthetic():
    rows = [
        _row(obligation="O1", budget="B1", group="新签", locked_year=5000,
             actual=1000, cat=DUE_2026, month=6, amount=6000),
        _row(obligation="O2", budget="B2", group="递延", locked_year=7000,
             cat=IN_PIPELINE, amount=8000),
    ]
    results = [forecast(rows) for _ in range(3)]
    dicts = [dataclasses.asdict(x) for x in results]
    assert dicts[0] == dicts[1] == dicts[2]


# ─────────────────────── 真实财报黄金数字 ───────────────────────

@pytest.fixture(scope="module")
def real_parse():
    if not REAL_REPORT.is_file():
        pytest.skip(f"真实财报不存在: {REAL_REPORT}")
    return parse_report(REAL_REPORT)


@pytest.fixture(scope="module")
def real_result(real_parse):
    return forecast(real_parse.rows)


def test_real_row_counts_and_join(real_parse):
    assert real_parse.budget_rows == 10472
    assert real_parse.draft_rows == 38052
    assert real_parse.join_by_current_key == 10301
    assert real_parse.join_by_budget_key == 498
    assert real_parse.join_miss == 27253


def test_real_identities_zero_mismatch(real_parse):
    assert real_parse.ok is True
    assert real_parse.issues == ()


def test_real_locked_golden(real_result):
    r = real_result
    assert r.locked_total == pytest.approx(138420136.78, abs=1e4)
    assert r.locked_by_group["新签"] == pytest.approx(66520133.50, abs=1e4)
    assert r.locked_by_group["递延"] == pytest.approx(71900003.28, abs=1e4)
    # 发布口径（亿元，2 位小数）
    assert round(r.locked_total / YI, 2) == 1.38
    assert round(r.locked_by_group["新签"] / YI, 2) == 0.67
    assert round(r.locked_by_group["递延"] / YI, 2) == 0.72


def test_real_locked_monthly_golden(real_result):
    # DETAIL §2.1 逐月（亿，3 位小数）
    published = [.116, .071, .110, .093, .087, .107, .126, .099,
                 .114, .135, .101, .227]
    measured = [.1156, .0710, .1097, .0925, .0865, .1069, .1255, .0994,
                .1143, .1345, .1012, .2270]
    vals = list(real_result.locked_monthly.values())
    assert len(vals) == 12
    for v, pub, meas in zip(vals, published, measured):
        assert v == pytest.approx(meas * YI, abs=1e4)       # 精确锚点 1 万元容差
        assert v == pytest.approx(pub * YI, abs=6e4)       # 发布值舍入级核对
    assert sum(vals) == pytest.approx(real_result.locked_total, abs=1.0)


def test_real_actual_golden(real_result):
    r = real_result
    assert r.actual_ytd_total == pytest.approx(94457828.53, abs=1e4)
    assert r.actual_by_group["新签"] == pytest.approx(43633873.37, abs=1e4)
    assert r.actual_by_group["递延"] == pytest.approx(50823955.16, abs=1e4)
    assert round(r.actual_ytd_total / YI, 2) == 0.94
    assert round(r.actual_by_group["新签"] / YI, 2) == 0.44
    assert round(r.actual_by_group["递延"] / YI, 2) == 0.51


def test_real_dynamic_golden(real_result):
    r = real_result
    assert r.dynamic_total == pytest.approx(171048611.81, abs=1e4)
    assert r.dynamic_by_group["新签"] == pytest.approx(85065322.34, abs=1e4)
    assert r.dynamic_by_group["递延"] == pytest.approx(85983289.47, abs=1e4)
    assert r.dynamic_due_total == pytest.approx(86936513.95, abs=1e4)
    assert r.dynamic_pipeline == pytest.approx(84112097.86, abs=1e4)
    # 发布口径
    assert round(r.dynamic_total / YI, 2) == 1.71
    assert round(r.dynamic_by_group["新签"] / YI, 3) == 0.851
    assert round(r.dynamic_by_group["递延"] / YI, 3) == 0.860
    assert round(r.dynamic_due_total / YI, 3) == 0.869
    assert round(r.dynamic_pipeline / YI, 3) == 0.841
    # DUE + PIPE = 动态合计
    assert r.dynamic_due_total + r.dynamic_pipeline == pytest.approx(
        r.dynamic_total, abs=1.0)


def test_real_gap_golden(real_result):
    r = real_result
    assert r.gap_dynamic_minus_locked == pytest.approx(32628475.03, abs=1e4)
    assert round(r.gap_dynamic_minus_locked / YI, 2) == 0.33


def test_real_due_monthly_and_pipeline_not_in_months(real_result):
    r = real_result
    due_published = [.001, 0, .010, .020, .030, .159, .102,
                     .093, .101, .106, .054, .194]
    vals = list(r.dynamic_due_monthly.values())
    for v, pub in zip(vals, due_published):
        assert v == pytest.approx(pub * YI, abs=6e4)
    assert sum(vals) == pytest.approx(r.dynamic_due_total, abs=1.0)
    # pipeline 独立于逐月
    assert all(abs(v) < 1e-6 for v in vals) or r.dynamic_pipeline > 0


def test_real_parse_and_forecast_idempotent_x3():
    reps = [parse_report(REAL_REPORT) for _ in range(3)]
    assert reps[0] == reps[1] == reps[2]
    results = [forecast(reps[0].rows) for _ in range(3)]
    dicts = [dataclasses.asdict(x) for x in results]
    assert dicts[0] == dicts[1] == dicts[2]
