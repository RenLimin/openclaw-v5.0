"""模块5 交付管理系统设定 —— 测试。

用法：
    cd L4-proprietary/components/bdms && export PYTHONPATH=src && python3 -m pytest tests/test_settings.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bdms.core import db as _db                                  # noqa: E402
from bdms.modules.settings import SettingsEngine, SettingsService  # noqa: E402
from bdms.modules.settings.engine import month_minus, month_diff   # noqa: E402


@pytest.fixture()
def svc(tmp_path):
    db = tmp_path / "test_settings.db"
    s = SettingsService(db)
    s.ensure_schema()
    return s


@pytest.fixture()
def svc_with_months(tmp_path):
    """带 report_month 记录的库：202605-202608。"""
    db = tmp_path / "test_settings2.db"
    _db.init_db(db)
    conn = _db.get_connection(db)
    for m in ["202605", "202606", "202607", "202608"]:
        _db.register_month(conn, "revenue", m, source_path="/x.xlsx",
                           row_counts={"预算执行表": 100})
    _db.register_month(conn, "delivery_report", "202606", row_counts={"签约": 50})
    conn.commit()
    conn.close()
    return SettingsService(db)


# ─── 基础读写 ───

def test_defaults_present(svc):
    allv = svc.get_all()
    assert allv["view.default_months_back"] == 12
    assert allv["view.default_month"] is None
    assert allv["view.available_months"] == []
    assert allv["report.auto_overwrite"] is False
    assert allv["report.excel_output_dir"] == "output"


def test_set_and_get(svc):
    r = svc.set("view.default_months_back", 6)
    assert r["ok"] and r["value"] == 6 and r["previous"] == 12
    assert svc.get("view.default_months_back") == 6
    # 整型往返（不是字符串 "6"）
    assert isinstance(svc.get("view.default_months_back"), int)


def test_set_bool_and_str(svc):
    svc.set("report.auto_overwrite", True)
    assert svc.get("report.auto_overwrite") is True
    svc.set("report.auto_overwrite", "false")
    assert svc.get("report.auto_overwrite") is False
    svc.set("report.excel_output_dir", "/tmp/out")
    assert svc.get("report.excel_output_dir") == "/tmp/out"


def test_set_month_normalization(svc):
    svc.set("view.default_month", "2026-08")
    assert svc.get("view.default_month") == "202608"
    svc.set("view.default_month", None)
    assert svc.get("view.default_month") is None


def test_set_validation(svc):
    with pytest.raises(ValueError):
        svc.set("view.default_months_back", "abc")
    with pytest.raises(ValueError):
        svc.set("view.default_months_back", 0)
    with pytest.raises(ValueError):
        svc.set("view.default_months_back", 999)
    with pytest.raises(ValueError):
        svc.set("view.default_month", "2026")
    with pytest.raises(ValueError):
        svc.set("view.available_months", "202608")
    with pytest.raises(ValueError):
        svc.set("", 1)


def test_available_months_normalized_desc(svc):
    svc.set("view.available_months", ["202606", "202608", "202605", "202608"])
    assert svc.get("view.available_months") == ["202608", "202606", "202605"]


def test_set_many(svc):
    r = svc.set_many({"report.auto_overwrite": True, "view.default_months_back": 3})
    assert r["count"] == 2
    assert svc.get("report.auto_overwrite") is True
    assert svc.get("view.default_months_back") == 3


def test_reset_defaults(svc):
    svc.set("view.default_months_back", 3)
    svc.set("report.auto_overwrite", True)
    r = svc.reset_defaults()
    assert r["ok"]
    assert svc.get("view.default_months_back") == 12
    assert svc.get("report.auto_overwrite") is False
    assert svc.get("view.default_month") is None


# ─── 月份聚合 ───

def test_get_available_months(svc_with_months):
    assert svc_with_months.get_available_months() == ["202608", "202607", "202606", "202605"]
    assert svc_with_months.get_available_months("delivery_report") == ["202606"]


def test_sync_available_months(svc_with_months):
    r = svc_with_months.sync_available_months()
    assert r["months"] == ["202608", "202607", "202606", "202605"]
    assert svc_with_months.get("view.available_months") == r["months"]


def test_month_coverage(svc_with_months):
    cov = {c["month"]: c["modules"] for c in svc_with_months.get_month_coverage()}
    assert set(cov["202606"]) == {"revenue", "delivery_report"}
    assert cov["202608"] == ["revenue"]


# ─── 有效视图 ───

def test_effective_view_default_month_auto(svc_with_months):
    v = svc_with_months.get_effective_view()
    assert v["default_month"] == "202608"          # 自动取最新
    assert v["default_months_back"] == 12
    assert v["latest_month"] == "202608"
    assert v["earliest_month"] == "202605"
    assert v["month_window"] == ["202605", "202606", "202607", "202608"]


def test_effective_view_respects_months_back(svc_with_months):
    svc_with_months.set("view.default_months_back", 2)
    v = svc_with_months.get_effective_view()
    assert v["month_window"] == ["202607", "202608"]
    assert v["earliest_month"] == "202607"


def test_effective_view_configured_month(svc_with_months):
    svc_with_months.set("view.default_month", "202606")
    v = svc_with_months.get_effective_view()
    assert v["default_month"] == "202606"
    assert v["month_window"] == ["202605", "202606"]


def test_effective_view_invalid_configured_month_falls_back(svc_with_months):
    svc_with_months.set("view.default_month", "202001")   # 不在可用列表
    v = svc_with_months.get_effective_view()
    assert v["default_month"] == "202608"


def test_effective_view_empty_db(svc):
    v = svc.get_effective_view()
    assert v["available_months"] == []
    assert v["month_window"] == []
    assert v["earliest_month"] is None


# ─── 描述与统计 ───

def test_describe_covers_known_keys(svc):
    keys = {d["key"] for d in svc.describe()}
    assert {"view.default_months_back", "view.default_month",
            "view.available_months", "report.auto_overwrite",
            "report.excel_output_dir"} <= keys
    assert all("description" in d and d["description"] for d in svc.describe())


def test_stats(svc_with_months):
    st = svc_with_months.engine.stats()
    mods = {m["module"]: m for m in st["modules"]}
    assert mods["revenue"]["months"] == 4
    assert mods["revenue"]["earliest"] == "202605"
    assert st["total_months"] == 4


def test_summary(svc_with_months):
    s = svc_with_months.summary()
    assert s["settings"]["view.default_months_back"] == 12
    assert s["available_months"][0] == "202608"
    assert s["effective"]["default_month"] == "202608"


# ─── 工具函数 ───

def test_month_math():
    assert month_minus("202601", 1) == "202512"
    assert month_minus("202608", 11) == "202509"
    assert month_diff("202608", "202605") == 3
    with pytest.raises(ValueError):
        month_minus("bad", 1)
