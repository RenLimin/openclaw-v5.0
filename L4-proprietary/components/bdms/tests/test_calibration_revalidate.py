"""校准后重校验闭环 — 单元测试。

对齐 DESIGN-DETAIL-MANUAL-CALIBRATION-v1.0.md §3：
  - 校准→问题消失；撤销→问题回现（AC-03）
  - issue 流转 confirmed/pending + operator/resolved_at 留痕
  - 重算 review_status KPI
  - busy 锁：同月 job running 时拒绝写（409 CALIBRATION_BUSY）
真实临时 SQLite，不用 mock。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from bdms.core import db as _db
from bdms.modules.delivery_report.calibration import (
    CalibrationError,
    CalibrationService,
)
from bdms.modules.delivery_report.engine import DeliveryReportEngine
from bdms.modules.delivery_report.service import DeliveryReportService


# ─── Fixtures ───

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    _db.init_db(path)
    return path


@pytest.fixture
def seeded(db_path):
    """签约数据：行0 好日期、行1 坏日期（触发 R_DATE）。"""
    raw = {
        "签约": pd.DataFrame({
            "合同编号": ["C001", "C002"],
            "项目名称": ["P-A", "P-B"],
            "所属产线": ["L1", "L2"],
            "签约日期": ["2026/6/3", "bad-date"],
        }),
    }
    DeliveryReportEngine(db_path).persist("202610", raw)
    return db_path


@pytest.fixture
def svc(seeded):
    return DeliveryReportService(seeded)


@pytest.fixture
def cs(seeded):
    return CalibrationService(seeded)


def _pending_count(seeded, month="202610"):
    conn = _db.get_connection(seeded)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM dr_import_validation "
            "WHERE month=? AND status='pending'", (month,)).fetchone()[0]
    finally:
        conn.close()


def _confirmed_count(seeded, month="202610"):
    conn = _db.get_connection(seeded)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM dr_import_validation "
            "WHERE month=? AND status='confirmed'", (month,)).fetchone()[0]
    finally:
        conn.close()


# ─── 1. 校准 → 问题消失 → 撤销 → 回现（AC-03）───

def test_calibrate_resolves_issue_and_revoke_reappears(svc, cs, seeded):
    # 生产路径落 issue 明细
    svc._update_review_status("202610", "validating")
    assert _pending_count(seeded) >= 1  # bad-date 触发

    # 校准 → 重校验 → 该行问题 resolved
    cs.upsert("202610", "签约", 1, "签约日期", "2026-06-05",
              "日期修正", "gateway-owner")
    rc = svc.recalculate_after_calibration("202610", [("签约", 1)],
                                           operator="gateway-owner")
    assert rc["resolved_issues"] >= 1
    # 同一行校准后 pending 中不再含该日期问题
    assert _confirmed_count(seeded) >= 1

    # 撤销 → 问题回现
    cs.revoke("202610", "签约", 1, "签约日期", "gateway-owner")
    svc.recalculate_after_calibration("202610", [("签约", 1)],
                                      operator="gateway-owner")
    assert _pending_count(seeded) >= 1
    assert _confirmed_count(seeded) == 0  # 撤销后 confirmed 回落 pending


def test_calibration_does_not_clear_manual_confirmed(svc, cs, seeded):
    """人工 confirmed（非自动）不能被重校验覆盖（合并语义）。"""
    svc._update_review_status("202610", "validating")
    conn = _db.get_connection(seeded)
    try:
        # 行0 无违规，手动插入一条 issue 并 confirmed（人工处置语义）
        cur = conn.execute(
            "INSERT INTO dr_import_validation "
            "(month, sheet, row_index, column_name, rule_code, severity, "
            " message, original_value, status, operator) "
            "VALUES ('202610','签约',0,'项目名称','R_MANUAL','WARNING',"
            "'人工确认无误','P-A','confirmed','human')")
        conn.commit()
        assert cur.lastrowid > 0
    finally:
        conn.close()
    conn = _db.get_connection(seeded)
    try:
        manual_row = conn.execute(
            "SELECT * FROM dr_import_validation "
            "WHERE month='202610' AND sheet='签约' AND row_index=0 "
            "AND rule_code='R_MANUAL'").fetchone()
    finally:
        conn.close()
    assert dict(manual_row)["status"] == "confirmed"
    assert dict(manual_row)["operator"] == "human"

    cs.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    svc.recalculate_after_calibration("202610", [("签约", 1)], operator="op")
    # 人工 confirmed 保留：该记录不被重校验清除/改写
    conn = _db.get_connection(seeded)
    try:
        manual_row2 = conn.execute(
            "SELECT * FROM dr_import_validation "
            "WHERE month='202610' AND sheet='签约' AND row_index=0 "
            "AND rule_code='R_MANUAL'").fetchone()
    finally:
        conn.close()
    assert manual_row2 is not None
    assert dict(manual_row2)["status"] == "confirmed"
    assert dict(manual_row2)["operator"] == "human"
    # 校准 row1 的坏日期 → 该行问题自动 confirmed（总数增加是预期）
    assert _confirmed_count(seeded) == 2


# ─── 2. KPI 重算 ───

def test_review_status_kpi_after_calibration(svc, cs, seeded):
    svc._update_review_status("202610", "validating")
    rs_before = svc.get_review_status("202610")
    assert rs_before["status"] == "validating"

    cs.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    svc.recalculate_after_calibration("202610", [("签约", 1)], operator="op")
    rs_after = svc.get_review_status("202610")
    assert rs_after["status"] == "validating"
    # KPI 字段必须齐全且 pending_fixes 与明细表一致
    assert "total_errors" in rs_after and "pending_fixes" in rs_after
    assert rs_after["pending_fixes"] == _pending_count(seeded)


# ─── 3. busy 锁（409 CALIBRATION_BUSY）───

def test_busy_lock_blocks_upsert(svc, cs, seeded):
    conn = _db.get_connection(seeded)
    try:
        _db.create_job(conn, "calibration", "202610", "revalidate")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(CalibrationError) as ei:
        cs.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    assert ei.value.code == "CALIBRATION_BUSY"


def test_busy_lock_blocks_revoke(svc, cs, seeded):
    cs.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    conn = _db.get_connection(seeded)
    try:
        _db.create_job(conn, "calibration", "202610", "revalidate")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(CalibrationError) as ei:
        cs.revoke("202610", "签约", 1, "签约日期", "op")
    assert ei.value.code == "CALIBRATION_BUSY"


def test_busy_lock_released_after_job_done(cs, seeded):
    conn = _db.get_connection(seeded)
    try:
        job_id = _db.create_job(conn, "calibration", "202610", "revalidate")
        _db.update_job_status(conn, job_id, "done", 100)
        conn.commit()
    finally:
        conn.close()
    # job 已 done → 不再阻塞
    r = cs.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    assert r["action"] == "created"


def test_other_month_job_does_not_block(cs, seeded):
    conn = _db.get_connection(seeded)
    try:
        _db.create_job(conn, "calibration", "202611", "revalidate")
        conn.commit()
    finally:
        conn.close()
    r = cs.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    assert r["action"] == "created"


# ─── 4. 错误契约 ───

def test_calibration_error_to_dict():
    e = CalibrationError("日期格式非法", code="INVALID_TYPE", value="x")
    d = e.to_dict()
    assert d["detail"]["code"] == "INVALID_TYPE"
    assert "日期格式非法" in d["detail"]["message"]
