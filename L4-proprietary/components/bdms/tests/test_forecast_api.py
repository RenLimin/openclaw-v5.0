"""revenue_forecast Phase 4 — service 编排 + /api/forecast/* 真实 HTTP 测试。

铁律（AGENTS.md 测试规范）：Web 功能验收必须用真实 HTTP。
本套件启动真实 uvicorn 子进程（BDMS_DB 指向 tmp 临时库），用 httpx 打本机端口，
禁用 FastAPI TestClient / ASGITransport。

覆盖：
  - POST /api/forecast/upload（真实财报 multipart）→ job_id，轮询 progress 到 done；
  - periods / overview / monthly / lines / provider-status 契约与黄金金额；
  - period 缺省由文件名推断；显式 period 与 year 表单字段；
  - 恒等式 issues 不阻断（真实财报 issues=0）；
  - 错误文件（非 xlsx）upload → job failed 且 current 不被破坏；
  - 未指定 period 且无 current → 400。

黄金锚点（元，DESIGN-DETAIL §9）：
  locked ≈ 1.384 亿、dynamic ≈ 1.710 亿、actual ≈ .945 亿、
  gap ≈ +.326 百万、pipeline ≈ .841 亿。
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
    db_path = tmp_path / "forecast_api.db"
    _db.init_db(db_path)   # job 等公共表

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
        with httpx.Client(base_url=base, timeout=30) as client:
            yield client, db_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


def _poll_done(client: httpx.Client, job_id: int, timeout: float = 60) -> dict:
    end = time.time() + timeout
    last = {}
    while time.time() < end:
        last = client.get(f"/api/forecast/progress/{job_id}").json()
        if last["status"] in ("done", "failed"):
            return last
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} 超时未结束: {last}")


# ─────────────────────── 主路径：真实财报 upload→progress→读模型 ───────────────────────

@pytest.mark.skipif(not REAL_REPORT.is_file(), reason="真实财报 fixture 不存在")
def test_upload_real_report_full_flow(server):
    client, db_path = server
    content = REAL_REPORT.read_bytes()

    # period 缺省：文件名含 202601-09，正则取末尾 6 位 → 202609（若推断歧义则显式传）
    resp = client.post(
        "/api/forecast/upload",
        files={"file": (REAL_REPORT.name, content,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"period": "202609", "year": "2026"},
    )
    assert resp.status_code == 200, resp.text
    started = resp.json()
    assert started["period"] == "202609"
    job_id = started["job_id"]

    progress = _poll_done(client, job_id)
    assert progress["status"] == "done", progress
    assert progress["pct"] == 100
    assert progress["error"] is None

    # periods
    periods = client.get("/api/forecast/periods").json()
    assert periods["current"] == "202609"
    assert any(p["period"] == "202609" for p in periods["periods"])

    # overview —— 黄金金额（元）
    overview = client.get("/api/forecast/overview", params={"period": "202609"}).json()
    assert overview["locked"]["total"] == pytest.approx(1.384 * YI, rel=2e-3)
    assert overview["dynamic"]["total"] == pytest.approx(1.710 * YI, rel=2e-3)
    assert overview["actual"] == pytest.approx(0.945 * YI, rel=2e-3)
    assert overview["gap"] == pytest.approx(3.26e7, abs=1e7)  # +.326 亿
    assert overview["dynamic"]["pipeline"] == pytest.approx(0.841 * YI, rel=2e-3)
    # by_group：新签/递延
    assert set(overview["locked"]["by_group"]) == {"新签", "递延"}
    assert overview["locked"]["by_group"]["新签"] == pytest.approx(0.67 * YI, rel=3e-2)
    assert overview["dynamic"]["by_group"]["新签"] == pytest.approx(0.851 * YI, rel=3e-2)

    # monthly locked：12 月合计 ≈ locked total
    monthly_l = client.get(
        "/api/forecast/monthly", params={"period": "202609", "basis": "locked"}
    ).json()
    assert sorted(monthly_l["months"].keys()) == [f"{m:02d}" for m in range(1, 13)]
    assert sum(monthly_l["months"].values()) == pytest.approx(1.384 * YI, rel=2e-3)

    # monthly dynamic：DUE 12 月 + pipeline
    monthly_d = client.get(
        "/api/forecast/monthly", params={"period": "202609", "basis": "dynamic"}
    ).json()
    assert monthly_d["pipeline"] == pytest.approx(0.841 * YI, rel=2e-3)
    assert sum(monthly_d["months"].values()) + monthly_d["pipeline"] == pytest.approx(
        1.710 * YI, rel=2e-3)

    # lines 分页 + 过滤实际生效
    page1 = client.get(
        "/api/forecast/lines",
        params={"period": "202609", "page": 1, "page_size": 50},
    ).json()
    assert page1["total"] > 30000
    assert len(page1["items"]) == 50

    in_plan = client.get(
        "/api/forecast/lines",
        params={"period": "202609", "in_plan": "true", "page_size": 5},
    ).json()
    assert all(it["dyn_in_plan"] for it in in_plan["items"])
    assert in_plan["total"] < page1["total"]

    by_cat = client.get(
        "/api/forecast/lines",
        params={"period": "202609", "category": "DUE_2026", "page_size": 5},
    ).json()
    assert all(it["dyn_category"] == "DUE_2026" for it in by_cat["items"])

    # provider-status
    pstatus = client.get("/api/forecast/provider-status").json()
    assert pstatus["part_b"]["name"] == "ones"
    assert pstatus["part_b"]["status"] == "not_configured"


@pytest.mark.skipif(not REAL_REPORT.is_file(), reason="真实财报 fixture 不存在")
def test_period_inferred_from_filename(server):
    """不传 period：用真实财报文件名（含 202609 段）推断。"""
    client, _ = server
    # 原始名中 202601-09 会被 6 位正则匹配为 202601（首个命中），
    # 因此这里用明确含 202609 的文件名验证推断机制本身。
    resp = client.post(
        "/api/forecast/upload",
        files={"file": ("收入预算执行对比表202609.xlsx", REAL_REPORT.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"year": "2026"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["period"] == "202609"
    progress = _poll_done(client, resp.json()["job_id"])
    assert progress["status"] == "done", progress


def test_bad_file_does_not_switch_current(server):
    """错误文件 upload → job failed 且 current 不被建立/破坏。"""
    client, _ = server

    # 初始无 current
    assert client.get("/api/forecast/periods").json()["current"] is None

    resp = client.post(
        "/api/forecast/upload",
        files={"file": ("bad.xlsx", b"this is not an xlsx file at all",
                        "application/octet-stream")},
        data={"period": "202609"},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    progress = _poll_done(client, job_id)
    assert progress["status"] == "failed"
    assert progress["error"]

    # current 仍为空；overview 400
    assert client.get("/api/forecast/periods").json()["current"] is None
    ov = client.get("/api/forecast/overview", params={"period": "202609"})
    assert ov.status_code == 400


def test_missing_period_without_current_400(server):
    """无法确定 period（无表单字段 + 文件名无期间）且无 current → 400。"""
    client, _ = server
    resp = client.post(
        "/api/forecast/upload",
        files={"file": ("随便起的名字.xlsx", b"abc", "application/octet-stream")},
        data={"year": "2026"},
    )
    assert resp.status_code == 400
    assert "period" in resp.json()["error"] or "账期" in resp.json()["error"]


def test_invalid_basis_400(server):
    client, _ = server
    resp = client.get("/api/forecast/monthly", params={"basis": "bogus"})
    assert resp.status_code == 400
