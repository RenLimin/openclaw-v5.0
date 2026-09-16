"""模块2 确认收入 — service 层回归测试。

覆盖本次修复的两个真实缺陷：
  1. has_data(month) 忽略 month 参数（导致 --mode read 对空月份假成功）
  2. revenue 缺 service 层，CLI/Web 的 --mode 幂等语义被静默忽略
"""

import pytest

from bdms.modules.revenue.service import (
    RevenueService, MODE_AUTO, MODE_READ, MODE_REGENERATE,
)

HAS_DATA_MONTH = "202608"
EMPTY_MONTH = "203012"  # 远期月份，确定无数据


@pytest.fixture(scope="module")
def svc():
    s = RevenueService()
    s.adapter.db_path.parent.mkdir(parents=True, exist_ok=True)
    return s


# ─── has_data 必须按月份过滤 ───

def test_has_data_filters_by_month(svc):
    """回归：早期实现只查“是否有任意行”，任何月份都返回 True。"""
    assert svc.has_data(HAS_DATA_MONTH) is True
    assert svc.has_data(EMPTY_MONTH) is False


def test_has_data_ok_for_other_known_months(svc):
    """202606 是手工报表月份，应有数据。"""
    assert svc.has_data("202606") is True


# ─── 幂等模式语义 ───

def test_generate_auto_reads_when_data_exists(svc):
    r = svc.generate(HAS_DATA_MONTH, MODE_AUTO)
    assert r["action"] == "read"
    assert r["month"] == HAS_DATA_MONTH
    assert isinstance(r["job_id"], int)


def test_generate_read_raises_on_empty_month(svc):
    with pytest.raises(ValueError):
        svc.generate(EMPTY_MONTH, MODE_READ)


def test_generate_read_works_on_populated_month(svc):
    r = svc.generate(HAS_DATA_MONTH, MODE_READ)
    assert r["action"] == "read"


def test_generate_rejects_unknown_mode(svc):
    with pytest.raises(ValueError):
        svc.generate(HAS_DATA_MONTH, "bogus")


def test_generate_writes_job_log(svc):
    """每次 generate 都应写一条 job 记录。"""
    from bdms.core import db as _db
    r = svc.generate(HAS_DATA_MONTH, MODE_AUTO)
    conn = _db.get_connection(svc.meta_db_path)
    try:
        row = _db.get_job(conn, r["job_id"])
        assert row is not None
        assert row["module"] == "revenue"
        assert row["month"] == HAS_DATA_MONTH
    finally:
        conn.close()


# ─── 月份列表与规模 ───

def test_list_months_descending(svc):
    months = svc.list_months()
    assert HAS_DATA_MONTH in months
    assert months == sorted(months, reverse=True)


def test_summary_counts_positive(svc):
    counts = svc.summary_counts(HAS_DATA_MONTH)
    assert counts.get("plan_draft", 0) > 0
    assert counts.get("budget_exec", 0) > 0
