"""P3 分桶引擎 · 切片1：Q3 跨期继承（DESIGN-DETAIL v1.1 §4）

口径（Rex 确认）：① 本期人工改判 > ② 按履约ID继承上期 BU 桶 > ③ 留空待规则引擎
红线（§4.2）：上期/本期数据缺失 → fail-closed 抛错，不推断、不伪造。
"""

import pytest

from bdms.modules.base import ImportError_
from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine


# ⚠️ 规范字母（config.BUDGET_CANONICAL_FROM_202606）：履约ID=G（Excel 物理列 J）、
#    预算趋势=BU。DB 行键是规范字母，不是 Excel 物理列位。
PERF_KEY, BUCKET_KEY = "G", "BU"


def _row(pid, bu):
    return {PERF_KEY: pid, BUCKET_KEY: bu}


@pytest.fixture
def eng(tmp_path):
    return RevenueAnalysisEngine(tmp_path / "p3.db")


# ─── 账期回退 ───

@pytest.mark.parametrize("cur,prev", [
    ("202606", "202605"), ("202609", "202608"),
    ("202601", "202512"), ("202701", "202612"),
])
def test_prev_period(eng, cur, prev):
    assert eng._prev_period(cur) == prev


# ─── 继承逻辑 ───

def _seed(eng, period_rows, prev_rows):
    """用合成行替代真实宽表读取（本切片只验算法，不验导入）。"""
    eng._load_sheet_rows = lambda p, sheet: (
        prev_rows if p == "202605" else period_rows)


def test_inherit_priority_order(eng):
    """人工改判 > 跨期继承 > 留空。"""
    cur = [_row("A1", ""), _row("A2", ""), _row("A3", ""), _row("", "")]
    prev = [_row("A1", "本年度正常可确收"), _row("A2", "异常中"), _row("A9", "未来交付")]
    _seed(eng, cur, prev)
    r = eng.inherit_previous_buckets("202606",
                                     manual_override={"A2": "已下单但无法交付"})
    assert r["inherited"] == 1 and r["overridden"] == 1 and r["blank"] == 1
    assert r["result"]["A1"] == "本年度正常可确收"      # 继承
    assert r["result"]["A2"] == "已下单但无法交付"       # 改判覆盖
    assert "A3" not in r["result"] and "A3" in r["missing_prev_ids"]
    assert r["total"] == 3                              # A1/A2/A3；无ID行不计
    assert r["total"] == r["inherited"] + r["overridden"] + r["blank"]


def test_fail_closed_when_prev_missing(eng):
    """《上期差异表》缺失 → 报错，不伪造。"""
    _seed(eng, [_row("A1", "")], [])
    with pytest.raises(ImportError_) as ei:
        eng.inherit_previous_buckets("202606")
    assert "202605" in str(ei.value)


def test_fail_closed_when_current_missing(eng):
    """本期预算执行表缺失 → 报错。"""
    _seed(eng, [], [_row("A1", "本年度正常可确收")])
    with pytest.raises(ImportError_) as ei:
        eng.inherit_previous_buckets("202606")
    assert "202606" in str(ei.value)


def test_cold_start_prev_file_absent_is_fail_closed(eng):
    """冷启动：《上期差异表》整表不存在 → fail-closed（§4.2「报错，不伪造」）。

    注意与「上期表存在、但该行无值」区分：后者才是 §3.2 的 7 桶规则场景
    （本切片只负责留空，不跑规则）。
    """
    _seed(eng, [_row("A1", ""), _row("A2", "")], [])
    with pytest.raises(ImportError_):
        eng.inherit_previous_buckets("202606")


def test_prev_table_present_but_row_unvalued_is_blank(eng):
    """上期表存在、该履约ID无值 → 留空（交由 §3 规则引擎，不在本切片断言）。"""
    cur = [_row("NEW1", "")]
    prev = [_row("OLD1", "本年度正常可确收")]   # 表存在，但无 NEW1
    _seed(eng, cur, prev)
    r = eng.inherit_previous_buckets("202606")
    assert r["inherited"] == 0 and r["blank"] == 1
    assert r["missing_prev_ids"] == ["NEW1"]


# ─── 落库与回读（下一期继承源）───

def test_persist_and_load_roundtrip(eng):
    r = {"period": "202606", "prev": "202605", "inherited": 2,
         "result": {"A1": "本年度正常可确收", "A2": "合同消失"}}
    w = eng.persist_buckets("202606", r)
    assert w["written"] == 2 and w["source"].startswith("inherit:")
    got = eng.load_buckets("202606")
    assert got == {"A1": "本年度正常可确收", "A2": "合同消失"}


def test_persist_overwrites_same_period(eng):
    """重复生成不得累积旧行。"""
    eng.persist_buckets("202606", {"inherited": 1, "prev": "202605",
                                   "result": {"A1": "X"}})
    eng.persist_buckets("202606", {"inherited": 1, "prev": "202605",
                                   "result": {"A2": "Y"}})
    assert eng.load_buckets("202606") == {"A2": "Y"}
