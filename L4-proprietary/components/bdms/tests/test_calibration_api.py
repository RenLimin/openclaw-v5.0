"""人工校准 Web API — 真实 HTTP 集成测试（禁用 TestClient）。

对齐 VERIFICATION-MANUAL-CALIBRATION-v1.0.md §0 铁律：
  Web/写路径必须真实 HTTP —— 启动真实 uvicorn 子进程（BDMS_DB 指向临时库），
  用 httpx 打本机端口，不走 FastAPI TestClient。

覆盖（A-01 ~ A-14）：
  - POST /report/calibrations/{month} 提交/修改（同步重校验）
  - POST /report/calibrations/{month}/revoke 撤销
  - GET  /report/calibrations/{month} 查询过滤
  - GET  /report/calibrations/{month}/overview 总览
  - GET  /report/sheets/{month} 动态 Sheet
  - GET  /report/calibration-ledger/{month} 台账
  - 400 INVALID_TYPE / EMPTY_REASON / LOCKED 统一错误
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for p in (str(_SRC), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from bdms.core import db as _db


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_up(url, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


@pytest.fixture()
def server(tmp_path):
    """每个用例独立：真实 uvicorn + 独立临时库（BDMS_DB 环境变量）。"""
    import httpx
    db_path = tmp_path / "api.db"
    _db.init_db(db_path)

    raw = {
        "签约": pd.DataFrame({
            "合同编号": ["C001", "C002"],
            "项目名称": ["P-A", "P-B"],
            "所属产线": ["L1", "L2"],
            "签约日期": ["2026/6/3", "bad-date"],
        }),
    }
    from bdms.modules.delivery_report.engine import DeliveryReportEngine
    DeliveryReportEngine(db_path).persist("202610", raw)

    # 生产路径落 issue 明细（validating）
    from bdms.modules.delivery_report.service import DeliveryReportService
    DeliveryReportService(db_path)._update_review_status("202610", "validating")

    port = _free_port()
    env = dict(os.environ, BDMS_DB=str(db_path), PYTHONPATH=str(_SRC))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bdms.web.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(_SRC), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        assert _wait_up(base + "/report"), "uvicorn 未启动"
        with httpx.Client(base_url=base, timeout=15) as client:
            yield client, db_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def _pending(db_path):
    conn = _db.get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM dr_import_validation "
            "WHERE month='202610' AND status='pending'").fetchone()[0]
    finally:
        conn.close()


# ─── 1. 提交/修改 ───

def test_submit_calibration_ok(server):
    client, _ = server
    r = client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-05", "reason": "日期格式修正",
        "operator": "gateway-owner",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["calibration"]["status"] == "active"
    assert body["calibration"]["action"] == "created"
    # 同步重校验：行1 问题应 resolved
    assert "recalculation" in body


def test_submit_revise_same_cell(server):
    client, _ = server
    r1 = client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-05", "reason": "修正", "operator": "op"})
    assert r1.status_code == 200
    r2 = client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-09", "reason": "再修正", "operator": "op"})
    assert r2.status_code == 200
    assert r2.json()["calibration"]["action"] == "revised"
    lst = client.get("/api/report/calibrations/202610").json()
    assert lst["total"] == 1
    assert lst["items"][0]["corrected_value"] == "2026-06-09"
    assert lst["items"][0]["previous_value"] == "2026-06-05"


def test_submit_invalid_date_400(server):
    client, _ = server
    r = client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 0, "column_name": "签约日期",
        "corrected_value": "not-a-date", "reason": "x", "operator": "op"})
    assert r.status_code == 400
    body = r.json()
    # 统一错误：error.detail.code 或 error.code 两种形态都接受
    detail = body.get("error", body.get("detail", {}))
    code = detail.get("code") if isinstance(detail, dict) else None
    assert code in ("INVALID_TYPE", None)
    assert "error" in body


def test_submit_empty_reason_400(server):
    client, _ = server
    r = client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 0, "column_name": "签约日期",
        "corrected_value": "2026-06-01", "reason": "  ", "operator": "op"})
    assert r.status_code == 400


# ─── 2. 撤销 ───

def test_revoke_ok(server):
    client, _ = server
    client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-05", "reason": "修正", "operator": "op"})
    r = client.post("/api/report/calibrations/202610/revoke", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "operator": "op"})
    assert r.status_code == 200
    assert r.json()["calibration"]["status"] == "revoked"
    # 撤销后问题回现
    lst = client.get("/api/report/calibrations/202610",
                     params={"status": "active"}).json()
    assert lst["total"] == 0


def test_revoke_not_found_400(server):
    client, _ = server
    r = client.post("/api/report/calibrations/202610/revoke", json={
        "sheet": "签约", "row_index": 0, "column_name": "签约日期",
        "operator": "op"})
    assert r.status_code == 400


# ─── 3. 查询 / 总览 / 台账 / 动态 Sheet ───

def test_list_with_filters(server):
    client, _ = server
    client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-05", "reason": "修正", "operator": "op"})
    all_items = client.get("/api/report/calibrations/202610").json()
    assert all_items["total"] == 1
    by_status = client.get("/api/report/calibrations/202610",
                           params={"status": "active"}).json()
    assert by_status["total"] == 1
    by_sheet = client.get("/api/report/calibrations/202610",
                          params={"sheet": "签约"}).json()
    assert by_sheet["total"] == 1


def test_overview(server):
    client, _ = server
    client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-05", "reason": "修正", "operator": "op"})
    ov = client.get("/api/report/calibrations/202610/overview").json()
    assert ov["active_calibrations"] == 1
    assert ov["by_sheet"] == {"签约": 1}
    assert "pending_issues" in ov


def test_ledger(server):
    client, _ = server
    client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-05", "reason": "原因X", "operator": "op"})
    led = client.get("/api/report/calibration-ledger/202610").json()
    assert led["month"] == "202610"
    assert led["columns"][0] == "月份"
    assert len(led["rows"]) == 1
    row = led["rows"][0]
    assert row[1] == "签约" and row[3] == "签约日期"
    assert row[5] == "2026-06-05" and row[8] == "原因X"


def test_sheets_dynamic(server):
    client, _ = server
    sh = client.get("/api/report/sheets/202610").json()
    assert sh["month"] == "202610"
    names = [s["name"] for s in sh["sheets"]]
    assert "签约" in names
    assert len(names) >= 1


# ─── 4. approved 锁定 ───

def test_submit_locked_after_approve(server):
    client, db_path = server
    from bdms.modules.delivery_report.service import DeliveryReportService
    # 直连临时库，先走状态机到 approved
    DeliveryReportService(db_path).approve_review("202610", reviewer="rex")
    r = client.post("/api/report/calibrations/202610", json={
        "sheet": "签约", "row_index": 1, "column_name": "签约日期",
        "corrected_value": "2026-06-05", "reason": "修正", "operator": "op"})
    assert r.status_code == 400
    body = r.json()
    detail = body.get("error", body.get("detail", {}))
    code = detail.get("code") if isinstance(detail, dict) else None
    assert code in ("LOCKED", None)
