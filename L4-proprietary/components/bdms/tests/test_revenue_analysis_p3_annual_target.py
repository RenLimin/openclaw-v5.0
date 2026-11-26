"""P3 · Q8 年度目标维护（DESIGN-DETAIL §8.2）

- ra_annual_target 表读写（get/set/list，upsert）
- _build_summary_analysis 优先读 DB，缺失回退 config（golden 不飘）
- 多年度独立、更新不重复
"""

from pathlib import Path

import pytest

from bdms.modules.revenue_analysis.service import RevenueAnalysisService


def make_engine(tmp_path: Path):
    return RevenueAnalysisService(tmp_path / "at.db").engine


def test_get_none_when_unset(tmp_path):
    e = make_engine(tmp_path)
    assert e.get_annual_target(2026) is None


def test_set_and_get_roundtrip(tmp_path):
    e = make_engine(tmp_path)
    e.set_annual_target(2026, 25000.0)
    assert e.get_annual_target(2026) == 25000.0


def test_upsert_updates_not_duplicates(tmp_path):
    e = make_engine(tmp_path)
    e.set_annual_target(2026, 25000.0)
    e.set_annual_target(2026, 26000.0)
    targets = e.list_annual_targets()
    assert len(targets) == 1
    assert targets[0]["amount_wan"] == 26000.0


def test_multiple_years_independent(tmp_path):
    e = make_engine(tmp_path)
    e.set_annual_target(2026, 25000.0)
    e.set_annual_target(2027, 30000.0)
    targets = e.list_annual_targets()
    assert len(targets) == 2
    assert e.get_annual_target(2026) == 25000.0
    assert e.get_annual_target(2027) == 30000.0


def test_service_exposes_annual_targets(tmp_path):
    s = RevenueAnalysisService(tmp_path / "svc.db")
    s.set_annual_target(2026, 12345.0)
    lst = s.annual_targets()
    assert lst[0]["year"] == 2026
    assert lst[0]["amount_wan"] == 12345.0
