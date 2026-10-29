"""人工校准覆盖层 CalibrationService — 单元测试。

对齐 DESIGN-DETAIL-MANUAL-CALIBRATION-v1.0.md §2/§7：
  - 原始 dr_sheet_row 永不修改（AC-02）
  - upsert/revise/revoke + history 留痕（AC-05/06/07）
  - apply_overlays 是原始→effective 唯一口径，入参不可变
  - 保存前置类型/枚举/原因校验（AC-10）
所有测试用真实临时 SQLite（不用 mock）。
"""
import json
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


# ─── Fixtures ───

@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    _db.init_db(path)
    return path


@pytest.fixture
def seeded(db_path):
    """写入 3 行签约数据（含坏日期/坏数值/空值）。"""
    raw = {
        "签约": pd.DataFrame({
            "合同编号": ["C001", "C002", "C003"],
            "项目名称": ["P-A", "P-B", "P-C"],
            "签约日期": ["2026/6/3", "bad-date", ""],
            "金额": ["100", "200", "x"],
        }),
    }
    DeliveryReportEngine(db_path).persist("202610", raw)
    return db_path


@pytest.fixture
def svc(seeded):
    return CalibrationService(seeded)


def _seed_legend(db_path, col_values):
    """向 md_reference 写 legend_config（枚举允许集合），模拟 seed_legend。"""
    conn = _db.get_connection(db_path)
    try:
        conn.execute("DELETE FROM md_reference WHERE data_type='legend_config'")
        conn.execute(
            "INSERT INTO md_reference (data_type, code, label, extra, sort_order, enabled) "
            "VALUES ('legend_config', '__header__', '表头行', ?, 0, 0)",
            (json.dumps({"状态": "状态"}, ensure_ascii=False),))
        for i, v in enumerate(col_values, 1):
            conn.execute(
                "INSERT INTO md_reference (data_type, code, label, extra, sort_order, enabled) "
                "VALUES ('legend_config', ?, ?, ?, ?, 1)",
                (v, v, json.dumps({"状态": v}, ensure_ascii=False), i))
        conn.commit()
    finally:
        conn.close()


_STATUS_8 = ["义务已拆分", "交付邮件交接中", "交付邮件已归档", "实施未开始",
             "实施进行中", "实施已完成", "验收文件交接中", "验收文件已归档"]


@pytest.fixture
def enum_seeded(db_path):
    """异常项目 sheet + legend 状态列 8 值（对齐 DESIGN-DETAIL §2.3.1）。"""
    raw = {"异常项目": pd.DataFrame({
        "项目名称": ["P-X", "P-Y"],
        "异常报备日期": ["2026/6/1", "2026/6/2"],
        "状态": ["实施未开始", "义务已拆分"],
    })}
    DeliveryReportEngine(db_path).persist("202610", raw)
    _seed_legend(db_path, _STATUS_8)
    return db_path


def _raw_cell(db_path, sheet, row, col):
    conn = _db.get_connection(db_path)
    try:
        data = json.loads(conn.execute(
            "SELECT data FROM dr_sheet_row WHERE month='202610' "
            "AND sheet=? AND row_index=?", (sheet, row)).fetchone()["data"])
        return data.get(col)
    finally:
        conn.close()


# ─── 1. upsert：新增 / 修改 / 原值快照 ───

def test_upsert_created(svc):
    r = svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05",
                   "日期修正", "gateway-owner")
    assert r["action"] == "created" and r["status"] == "active"
    assert isinstance(r["id"], int)


def test_upsert_snapshots_original_value(svc, seeded):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    lst = svc.list_calibrations("202610")["items"]
    assert lst[0]["original_value"] == "bad-date"
    assert lst[0]["corrected_value"] == "2026-06-05"


def test_upsert_revise_keeps_single_active_and_history(svc, seeded):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r1", "op")
    r2 = svc.upsert("202610", "签约", 1, "签约日期", "2026-06-06", "r2", "op")
    assert r2["action"] == "revised"
    actives = svc.list_calibrations("202610", status="active")["items"]
    assert len(actives) == 1
    assert actives[0]["corrected_value"] == "2026-06-06"
    assert actives[0]["previous_value"] == "2026-06-05"
    conn = _db.get_connection(seeded)
    try:
        h = conn.execute(
            "SELECT change_type, corrected_value FROM dr_calibration_history "
            "ORDER BY id").fetchall()
    finally:
        conn.close()
    assert [dict(x)["change_type"] for x in h] == ["revise"]
    assert dict(h[0])["corrected_value"] == "2026-06-05"


def test_recreate_after_revoke_allowed(svc):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    svc.revoke("202610", "签约", 1, "签约日期", "op")
    r = svc.upsert("202610", "签约", 1, "签约日期", "2026-07-01", "重做", "op")
    assert r["action"] == "created"
    assert svc.overview("202610")["active_calibrations"] == 1


# ─── 2. 原始层不可变（AC-02 红线）───

def test_upsert_never_mutates_raw_row(svc, seeded):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-09", "r2", "op")
    svc.revoke("202610", "签约", 1, "签约日期", "op")
    assert _raw_cell(seeded, "签约", 1, "签约日期") == "bad-date"


# ─── 3. apply_overlays：唯一口径 / 不改入参 / 告警 ───

def test_apply_overlays_replaces_value(svc, seeded):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    raw = DeliveryReportEngine(seeded).load("202610")
    eff = svc.apply_overlays("202610", raw)
    assert list(eff["签约"]["签约日期"]) == ["2026/6/3", "2026-06-05", ""]


def test_apply_overlays_does_not_mutate_input(svc, seeded):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    raw = DeliveryReportEngine(seeded).load("202610")
    before = list(raw["签约"]["签约日期"])
    svc.apply_overlays("202610", raw)
    assert list(raw["签约"]["签约日期"]) == before


def test_apply_overlays_warns_missing_column(svc, seeded):
    # 校准一个列，然后给一个缺该列的 raw → 告警不抛异常
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    raw = {"签约": pd.DataFrame({"合同编号": ["C001", "C002"]})}
    eff = svc.apply_overlays("202610", raw)
    w = eff["__warnings__"]
    assert any(x["reason"] == "column_missing_after_regenerate" for x in w)


def test_apply_overlays_warns_row_out_of_range(svc, seeded):
    svc.upsert("202610", "签约", 99, "签约日期", "2026-06-05", "r", "op")
    raw = DeliveryReportEngine(seeded).load("202610")
    eff = svc.apply_overlays("202610", raw)
    w = eff["__warnings__"]
    assert any(x["reason"] == "row_out_of_range" for x in w)


# ─── 4. 保存前置校验（AC-10）───

def test_reject_invalid_date(svc):
    with pytest.raises(CalibrationError) as ei:
        svc.upsert("202610", "签约", 0, "签约日期", "not-a-date", "r", "op")
    assert ei.value.code == "INVALID_TYPE"


def test_reject_impossible_calendar_date(svc):
    with pytest.raises(CalibrationError):
        svc.upsert("202610", "签约", 0, "签约日期", "2026-13-40", "r", "op")


def test_reject_invalid_numeric(svc):
    with pytest.raises(CalibrationError) as ei:
        svc.upsert("202610", "签约", 2, "金额", "abc", "r", "op")
    assert ei.value.code == "INVALID_TYPE"


def test_accept_valid_numeric_and_text(svc):
    svc.upsert("202610", "签约", 2, "金额", "300.5", "r", "op")
    svc.upsert("202610", "签约", 0, "项目名称", "新项目名", "r", "op")
    assert svc.overview("202610")["active_calibrations"] == 2


# ─── 4.1 枚举校验（U-10，DESIGN-DETAIL §2.3.1）───

def test_reject_invalid_enum_value(enum_seeded):
    svc = CalibrationService(enum_seeded)
    with pytest.raises(CalibrationError) as ei:
        svc.upsert("202610", "异常项目", 0, "状态",
                   "不存在的状态", "r", "op")
    assert ei.value.code == "INVALID_VALUE"


def test_accept_valid_enum_value(enum_seeded):
    svc = CalibrationService(enum_seeded)
    r = svc.upsert("202610", "异常项目", 0, "状态",
                   "实施已完成", "状态修正", "op")
    assert r["status"] == "active"


def test_enum_legacy_dead_config_removed():
    """废弃配置：签约.履约状态 列不存在，映射表不应再包含。"""
    from bdms.modules.delivery_report.validator import ENUM_COLS
    assert "签约" not in ENUM_COLS or "履约状态" not in ENUM_COLS.get("签约", {})
    assert ENUM_COLS.get("异常项目", {}).get("状态") == "状态"


def test_enum_non_mapped_column_still_text(enum_seeded):
    """非映射 text 列不因 legend 存在而误阻断（降级口径）。"""
    svc = CalibrationService(enum_seeded)
    svc.upsert("202610", "异常项目", 0, "项目名称",
               "全新项目名", "改名", "op")
    assert svc.overview("202610")["active_calibrations"] == 1


def test_reject_empty_reason(svc):
    with pytest.raises(CalibrationError) as ei:
        svc.upsert("202610", "签约", 0, "签约日期", "2026-06-01", "  ", "op")
    assert ei.value.code == "EMPTY_REASON"


def test_reject_empty_operator(svc):
    with pytest.raises(CalibrationError) as ei:
        svc.upsert("202610", "签约", 0, "签约日期", "2026-06-01", "r", "")
    assert ei.value.code == "EMPTY_OPERATOR"


def test_empty_value_passes_type_check(svc):
    # 清空值不触发类型规则（空值由非空规则管）
    svc.upsert("202610", "签约", 1, "签约日期", "", "清空", "op")
    assert svc.list_calibrations("202610", status="active")["items"][0][
        "corrected_value"] == ""


# ─── 5. revoke / 查询 / 台账 / issue 回填 ───

def test_revoke_not_found(svc):
    with pytest.raises(CalibrationError) as ei:
        svc.revoke("202610", "签约", 0, "签约日期", "op")
    assert ei.value.code == "NOT_FOUND"


def test_revoke_writes_history_and_status(svc, seeded):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    r = svc.revoke("202610", "签约", 1, "签约日期", "op")
    assert r["status"] == "revoked"
    conn = _db.get_connection(seeded)
    try:
        ct = conn.execute(
            "SELECT change_type FROM dr_calibration_history").fetchall()
        status = conn.execute(
            "SELECT status, resolved_at FROM dr_calibration").fetchone()
    finally:
        conn.close()
    assert dict(ct[0])["change_type"] == "revoke"
    assert dict(status)["status"] == "revoked"
    assert dict(status)["resolved_at"]


def test_list_filters(svc):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    svc.revoke("202610", "签约", 1, "签约日期", "op")
    svc.upsert("202610", "异常项目", 0, "异常报备日期", "2026-06-01", "r", "op")
    assert svc.list_calibrations("202610", status="active")["total"] == 1
    # 签约那条 created→revoked 是同一条记录；异常项目是另一条
    assert svc.list_calibrations("202610", sheet="签约")["total"] == 1
    assert svc.list_calibrations("202610", sheet="异常项目")["total"] == 1
    assert svc.list_calibrations("202610", row_index=1)["total"] == 1


def test_overview_counts_by_sheet(svc):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op")
    svc.upsert("202610", "异常项目", 0, "异常报备日期", "2026-06-01", "r", "op")
    ov = svc.overview("202610")
    assert ov["active_calibrations"] == 2
    assert ov["by_sheet"] == {"签约": 1, "异常项目": 1}
    assert ov["review_locked"] is False


def test_ledger_rows_column_order(svc):
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "原因X", "op")
    rows = svc.ledger_rows("202610")
    assert len(rows) == 1
    row = rows[0]
    # [月份, sheet, 行号, 列名, 原始值, 校准值, 操作人, 时间, 原因, 状态]
    assert row[0] == "202610" and row[1] == "签约" and row[2] == 1
    assert row[3] == "签约日期" and row[4] == "bad-date"
    assert row[5] == "2026-06-05" and row[6] == "op"
    assert row[8] == "原因X" and row[9] == "active"


def test_upsert_backfills_issue_corrected_value(svc, seeded):
    conn = _db.get_connection(seeded)
    try:
        # dr_import_validation 表存在；插入一条 pending issue
        cols = [r[1] for r in conn.execute("PRAGMA table_info(dr_import_validation)")]
        cur = conn.execute(
            "INSERT INTO dr_import_validation (month, sheet, row_index, column_name, "
            "rule_code, severity, message, original_value, status) "
            "VALUES ('202610','签约',1,'签约日期','R_DATE','ERROR','坏日期','bad-date','pending')")
        issue_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r", "op",
               issue_id=issue_id)
    conn = _db.get_connection(seeded)
    try:
        backfilled = conn.execute(
            "SELECT corrected_value FROM dr_import_validation WHERE id=?",
            (issue_id,)).fetchone()
    finally:
        conn.close()
    assert dict(backfilled)["corrected_value"] == "2026-06-05"


# ─── 6. 旧路径收敛（Phase7）：原始层永不修改红线 ───

def test_raw_row_identical_after_any_calibration(svc, seeded):
    """校准/修改/撤销任意次数后，dr_sheet_row 与生成时完全一致（AC-02 回归锁定）。"""
    import json as _json
    conn = _db.get_connection(seeded)
    try:
        before = conn.execute(
            "SELECT data FROM dr_sheet_row WHERE month='202610' "
            "AND sheet='签约' ORDER BY row_index").fetchall()
    finally:
        conn.close()
    before_data = [dict(r)["data"] for r in before]

    # 同一单元格反复校准 3 次 + 撤销 + 再校准
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-05", "r1", "op")
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-06", "r2", "op")
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-07", "r3", "op")
    svc.revoke("202610", "签约", 1, "签约日期", "op")
    svc.upsert("202610", "签约", 1, "签约日期", "2026-06-08", "r4", "op")
    # 另一单元格校准
    svc.upsert("202610", "签约", 2, "金额", "300", "r5", "op")

    conn = _db.get_connection(seeded)
    try:
        after = conn.execute(
            "SELECT data FROM dr_sheet_row WHERE month='202610' "
            "AND sheet='签约' ORDER BY row_index").fetchall()
    finally:
        conn.close()
    after_data = [dict(r)["data"] for r in after]
    assert after_data == before_data


def test_service_apply_fixes_uses_overlay(svc, seeded):
    """service.apply_fixes 收敛：写校准表而非 dr_sheet_row（旧路径回归锁定）。"""
    from bdms.modules.delivery_report.service import DeliveryReportService
    svc2 = DeliveryReportService(seeded)
    r = svc2.apply_fixes("202610", [
        {"sheet": "签约", "row_index": 1, "col": "签约日期",
         "value": "2026-06-05", "reason": "legacy收敛", "operator": "op"},
    ])
    assert r["applied"] == 1
    # 校准表有记录
    lst = svc.list_calibrations("202610", status="active")
    assert lst["total"] == 1
    assert lst["items"][0]["corrected_value"] == "2026-06-05"
    # 原始行未变
    import json as _json
    conn = _db.get_connection(seeded)
    try:
        data = _json.loads(conn.execute(
            "SELECT data FROM dr_sheet_row WHERE month='202610' "
            "AND sheet='签约' AND row_index=1").fetchone()["data"])
    finally:
        conn.close()
    assert data["签约日期"] == "bad-date"
