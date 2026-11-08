"""revenue_forecast Phase 6 — GET /api/forecast/export 真实 HTTP 测试。

铁律：Web 功能验收必须用真实 HTTP（同 test_forecast_api.py：真实 uvicorn
子进程 + BDMS_DB 临时库 + httpx），禁用 FastAPI TestClient。

流程：上传真实财报 → 轮询 done → 调 export 下载 xlsx → openpyxl 重开，
断言 5 个 Sheet 齐全、汇总金额与 overview 一致、明细行数对、逐月合计闭环。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import httpx
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for p in (str(_SRC), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from bdms.core import db as _db  # noqa: E402

REAL_REPORT = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
)
YI = 1e8

SHEETS = ["汇总", "锁定逐月", "动态逐月", "履约明细", "风险与排除"]
RISK_CATEGORIES = ["FUTURE_YEAR", "EXCEPTION", "TERMINATED",
                   "NOT_STARTED", "MISSING_DATE"]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_up(url: str, timeout: float = 25) -> bool:
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
    db_path = tmp_path / "forecast_export.db"
    _db.init_db(db_path)
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
        assert _wait_up(base + "/api/health"), "uvicorn 未在限时内启动"
        with httpx.Client(base_url=base, timeout=60) as client:
            yield client
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def _upload_and_wait(client: httpx.Client) -> None:
    resp = client.post(
        "/api/forecast/upload",
        files={"file": (REAL_REPORT.name, REAL_REPORT.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"period": "202609", "year": "2026"},
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    end = time.time() + 90
    while time.time() < end:
        pr = client.get(f"/api/forecast/progress/{job_id}").json()
        if pr["status"] in ("done", "failed"):
            assert pr["status"] == "done", pr
            return
        time.sleep(0.5)
    raise AssertionError("upload job 超时")


@pytest.mark.skipif(not REAL_REPORT.is_file(), reason="真实财报 fixture 不存在")
def test_forecast_export_xlsx(server, tmp_path):
    client = server
    _upload_and_wait(client)
    overview = client.get(
        "/api/forecast/overview", params={"period": "202609"}).json()
    lines_meta = client.get(
        "/api/forecast/lines",
        params={"period": "202609", "page": 1, "page_size": 1}).json()
    total_lines = lines_meta["total"]

    # 1) 调 export，跟随文件流下载
    resp = client.get("/api/forecast/export", params={"period": "202609"})
    assert resp.status_code == 200, resp.text
    cd = resp.headers.get("content-disposition", "")
    assert "202609" in cd
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml")
    out = tmp_path / "exported.xlsx"
    out.write_bytes(resp.content)
    assert out.stat().st_size > 10000

    # 2) openpyxl 重开校验
    from openpyxl import load_workbook
    wb = load_workbook(out, read_only=True, data_only=True)
    assert wb.sheetnames == SHEETS

    # ── 汇总 Sheet：金额与 overview 一致 ──
    ws = wb["汇总"]
    summary = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
               for r in range(4, 9)}
    assert summary["锁定口径"] == pytest.approx(
        overview["locked"]["total"], rel=1e-9)
    assert summary["动态口径"] == pytest.approx(
        overview["dynamic"]["total"], rel=1e-9)
    assert summary["实际累计"] == pytest.approx(overview["actual"], rel=1e-9)
    assert summary["差异(动态-锁定)"] == pytest.approx(overview["gap"], rel=1e-9)
    assert summary["其中：pipeline"] == pytest.approx(
        overview["dynamic"]["pipeline"], rel=1e-9)
    # 黄金锚点
    assert summary["锁定口径"] == pytest.approx(1.384 * YI, rel=2e-3)
    assert summary["动态口径"] == pytest.approx(1.710 * YI, rel=2e-3)

    # 万元列存在且换算正确
    assert ws.cell(row=4, column=3).value == pytest.approx(
        overview["locked"]["total"] / 1e4, rel=1e-9)

    # ── 锁定逐月：12 行 + 合计闭环 ──
    ws = wb["锁定逐月"]
    months = [ws.cell(row=r, column=2).value for r in range(2, 14)]
    assert len(months) == 12
    assert ws.cell(row=14, column=1).value == "合计"
    assert ws.cell(row=14, column=2).value == pytest.approx(
        overview["locked"]["total"], rel=1e-6)
    assert sum(months) == pytest.approx(overview["locked"]["total"], rel=1e-6)

    # ── 动态逐月：12 月 + pipeline + 合计闭环 ──
    ws = wb["动态逐月"]
    due = [ws.cell(row=r, column=2).value for r in range(2, 14)]
    assert ws.cell(row=14, column=1).value == "pipeline"
    pipeline = ws.cell(row=14, column=2).value
    assert pipeline == pytest.approx(
        overview["dynamic"]["pipeline"], rel=1e-9)
    assert ws.cell(row=15, column=1).value == "合计"
    assert ws.cell(row=15, column=2).value == pytest.approx(
        overview["dynamic"]["total"], rel=1e-6)
    assert sum(due) + pipeline == pytest.approx(
        overview["dynamic"]["total"], rel=1e-6)

    # ── 履约明细：行数 == forecast_line 全量 ──
    ws = wb["履约明细"]
    assert ws.cell(row=1, column=1).value == "履约义务ID"
    assert ws.cell(row=1, column=13).value == "动态分类"
    data_rows = ws.max_row - 1
    assert data_rows == total_lines
    assert data_lines_sanity(ws, total_lines)

    # ── 风险与排除：五类计数 + 明细行数闭环 ──
    ws = wb["风险与排除"]
    counts = {}
    for r in range(4, 9):
        counts[ws.cell(row=r, column=1).value] = ws.cell(row=r, column=2).value
    assert set(counts) == set(RISK_CATEGORIES)
    assert all(v > 0 for v in counts.values())

    # 明细区从表头行（由实现固定：分类汇总 5 行后空 2 行，表头）
    header_row = None
    for r in range(9, 14):
        if ws.cell(row=r, column=2).value == "履约义务ID":
            header_row = r
            break
    assert header_row is not None
    detail_n = ws.max_row - header_row
    assert detail_n == sum(counts.values())
    wb.close()


def data_lines_sanity(ws, total_lines) -> bool:
    """抽查明细：是否计入列取值为 是/否，存在 DUE_2026 与 IN_PIPELINE 行。"""
    cats = set()
    in_plan_vals = set()
    # read_only 模式下遍历，避免逐 cell 慢
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        cats.add(row[12])
        in_plan_vals.add(row[14])
        if i > 4000:
            break
    return cats >= {"DUE_2026", "IN_PIPELINE"} and in_plan_vals <= {"是", "否"}


@pytest.mark.skipif(not REAL_REPORT.is_file(), reason="真实财报 fixture 不存在")
def test_forecast_export_default_period(server, tmp_path):
    """period 缺省：导出 current 账期。"""
    client = server
    _upload_and_wait(client)
    resp = client.get("/api/forecast/export")
    assert resp.status_code == 200
    assert "202609" in resp.headers.get("content-disposition", "")
    out = tmp_path / "default.xlsx"
    out.write_bytes(resp.content)
    from openpyxl import load_workbook
    wb = load_workbook(out, read_only=True)
    assert wb.sheetnames == SHEETS
    wb.close()


def test_forecast_export_unknown_period_400(server):
    client = server
    resp = client.get("/api/forecast/export", params={"period": "209901"})
    assert resp.status_code == 400
