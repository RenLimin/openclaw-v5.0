"""revenue_analysis Web UI 集成 — 真实 HTTP 测试（/api/revenue-analysis/*）。

铁律（AGENTS.md 测试规范）：Web 功能验收必须用真实 HTTP。
本套件启动真实 uvicorn 子进程（BDMS_DB 指向 tmp 临时库），用 httpx 打本机端口，
禁用 FastAPI TestClient / ASGITransport。

覆盖：
  - GET /revenue-analysis 页面 200 + 关键控件存在；
  - GET /api/revenue-analysis/periods 返回已登记账期；
  - 无数据账期：summary/trend/attribution/alerts 全部 fail-closed → 400；
  - GET /api/revenue-analysis/progress/{不存在} → not_found；
  - GET /api/revenue-analysis/download/{非法} → 404；
  - POST generate 创建 job 并轮询到终态（含失败路径：read 模式无数据 → failed）；
  - 端到端（skipif 真实 202606 源缺失）：导入真实源 → generate → 汇总/趋势/归因可读。
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

REAL_SOURCE = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/"
    "2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx"
)


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
    """真实 uvicorn + 独立临时库；不污染 data/bdms.db。"""
    db_path = tmp_path / "ra_web.db"
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
            yield client, db_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def _poll(client: httpx.Client, job_id: int, timeout: float = 60) -> dict:
    end = time.time() + timeout
    last: dict = {}
    while time.time() < end:
        last = client.get(f"/api/revenue-analysis/progress/{job_id}").json()
        if last["status"] in ("done", "failed", "not_found"):
            return last
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} 超时未结束: {last}")


# ─────────────────────── 契约层（空库）───────────────────────

def test_page_renders(server):
    client, _ = server
    r = client.get("/revenue-analysis")
    assert r.status_code == 200, r.text[:300]
    body = r.text
    for token in ("ra-period", "ra-gen-btn", "ra-exp-btn", "ra-attribution",
                  "ra-trend", "ra-alerts", "确收分析"):
        assert token in body, f"页面缺少 {token}"


def test_periods_empty_returns_list(server):
    client, _ = server
    d = client.get("/api/revenue-analysis/periods").json()
    assert isinstance(d["periods"], list)


@pytest.mark.parametrize("ep", ["summary", "trend", "attribution"])
def test_no_data_fail_closed(server, ep):
    """PRD v1.1 红线：无数据显式报错，不伪造（alerts 例外，见下）。"""
    client, _ = server
    r = client.get(f"/api/revenue-analysis/{ep}/202606")
    assert r.status_code == 400, f"{ep} 应 400，实际 {r.status_code}"


def test_alerts_empty_is_legal_result(server):
    """P2 既定契约（test_service_fail_closed 冻结）：未生成/零预警均返回 []。

    与 summary/trend/attribution 不同，alerts 不抛错——「该账期确实无异常」
    是合法结果；调用方应结合 /periods 判断账期是否已生成。
    此处刻意保持与冻结口径一致，不擅自改语义。
    """
    client, _ = server
    r = client.get("/api/revenue-analysis/alerts/202606")
    assert r.status_code == 200
    assert r.json()["alerts"] == []


def test_progress_not_found(server):
    client, _ = server
    d = client.get("/api/revenue-analysis/progress/999999").json()
    assert d["status"] == "not_found"


def test_download_invalid_job_404(server):
    client, _ = server
    r = client.get("/api/revenue-analysis/download/999999")
    assert r.status_code == 404


def test_generate_read_mode_without_data_fails(server):
    """read 模式无数据 → job 创建成功但终态为 failed（显式失败，非静默）。"""
    client, _ = server
    r = client.post("/api/revenue-analysis/generate",
                    json={"period": "202606", "mode": "read"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    end = _poll(client, job_id)
    assert end["status"] == "failed", end


def test_download_returns_real_file(server, tmp_path):
    """下载端点必须能真正回吐产物（曾踩：模块级缺 Path 导入 → NameError → 500）。"""
    client, db_path = server
    payload = b"PK\x03\x04fake-xlsx-bytes"
    f = tmp_path / "ra_out.xlsx"
    f.write_bytes(payload)
    conn = _db.get_connection(db_path)
    try:
        jid = _db.create_job(conn, "revenue_analysis", "202606", "export")
        _db.update_job_status(conn, jid, "done", 100, message="ok",
                              output_path=str(f))
        conn.commit()
    finally:
        conn.close()
    r = client.get(f"/api/revenue-analysis/download/{jid}")
    assert r.status_code == 200, r.text[:200]
    assert r.content == payload


def test_download_refuses_other_module_output(server, tmp_path):
    """跨模块产物不得被本端点下载（越权读取防护）。"""
    client, db_path = server
    f = tmp_path / "other.xlsx"
    f.write_bytes(b"x")
    conn = _db.get_connection(db_path)
    try:
        jid = _db.create_job(conn, "delivery_report", "202606", "auto")
        _db.update_job_status(conn, jid, "done", 100,
                              output_path=str(f))
        conn.commit()
    finally:
        conn.close()
    r = client.get(f"/api/revenue-analysis/download/{jid}")
    assert r.status_code == 404


def test_invalid_mode_rejected(server):
    client, _ = server
    r = client.post("/api/revenue-analysis/generate",
                    json={"period": "202606", "mode": "bogus"})
    assert r.status_code == 400


# ─────────────────────── 端到端（真实源，重）───────────────────────

@pytest.mark.skipif(not REAL_SOURCE.is_file(), reason="202606 真实源未就位")
def test_e2e_import_generate_and_read(server):
    """真实操作路径：导入 202606 源 → generate(auto) → 汇总/趋势/归因/预警可读。"""
    client, db_path = server
    svc = pytest.importorskip("bdms.modules.revenue_analysis.service")
    from bdms.modules.revenue_analysis.service import RevenueAnalysisService

    st = RevenueAnalysisService(db_path).import_source("202606", REAL_SOURCE)
    assert st, "导入未返回统计"

    r = client.post("/api/revenue-analysis/generate",
                    json={"period": "202606", "mode": "auto"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    end = _poll(client, job_id, timeout=900)
    assert end["status"] == "done", end

    summary = client.get("/api/revenue-analysis/summary/202606").json()
    assert "locked" in summary and "dynamic" in summary
    trend = client.get("/api/revenue-analysis/trend/202606").json()
    assert len(trend["rows"]) >= 15, trend
    attr = client.get("/api/revenue-analysis/attribution/202606").json()
    assert attr["triggered"] > 0
    alerts = client.get("/api/revenue-analysis/alerts/202606").json()
    assert isinstance(alerts["alerts"], list)

    periods = client.get("/api/revenue-analysis/periods").json()["periods"]
    assert "202606" in periods

    ex = client.post("/api/revenue-analysis/export",
                     json={"period": "202606", "mode": "auto"})
    assert ex.status_code == 200
    jd = _poll(client, ex.json()["job_id"], timeout=900)
    assert jd["status"] == "done", jd
    assert jd.get("output_path"), jd
    dl = client.get(f"/api/revenue-analysis/download/{jd['id']}")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/vnd.openxmlformats")
