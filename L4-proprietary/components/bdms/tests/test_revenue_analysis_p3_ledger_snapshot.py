"""P3 · Q6/Q7 台账时序快照（DESIGN-DETAIL §7.1/§7.2）

- persist_ledger_snapshot：generate 后自动 upsert（月度汇总记录 + 履约汇总记录）
- ra_snapshot (period, snapshot_type) 唯一；重复生成幂等，不重复
- load_ledger_snapshot / list_snapshot_periods 回读
- 缺月不静默：上一统计期无快照 → warnings 提示（不抛错、不推断）
"""

import json
from pathlib import Path

import pytest

from bdms.modules.revenue_analysis.service import RevenueAnalysisService


@pytest.fixture()
def engine(tmp_path: Path):
    return RevenueAnalysisService(tmp_path / "ls.db").engine


def _fake_data():
    return {
        "月度汇总记录": [{"A": "202606"}, {"A": "202606"}],
        "履约汇总记录": [{"B": "p1"}],
    }


def test_persist_and_load_roundtrip(engine):
    r = engine.persist_ledger_snapshot("202606", _fake_data())
    assert r["written"] == 2
    snap = engine.load_ledger_snapshot("202606")
    assert snap is not None
    assert len(snap["monthly_record"]) == 2
    assert len(snap["perf_record"]) == 1


def test_upsert_idempotent(engine):
    engine.persist_ledger_snapshot("202606", _fake_data())
    engine.persist_ledger_snapshot("202606", _fake_data())
    snap = engine.load_ledger_snapshot("202606")
    assert len(snap["monthly_record"]) == 2  # 不重复


def test_load_none_when_missing(engine):
    assert engine.load_ledger_snapshot("202600") is None


def test_list_snapshot_periods(engine):
    engine.persist_ledger_snapshot("202605", _fake_data())
    engine.persist_ledger_snapshot("202606", _fake_data())
    assert engine.list_snapshot_periods() == ["202605", "202606"]


def test_continuity_warning_when_prev_missing(engine):
    # 只有 202606，上一期 202605 缺失 → 有告警
    r = engine.persist_ledger_snapshot("202606", _fake_data())
    assert r["warnings"], "应报缺月告警"
    assert any("202605" in w for w in r["warnings"])


def test_continuity_ok_when_prev_present(engine):
    engine.persist_ledger_snapshot("202605", _fake_data())
    r = engine.persist_ledger_snapshot("202606", _fake_data())
    assert not r["warnings"], "上期存在时不应告警"


def test_service_exposes_ledger_snapshot(tmp_path):
    s = RevenueAnalysisService(tmp_path / "svc.db")
    e = s.engine
    e.persist_ledger_snapshot("202606", _fake_data())
    snap = s.ledger_snapshot("202606")
    assert snap["has_snapshot"] is True
    assert len(snap["monthly_record"]) == 2
    assert "202606" in s.snapshot_periods()
