"""P7 · 预测模型 + 年度目标（DESIGN-DETAIL v1.1 §8.3 / IMPLEMENTATION-PLAN §10）

覆盖：
- 单位红线：CaliberBuilder/ra_caliber 为元，输出统一万元（边界一次性换算）
- 差距公式：目标 −（实际达成 + 锁定 + future 桶）
- future 桶只统计已落库『未来可确收』行，金额按分类取权威列
- 四类风险清单 fail-closed 且与 apply_bucket_rules 证据自洽
- 服务层无数据 fail-closed 空结构
- 集成锚点：真实源 202606/202609 锁定/动态与 ra_caliber 冻结值零差异
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bdms.modules.base import ImportError_
from bdms.modules.revenue_analysis.engine import RevenueAnalysisEngine
from bdms.modules.revenue_analysis.forecast_engine import (
    ForecastEngine,
)
from bdms.modules.revenue_analysis.service import RevenueAnalysisService

REAL_202606 = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx")
REAL_202609 = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx")


@pytest.fixture
def eng(tmp_path):
    return RevenueAnalysisEngine(tmp_path / "p7.db")


def _fe(eng, *, budget_rows, draft_rows, actual_wan=0.0, signals=None):
    """受控替身：替换取数方法，保留真实 caliber_builder / 分桶常量。

    返回 ForecastEngine（`_actual_ytd_wan` 定义在 FE 上，须打在实例）。
    """
    eng._load_budget_rows = lambda p: list(budget_rows)
    eng._load_draft_rows = lambda p: list(draft_rows)

    def _sig(p):
        if signals is not None:
            return signals
        return {"period": p, "available": True, "missing_sources": [],
                "coverage": {"budget_contracts": 0, "oa_known": 0}}
    eng.load_bucket_signals = _sig
    fe = ForecastEngine(eng)
    fe._actual_ytd_wan = lambda p, b: float(actual_wan)
    return fe


def _put_bucket(eng, period, perf_id, fill=None, trend=None):
    conn = sqlite3.connect(eng.db_path)
    conn.execute(
        """INSERT INTO ra_bucket (period, perf_id, budget_fill, budget_trend,
                                  bucket_source, created_at)
           VALUES (?,?,?,?,?,datetime('now'))""",
        (period, perf_id, fill, trend, "test"))
    conn.commit()
    conn.close()


# ─── 单位 + 差距 ───

def test_unit_conversion_and_gap(eng):
    """口径为元、输出为万元；差距 = 目标 −（实际 + 锁定 + future）。"""
    fe = _fe(eng,
             budget_rows=[{"G": "F1", "A": "递延", "AB": 10000.0, "K": 1000.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}],
             actual_wan=500.0)
    eng.set_annual_target(2026, 10000.0)
    _put_bucket(eng, "202606", "F1", fill="未来可确收")
    r = fe.forecast("202606")
    assert r["unit"] == "万元"
    assert r["calibers"]["locked"]["total_wan"] == 1.0          # 10000 元
    assert r["future_bucket"]["amount_wan"] == 0.1              # 1000 元
    assert r["actual_ytd_wan"] == 500.0
    assert r["projection_wan"] == pytest.approx(501.1)
    assert r["gap_to_target_wan"] == pytest.approx(9498.9)
    assert r["annual_target"]["source"] == "db"


def test_target_falls_back_to_config(eng):
    fe = _fe(eng, budget_rows=[{"G": "A", "A": "递延", "AB": 1.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1.0}])
    r = fe.forecast("202606")
    assert r["annual_target"]["amount_wan"] == 23000.0
    assert r["annual_target"]["source"] == "config"


def test_no_data_raises_import_error(eng):
    """宽表缺失 → ImportError_（service 转 fail-closed 空结构）。"""
    fe = _fe(eng, budget_rows=[], draft_rows=[])
    with pytest.raises(ImportError_):
        fe.forecast("202606")


# ─── future 桶 ───

def test_future_bucket_only_counted_when_bucketed(eng):
    """未落桶的履约ID不计入 future；非『未来可确收』桶不计入。"""
    fe = _fe(eng,
             budget_rows=[
                 {"G": "F1", "A": "递延", "AB": 1.0, "K": 10000.0},
                 {"G": "N1", "A": "新签", "AB": 1.0, "Q_adj": 20000.0},
                 {"G": "X1", "A": "递延", "AB": 1.0, "K": 99999.0},
             ],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}])
    _put_bucket(eng, "202606", "F1", fill="未来可确收")
    _put_bucket(eng, "202606", "N1", fill="本年度正常可确收")
    r = fe.forecast("202606")
    fb = r["future_bucket"]
    assert fb["count"] == 1
    assert fb["amount_wan"] == pytest.approx(1.0)     # 仅 F1 的 K
    assert fb["by_group_wan"]["递延"] == pytest.approx(1.0)
    assert fb["by_group_wan"]["新签"] == 0.0


def test_future_amount_prefers_qadj_for_new(eng):
    """新签 future 优先 Q_adj；缺键回退 K（不硬编码物理列位）。"""
    fe = _fe(eng,
             budget_rows=[{"G": "N1", "A": "新签", "AB": 1.0,
                           "Q_adj": 5000.0, "K": 9999.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}])
    _put_bucket(eng, "202606", "N1", fill="未来可确收")
    r = fe.forecast("202606")
    assert r["future_bucket"]["amount_wan"] == pytest.approx(0.5)


def test_future_amount_empty_when_no_bucket_rows(eng):
    """ra_bucket 为空 → future 桶 count=0/amount=0（证据缺失≠缺陷）。"""
    fe = _fe(eng,
             budget_rows=[{"G": "F1", "A": "递延", "AB": 1.0, "K": 10000.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}])
    r = fe.forecast("202606")
    assert r["future_bucket"] == {
        "count": 0, "amount_wan": 0.0,
        "by_group_wan": {"新签": 0.0, "递延": 0.0}}


# ─── 风险清单 ───

def test_manual_review_counts_blank_and_never_bucketed(eng):
    """留空 + 从未落桶都要计入，且不得重复计数同一 ID。"""
    fe = _fe(eng,
             budget_rows=[{"G": "A", "A": "递延", "AB": 1.0},
                          {"G": "B", "A": "递延", "AB": 1.0},
                          {"G": "C", "A": "递延", "AB": 1.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}])
    _put_bucket(eng, "202606", "A", fill="")          # 留空
    _put_bucket(eng, "202606", "B", fill="未来可确收")  # 正常
    # C 从未落桶
    r = fe.forecast("202606")
    mr = next(x for x in r["risks"] if x["type"] == "manual_review")
    assert mr["count"] == 2
    assert mr["blank_in_bucket"] == 1
    assert mr["never_bucketed"] == 1


def test_manual_review_absent_when_clean(eng):
    fe = _fe(eng, budget_rows=[{"G": "A", "A": "递延", "AB": 1.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}])
    _put_bucket(eng, "202606", "A", fill="本年度正常可确收")
    r = fe.forecast("202606")
    assert all(x["type"] != "manual_review" for x in r["risks"])


def test_missing_signals_when_unavailable(eng):
    sig = {"period": "202606", "available": False,
           "missing_sources": ["oa"],
           "coverage": {"budget_contracts": 7, "oa_known": 0}}
    fe = _fe(eng, budget_rows=[{"G": "A", "A": "递延", "AB": 1.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}], signals=sig)
    r = fe.forecast("202606")
    ms = next(x for x in r["risks"] if x["type"] == "missing_signals")
    assert ms["count"] == 7
    assert ms["detail"].startswith("信号源不可用")


def test_missing_signals_when_partial_coverage(eng):
    sig = {"period": "202606", "available": True, "missing_sources": [],
           "coverage": {"budget_contracts": 10, "oa_known": 4}}
    fe = _fe(eng, budget_rows=[{"G": "A", "A": "递延", "AB": 1.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}], signals=sig)
    r = fe.forecast("202606")
    ms = next(x for x in r["risks"] if x["type"] == "missing_signals")
    assert ms["count"] == 6


def test_contract_disappear_risk(eng):
    """AR=合同终止 → contract_disappear（不影响口径，仅提示）。"""
    fe = _fe(eng,
             budget_rows=[{"G": "D1", "A": "递延", "AB": 1.0, "AR": "合同终止"},
                          {"G": "D2", "A": "递延", "AB": 1.0, "AR": ""}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}])
    r = fe.forecast("202606")
    cd = next(x for x in r["risks"] if x["type"] == "contract_disappear")
    assert cd["count"] == 1 and cd["samples"] == ["D1"]


def test_caliber_gap_threshold_boundary(eng):
    """差异 ≤1% 不报；>1% 报（阈值 ±1%）。"""
    fe = _fe(eng,
             budget_rows=[{"G": "A", "A": "递延", "AB": 100.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 101.0}])   # 差异 +1%
    r = fe.forecast("202606")
    assert all(x["type"] != "caliber_gap" for x in r["risks"])
    fe = _fe(eng,
             budget_rows=[{"G": "A", "A": "递延", "AB": 100.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 102.0}])   # 差异 +2%
    r = fe.forecast("202606")
    cg = next(x for x in r["risks"] if x["type"] == "caliber_gap")
    assert cg["relative_diff"] == pytest.approx(0.02)


# ─── 服务层 fail-closed ───

def test_service_fail_closed_empty_structure(tmp_path):
    svc = RevenueAnalysisService(tmp_path / "svc.db")
    out = svc.forecast("202606")
    assert out["has_data"] is False
    assert out["risks"] == []
    assert out["period"] == "202606"


def test_service_returns_snapshot(tmp_path):
    svc = RevenueAnalysisService(tmp_path / "svc.db")
    fe = _fe(svc.engine,
             budget_rows=[{"G": "A", "A": "递延", "AB": 1.0}],
             draft_rows=[{"C": "2026-09-30", "AQ": 1000.0}])
    svc.engine.set_annual_target(2026, 23000.0)
    out = svc.forecast("202606")
    assert out["has_data"] is True
    assert out["annual_target"]["amount_wan"] == 23000.0


# ─── CLI 接线 ───

def test_cli_accepts_forecast_action():
    from bdms.cli.main import build_parser
    parser = build_parser()
    args = parser.parse_args(["revenue-analysis", "forecast", "202606"])
    assert args.action == "forecast"


# ─── 集成锚点：真实源 vs ra_caliber 冻结值 ───

@pytest.mark.skipif(not REAL_202606.exists(), reason="真实 202606 源未就位")
def test_integration_202606_caliber_zero_diff(tmp_path):
    svc = RevenueAnalysisService(tmp_path / "it06.db")
    svc.import_source("202606", REAL_202606)
    svc.generate("202606", "regenerate")
    snap = svc.summary("202606")
    f = svc.forecast("202606")
    assert f["has_data"] is True
    assert f["calibers"]["locked"]["total_wan"] == pytest.approx(
        round(snap["locked"]["total"] / 10000, 6))
    assert f["calibers"]["dynamic"]["total_wan"] == pytest.approx(
        round(snap["dynamic"]["total"] / 10000, 6))
    # 风险清单与分桶证据自洽：blank_in_bucket == ra_bucket 中留空行数
    mr = next((x for x in f["risks"] if x["type"] == "manual_review"), None)
    conn = sqlite3.connect(svc.engine.db_path)
    blank = conn.execute(
        "SELECT COUNT(*) FROM ra_bucket WHERE period='202606' "
        "AND (budget_fill IS NULL OR budget_fill='')").fetchone()[0]
    conn.close()
    assert mr is not None and mr["blank_in_bucket"] == blank


@pytest.mark.skipif(not REAL_202609.exists(), reason="真实 202609 源未就位")
def test_integration_202609_runs(tmp_path):
    svc = RevenueAnalysisService(tmp_path / "it09.db")
    svc.import_source("202609", REAL_202609)
    svc.generate("202609", "regenerate")
    f = svc.forecast("202609")
    assert f["has_data"] is True
    assert f["calibers"]["locked"]["total_wan"] > 0
    assert isinstance(f["risks"], list)
