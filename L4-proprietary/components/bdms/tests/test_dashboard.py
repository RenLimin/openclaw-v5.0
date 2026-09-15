"""模块4（交付统计看板）测试。

用真实数据（202608）跑通全部聚合 + 下钻 + 快照缓存。
数据不可用时自动 skip，保证 CI 在无数据环境不误报。
"""

import sys
from pathlib import Path

import pytest

# 让 src 可导入
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from bdms.core import db as _db                      # noqa: E402
from bdms.core.paths import DATA_DIR                 # noqa: E402
from bdms.modules.dashboard.engine import (          # noqa: E402
    DashboardEngine,
    SHEET_SIGN,
    SHEET_EXCEPTION,
    SHEET_POC,
)
from bdms.modules.dashboard.service import DashboardService  # noqa: E402

MONTH = "202608"


# ─── fixtures ───

def _has_delivery_data(month: str = MONTH) -> bool:
    try:
        conn = _db.get_connection()
        try:
            return bool(_db.list_sheets(conn, month, prefix="dr"))
        finally:
            conn.close()
    except Exception:
        return False


def _has_revenue_data() -> bool:
    p = DATA_DIR / "revenue.db"
    if not p.exists():
        return False
    import sqlite3
    try:
        conn = sqlite3.connect(str(p))
        try:
            n = conn.execute("SELECT COUNT(*) FROM budget_exec").fetchone()[0]
            return n > 0
        finally:
            conn.close()
    except Exception:
        return False


needs_delivery = pytest.mark.skipif(
    not _has_delivery_data(), reason=f"无 {MONTH} 月报数据")
needs_revenue = pytest.mark.skipif(
    not _has_revenue_data(), reason="无 revenue.db/budget_exec 数据")


@pytest.fixture(scope="module")
def engine() -> DashboardEngine:
    return DashboardEngine()


@pytest.fixture(scope="module")
def service() -> DashboardService:
    return DashboardService()


# ─── 1. KPI ───

@needs_delivery
@needs_revenue
def test_compute_kpis(engine):
    k = engine.compute_kpis(MONTH)
    assert k["month"] == MONTH
    assert k["contract_amount"] > 0
    assert k["plan_revenue"] > 0
    assert k["actual_revenue"] >= 0
    # 完成率 = 实际/计划
    assert k["completion_rate"] == pytest.approx(
        k["actual_revenue"] / k["plan_revenue"], rel=1e-6)
    assert k["delivery_project_count"] > 0
    assert k["exception_project_count"] > 0
    # 分类明细：新签 + 递延 == 合计
    by_cat = k["by_category"]
    assert "新签" in by_cat and "递延" in by_cat
    assert (by_cat["新签"]["plan"] + by_cat["递延"]["plan"]
            == pytest.approx(k["plan_revenue"], rel=1e-6))


@needs_revenue
def test_compute_monthly_trend(engine):
    t = engine.compute_monthly_trend(["202606", "202607", "202608"])
    assert t["months"] == ["202606", "202607", "202608"]
    for cat in ("新签", "递延", "合计"):
        assert cat in t["series"]
        assert len(t["series"][cat]["plan"]) == 3
        assert len(t["series"][cat]["actual"]) == 3
    # 合计 = 新签 + 递延（逐月）
    for i in range(3):
        tot = (t["series"]["新签"]["plan"][i] + t["series"]["递延"]["plan"][i])
        assert t["series"]["合计"]["plan"][i] == pytest.approx(tot, rel=1e-6)


@needs_revenue
def test_trend_default_months(engine):
    t = engine.compute_monthly_trend()
    assert len(t["months"]) == 12  # 全年 202601..202612


# ─── 3. 交付状态分布 ───

@needs_delivery
def test_delivery_status_dist(engine):
    d = engine.compute_delivery_status_dist(MONTH, SHEET_SIGN)
    assert d["total"] > 0
    assert len(d["items"]) > 0
    # percent 累加 ≈ 1
    assert sum(i["percent"] for i in d["items"]) == pytest.approx(1.0, abs=1e-3)
    # value 累加 == total
    assert sum(i["value"] for i in d["items"]) == d["total"]
    # 每个 item 都有 label/value/percent
    for it in d["items"]:
        assert set(it) == {"label", "value", "percent"}
    # 验收状态分布应包含"未验收"
    assert d["acceptance_status"]["total"] > 0


@needs_delivery
def test_delivery_status_dist_poc(engine):
    d = engine.compute_delivery_status_dist(MONTH, SHEET_POC)
    assert d["total"] > 0


# ─── 4. 异常分布 ───

@needs_delivery
def test_exception_dist(engine):
    x = engine.compute_exception_dist(MONTH, "type")
    assert x["total"] > 0
    assert x["group_by"] == "type"
    # 组合标签形如 "状态 / 验收状态"
    assert any("/" in i["label"] for i in x["items"])
    assert sum(i["value"] for i in x["items"]) == x["total"]


@needs_delivery
def test_exception_dist_by_team(engine):
    x = engine.compute_exception_dist(MONTH, "team")
    assert x["total"] > 0
    assert all(i["label"] for i in x["items"])


# ─── 5. 部门统计 ───

@needs_delivery
def test_dept_stats(engine):
    dp = engine.compute_dept_stats(MONTH)
    assert dp["total"] > 0
    assert len(dp["items"]) > 0
    # 各部门 total 之和 == 全体
    assert sum(i["total"] for i in dp["items"]) == dp["total"]
    for it in dp["items"]:
        assert it["abnormal"] <= it["total"]
        assert 0.0 <= it["abnormal_rate"] <= 1.0
        assert isinstance(it["by_delivery_status"], dict)


# ─── 6. 下钻穿透 ───

@needs_delivery
def test_drill_down_delivery_status(engine):
    dist = engine.compute_delivery_status_dist(MONTH, SHEET_SIGN)
    # 取第一个非零分组
    label = dist["items"][0]["label"]
    expected = dist["items"][0]["value"]
    r = engine.drill_down(MONTH, SHEET_SIGN, "delivery_status", label)
    assert r["total"] == expected            # 下钻行数必须等于图表数值
    assert len(r["rows"]) == min(expected, r["shown"])
    assert len(r["columns"]) > 0


@needs_delivery
def test_drill_down_dept(engine):
    dp = engine.compute_dept_stats(MONTH)
    dept = dp["items"][0]["label"]
    expected = dp["items"][0]["total"]
    r = engine.drill_down(MONTH, SHEET_SIGN, "dept", dept)
    assert r["total"] == expected


@needs_delivery
def test_drill_down_exception_type(engine):
    x = engine.compute_exception_dist(MONTH, "type")
    label = x["items"][0]["label"]
    expected = x["items"][0]["value"]
    r = engine.drill_down(MONTH, SHEET_EXCEPTION, "exception_type", label)
    assert r["total"] == expected


@needs_delivery
def test_drill_down_invalid_dimension(engine):
    with pytest.raises(ValueError):
        engine.drill_down(MONTH, SHEET_SIGN, "nonexistent", "x")


@needs_delivery
def test_drill_down_limit(engine):
    r = engine.drill_down(MONTH, SHEET_SIGN, "dept", "南区客户服务部", limit=5)
    assert r["total"] >= r["shown"]
    assert len(r["rows"]) <= 5


# ─── 7. Service 层 ───

@needs_delivery
def test_get_dashboard(service):
    d = service.get_dashboard(MONTH, use_cache=False)
    for key in ("month", "kpis", "monthly_trend", "delivery_status_dist",
                "exception_dist", "dept_stats", "drill_options",
                "available_months"):
        assert key in d
    assert d["month"] == MONTH


@needs_delivery
def test_snapshot_roundtrip(service):
    """refresh_snapshot 后，缓存读取应命中且数据一致。"""
    service.refresh_snapshot(MONTH)
    fresh = service.get_dashboard(MONTH, use_cache=False)
    cached = service.get_dashboard(MONTH, use_cache=True)
    assert cached.get("_cached") is True
    assert (cached["kpis"]["actual_revenue"]
            == pytest.approx(fresh["kpis"]["actual_revenue"], rel=1e-9))


@needs_delivery
def test_snapshot_clear(service):
    service.refresh_snapshot(MONTH)
    n = service.clear_snapshot(MONTH)
    assert n >= 1
    # 清空后应退化为实时计算
    d = service.get_dashboard(MONTH, use_cache=True)
    assert "_cached" not in d


@needs_delivery
def test_service_drill_down_sheet_inference(service):
    x = service.get_dashboard(MONTH, use_cache=False)["exception_dist"]
    label = x["items"][0]["label"]
    r = service.drill_down(MONTH, "exception_type", label)
    assert r["sheet"] == SHEET_EXCEPTION
    d = service.get_dashboard(MONTH, use_cache=False)["dept_stats"]
    r2 = service.drill_down(MONTH, "dept", d["items"][0]["label"])
    assert r2["sheet"] == SHEET_SIGN


@needs_delivery
def test_list_available_months(service):
    months = service.list_available_months()
    assert MONTH in months
