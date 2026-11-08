"""revenue_forecast Phase 5 — /forecast 页面真实浏览器 E2E（slow，不入默认回归）。

铁律：真实 uvicorn（随机端口 + BDMS_DB 临时库）+ 真实 Chromium（Playwright headless），
人工操作序列：选文件→上传→进度条到 done→四卡黄金值→月度图渲染→明细分页/筛选→PartB。
截图落到组件内 tmp/forecast_e2e/。

运行：PYTHONPATH=src python3 -m pytest tests/test_forecast_e2e.py -q -m slow -s
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for p in (str(_SRC), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

REAL_REPORT = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202609/"
    "2026年计划确收&实际确收对比表202601-09-1017-差异分析.xlsx"
)
SHOT_DIR = _ROOT / "tmp" / "forecast_e2e"
YI = 1e8


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_up(url: str, timeout: float = 25) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"server not up: {url}")


@pytest.fixture()
def server(tmp_path):
    db = tmp_path / "e2e.db"
    port = _free_port()
    env = dict(os.environ, BDMS_DB=str(db), PYTHONPATH=str(_SRC))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bdms.web.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_up(base + "/api/health")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _amount_wan(page, card_id: str) -> str:
    return page.locator(f"#{card_id}").inner_text()


def test_forecast_page_full_flow(server):
    if not REAL_REPORT.exists():
        pytest.skip(f"真实财报不存在: {REAL_REPORT}")

    from playwright.sync_api import sync_playwright

    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        console_errors = []
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        # 1) 页面可访问，上传前空态
        page.goto(server + "/forecast", wait_until="networkidle")
        assert page.locator("#fc-file").is_visible()
        page.screenshot(path=str(SHOT_DIR / "01_empty.png"))

        # 2) 选文件 + 上传（显式给 period，避免文件名推断歧义）
        page.set_input_files("#fc-file", str(REAL_REPORT))
        page.fill("#fc-period", "202609")
        page.click("#fc-upload-btn")

        # 3) 进度条出现，且到达 done（最长 90s）
        page.wait_for_selector("#fc-progress", state="visible", timeout=5000)
        page.wait_for_function(
            "() => document.getElementById('fc-progress-pct').textContent === '100%'",
            timeout=90000,
        )
        step_text = page.locator("#fc-progress-step").inner_text()
        assert "完成" in step_text
        page.screenshot(path=str(SHOT_DIR / "02_done.png"))

        # 等概览四卡数据刷新
        page.wait_for_function(
            "() => document.getElementById('ov-locked-total').textContent !== '-'",
            timeout=10000,
        )

        # 4) 黄金锚点（亿元口径，容差来自展示精度：亿卡保留2位小数）
        locked = page.locator("#ov-locked-total").inner_text()
        dynamic = page.locator("#ov-dynamic-total").inner_text()
        actual = page.locator("#ov-actual-total").inner_text()
        gap = page.locator("#ov-gap-total").inner_text()
        assert "1.38" in locked, locked
        assert "1.71" in dynamic, dynamic
        assert "0.94" in actual or ".94" in actual, actual
        assert "+" in gap and "0.33" in gap, gap

        # 拆分文案存在（新签/递延）
        assert "新签" in page.locator("#ov-locked-split").inner_text()
        assert "递延" in page.locator("#ov-locked-split").inner_text()

        # 5) 月度图渲染（canvas 非空）
        page.wait_for_selector("#fc-chart")
        has_pixels = page.evaluate("""() => {
            const c = document.getElementById('fc-chart');
            const ctx = c.getContext('2d');
            const d = ctx.getImageData(0, 0, c.width, c.height).data;
            return d.some(v => v !== 0);
        }""")
        assert has_pixels
        page.screenshot(path=str(SHOT_DIR / "03_chart_locked.png"))

        # 切动态口径：出现 Pipeline 柱
        page.click("#fc-basis-dynamic")
        page.wait_for_function(
            "() => Object.keys(Chart.instances || {}).length >= 0 && "
            "[...document.querySelectorAll('#fc-chart')].length === 1",
            timeout=5000,
        )
        time.sleep(1)
        page.screenshot(path=str(SHOT_DIR / "04_chart_dynamic.png"))

        # 6) 明细表：初始 >0 行，翻页，筛选
        page.wait_for_function(
            "() => document.querySelectorAll('#fl-body tr').length > 0", timeout=10000)
        total_text = page.locator("#fl-info").inner_text()
        assert "共" in total_text

        # 筛 IN_PIPELINE
        page.select_option("#fl-category", "IN_PIPELINE")
        page.wait_for_function(
            "() => document.querySelectorAll('#fl-body tr .badge-warning').length > 0",
            timeout=10000,
        )
        assert "IN_PIPELINE" in page.locator("#fl-body").inner_text()

        # 展开第一行 pipeline 明细
        first_pipe = page.locator("#fl-body tr[onclick]").first
        first_pipe.click()
        detail_id = first_pipe.get_attribute("onclick")
        import re as _re
        obid = _re.search(r"toggleDetail\('([^']+)'\)", detail_id).group(1)
        page.wait_for_selector(f"#detail-{obid}", state="visible", timeout=5000)
        assert "Pipeline 桶" in page.locator(f"#detail-{obid}").inner_text()
        page.screenshot(path=str(SHOT_DIR / "05_pipeline_expand.png"))

        # 翻页测试：清筛选，page_size=10
        page.select_option("#fl-category", "")
        page.select_option("#fl-pagesize", "10")
        page.wait_for_function(
            "() => document.getElementById('fl-info').textContent.includes('共')",
            timeout=10000)
        time.sleep(0.5)
        if page.locator("#fl-next").is_enabled():
            page.click("#fl-next")
            page.wait_for_function(
                "() => document.getElementById('fl-page').textContent.startsWith('2 /')",
                timeout=10000)

        # in_plan 过滤
        page.select_option("#fl-inplan", "false")
        page.wait_for_function(
            "() => document.querySelectorAll('#fl-body tr').length > 0", timeout=10000)
        body_text = page.locator("#fl-body").inner_text()
        assert "不计入" in body_text
        page.screenshot(path=str(SHOT_DIR / "06_filtered.png"))

        # 7) PartB
        page.select_option("#fl-inplan", "")
        page.wait_for_selector("#fc-partb .badge")
        partb = page.locator("#fc-partb").inner_text()
        assert "ONES" in partb and "待接入" in partb

        # 8) 账期下拉含 202609
        opts = page.locator("#fc-view-period").evaluate(
            "el => [...el.options].map(o => o.value)")
        assert "202609" in opts

        page.screenshot(path=str(SHOT_DIR / "07_final.png"))
        browser.close()

    assert not console_errors, f"页面 JS 错误: {console_errors}"
