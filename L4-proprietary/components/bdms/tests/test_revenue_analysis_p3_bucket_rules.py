"""P3 分桶引擎 · 切片2：§3 七桶规则引擎（DESIGN-DETAIL v1.1 §3）

口径依据：
- §3.1 所有记录都应有值；上期为空 → 按 7 桶预定义规则自动判定
- §3.4 优先级：合同消失 > 已归档但未下单 > 已下单但无法交付 >
  已交付但无法确收 > 未来可确收 > 之前年度已确收 > 本年度正常可确收
- §3.5 fail-closed：任一信号源缺失 → 留空 + 提示人工校验，禁止用其他列推断
"""

import pytest

from bdms.modules.base import ImportError_
from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine as E


@pytest.fixture
def eng(tmp_path):
    return E(tmp_path / "p3r.db")


# ─── 辅助解析 ───

def test_year_of_variants(eng):
    assert eng._year_of(202612) == 2026
    assert eng._year_of("2026-05-01") == 2026
    assert eng._year_of("2027年") == 2027
    assert eng._year_of(None) is None and eng._year_of("") is None


def test_is_yes_normalization(eng):
    assert eng._is_yes("是") is True and eng._is_yes("y") is True
    assert eng._is_yes("否") is False and eng._is_yes("n") is False
    assert eng._is_yes(None) is None and eng._is_yes("未知") is None


# ─── BU 规则（§3.3）───

def test_bu_disappear_wins(eng):
    """合同消失最高优先（§3.4）。"""
    j = eng.judge_bucket("BU", at="合同终止", bx=202612, year=2026)
    assert j["bucket"] == "合同消失" and j["rule"] == "at_contract_terminated"


def test_bu_future_when_bx_after_year(eng):
    j = eng.judge_bucket("BU", bx=202701, year=2026)
    assert j["bucket"] == "未来可确收" and j["rule"] == "bx_after_year"


def test_bu_normal_when_bx_in_year(eng):
    j = eng.judge_bucket("BU", bx=202612, year=2026)
    assert j["bucket"] == "本年度正常可确收" and j["rule"] == "bx_in_year"


def test_bu_prior_year_rule_not_defined(eng):
    """§3.3「之前年度已确收」Rex 未给规则 → 留空，不得推断。"""
    j = eng.judge_bucket("BU", bx=202501, year=2026)
    assert j["bucket"] is None and j["rule"] == "unresolved"


def test_bu_missing_bx_is_fail_closed(eng):
    j = eng.judge_bucket("BU", bx=None, year=2026)
    assert j["bucket"] is None
    assert "bx" in j["missing_signals"]


# ─── BQ 规则（§3.2）───

def test_bq_ordered_unmatched(eng):
    j = eng.judge_bucket("BQ", oa_ordered=True, ones_matched=False, year=2026)
    assert j["bucket"] == "已下单但无法交付"


def test_bq_unordered_unmatched(eng):
    j = eng.judge_bucket("BQ", oa_ordered=False, ones_matched=False, year=2026)
    assert j["bucket"] == "已归档但未下单"


def test_bq_delivered_exception(eng):
    j = eng.judge_bucket("BQ", ones_matched=True, bf="3：交付异常", year=2026)
    assert j["bucket"] == "已交付但无法确收"


def test_bq_plan_date_rules(eng):
    assert eng.judge_bucket(
        "BQ", plan_start=202603, plan_end=202609, plan_finish=202609,
        year=2026)["bucket"] == "本年度正常可确收"
    assert eng.judge_bucket(
        "BQ", plan_start=202701, plan_end=202712, plan_finish=202712,
        year=2026)["bucket"] == "未来可确收"
    assert eng.judge_bucket(
        "BQ", plan_start=202501, plan_end=202512, plan_finish=202512,
        year=2026)["bucket"] == "之前年度已确收"


def test_bq_priority_disappear_over_ordered(eng):
    """§3.4：合同消失压过「已下单但无法交付」。"""
    j = eng.judge_bucket("BQ", at="合同终止",
                         oa_ordered=True, ones_matched=False, year=2026)
    assert j["bucket"] == "合同消失"


def test_bq_external_signal_unknown_is_blank(eng):
    """OA/ONES 未接入 → ②③④ 全不参与判定（fail-closed）。"""
    j = eng.judge_bucket("BQ", plan_start=202603, year=2026)
    assert j["bucket"] == "本年度正常可确收"       # 仍可由计划时间判定
    assert set(j["missing_signals"]) == {"oa_ordered", "ones_matched"}
    j2 = eng.judge_bucket("BQ", year=2026)         # 无任何可用信号
    assert j2["bucket"] is None


# ─── 落库 ───

def test_save_entry_upsert_no_clobber(eng):
    """同键再写不得清空已有列。"""
    eng.save_bucket_entry("202606", "A1", trend="未来可确收", rule="bx_after_year")
    eng.save_bucket_entry("202606", "A1", fill="本年度正常可确收",
                          rule="plan_in_year")
    conn = __import__("sqlite3").connect(eng.db_path)
    row = conn.execute(
        "SELECT budget_fill, budget_trend FROM ra_bucket "
        "WHERE period='202606' AND perf_id='A1'").fetchone()
    conn.close()
    assert tuple(row) == ("本年度正常可确收", "未来可确收")


# ─── apply_bucket_rules 集成（合成行）───

def _seed(eng, rows, existing=None):
    eng._load_sheet_rows = lambda p, s: rows
    if existing:
        for pid, b in existing.items():
            eng.save_bucket_entry("202606", pid, trend=b)


def test_apply_skips_existing_and_fills_new(eng):
    rows = [
        {"G": "OLD", "B": "C1"},                       # 已继承 → 跳过
        {"G": "NEW", "B": "C2", "BX": 202701},         # BX 明年 → 未来可确收
        {"G": "UNK", "B": "C3"},                       # 无信号 → 留空
    ]
    _seed(eng, rows, existing={"OLD": "本年度正常可确收"})
    r = eng.apply_bucket_rules("202606")
    assert r["stats"].get("skipped_existing") == 1
    assert r["results"] == {"NEW": "未来可确收"}
    assert [u["perf_id"] for u in r["unresolved"]] == ["UNK"]
    assert r["stats"]["unresolved"] == 1
    # 落库可回读
    assert eng.load_buckets("202606") == {"OLD": "本年度正常可确收",
                                          "NEW": "未来可确收"}


def test_apply_fail_closed_on_missing_sheet(eng):
    eng._load_sheet_rows = lambda p, s: []
    with pytest.raises(ImportError_):
        eng.apply_bucket_rules("202606")


def test_apply_cannot_override_inherited_value(eng):
    """红线：规则引擎不得覆盖已继承/人工值。"""
    rows = [{"G": "X", "B": "C9", "BX": 202701}]
    _seed(eng, rows, existing={"X": "合同消失"})
    r = eng.apply_bucket_rules("202606")
    assert r["newly_bucketed"] == 0 and r["results"] == {}
    assert eng.load_buckets("202606")["X"] == "合同消失"
