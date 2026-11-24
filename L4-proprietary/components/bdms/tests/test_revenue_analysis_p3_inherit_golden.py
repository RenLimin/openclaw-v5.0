"""P3 · Q3 跨期继承 真实源回归（DESIGN-DETAIL §4.1 自证口径）

锁定设计文档 §4.1 的实证数字：
  202606 预算执行表逐行继承 202605 → 8062 行继承、其中 4 行人工改判
  （例：XSZS2605180322 上期「本年度正常可确收」→ 本期「已下单但无法交付」）
带 manual_override 后须与 202606 源表现存 BU **零差异**。

口径红线：DB 行键是规范字母（G=履约ID、BU=预算趋势），不是 Excel 物理列位。
"""

from pathlib import Path

import pytest

from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine

SRC = Path("/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告")
S25 = SRC / "202605" / (
    "2026年计划确收&实际确收对比表202601-05-0627-差异分析.xlsx")
S26 = SRC / "202606" / (
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx")

pytestmark = pytest.mark.skipif(
    not (S25.exists() and S26.exists()), reason="202605/202606 财报未就位")


@pytest.fixture(scope="module")
def eng():
    e = RevenueAnalysisEngine(pytest.tmp_path_factory.mktemp("p3inh") / "g.db"
                             if hasattr(pytest, "tmp_path_factory") else None)
    return e


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    db = tmp_path_factory.mktemp("p3inh") / "golden.db"
    e = RevenueAnalysisEngine(db)
    e.import_source("202605", S25)
    e.import_source("202606", S26)
    r1 = e.inherit_previous_buckets("202606")
    overrides = {s["perf_id"]: s["source"]
                 for s in r1["audit_vs_source"]["samples"]}
    r2 = e.inherit_previous_buckets("202606", manual_override=overrides)
    e.persist_buckets("202606", r2)
    return {"first": r1, "final": r2, "engine": e}


def test_section_4_1_counts(result):
    """§4.1：8058 继承 + 4 人工改判 = 8062。"""
    f = result["final"]
    assert f["inherited"] == 8058
    assert f["overridden"] == 4
    assert f["inherited"] + f["overridden"] == 8062


def test_four_overrides_are_documented_example(result):
    """差异应落在 §4.1 举例的合同 XSZS2605180322 上。"""
    ids = sorted(s["perf_id"] for s in result["first"]["audit_vs_source"]["samples"])
    assert ids == [
        "XSZS2605180322_01_01_001", "XSZS2605180322_01_01_002",
        "XSZS2605180322_01_02_001", "XSZS2605180322_01_02_002",
    ]


def test_final_matches_source_zero_diff(result):
    a = result["final"]["audit_vs_source"]
    assert a["disagree"] == 0
    assert a["agree"] == 8062


def test_persist_roundtrip(result):
    buckets = result["engine"].load_buckets("202606")
    assert len(buckets) == 8062
    assert buckets["XSZS2605180322_01_01_001"] == "已下单但无法交付"


def test_manual_override_wins_over_inheritance(result):
    """优先级 ① > ②：显式改判不得被上期值覆盖。"""
    first = result["first"]
    # 首轮这些 ID 被继承为「本年度正常可确收」
    assert first["result"]["XSZS2605180322_01_01_001"] == "本年度正常可确收"
    assert result["final"]["result"]["XSZS2605180322_01_01_001"] == \
        "已下单但无法交付"
