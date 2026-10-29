"""人工校准 E2E（真实服务器 + 真实浏览器，模拟人工操作）。

对齐 VERIFICATION-MANUAL-CALIBRATION-v1.0.md §3.3。
  - 启动真实 uvicorn（BDMS_DB 指向临时库），非 TestClient
  - Playwright 驱动真实 Chromium 点按钮/填对话框，不跳过 UI
  - 覆盖：E-01 问题清单校准、E-04 数据浏览单元格校准、E-06 动态 Sheet
运行：python3 -m pytest tests/e2e_calibration.py
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
for p in (str(_SRC), str(_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from bdms.core import db as _db

@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    out = yield
    rep = out.get_result()
    setattr(item, 'rep_call', rep)
from bdms.modules.delivery_report.engine import DeliveryReportEngine


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_up(url, timeout=20):
    import urllib.request
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.3)
    return False


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    dbp = tmp / "e2e.db"
    _db.init_db(dbp)
    # 造数据：行0 合同编号空；行1 签约日期非法
    raw = {"签约": pd.DataFrame({
        "合同编号": ["", "C-002"],
        "项目名称": ["P-1", "P-2"],
        "所属产线": ["产线A", "产线B"],
        "签约日期": ["2026/6/3", "bad-date"],
        "金额": ["100", "200"],
    })}
    DeliveryReportEngine(dbp).persist("202610", raw)
    # 落 issue（走生产 validating 路径）
    from bdms.modules.delivery_report.service import DeliveryReportService
    DeliveryReportService(dbp).revalidate("202610")

    port = _free_port()
    env = dict(os.environ, BDMS_DB=str(dbp), PYTHONPATH=str(_SRC))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bdms.web.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(_SRC), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        assert _wait_up(base + "/report"), "uvicorn 未启动"
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


@pytest.fixture()
def page(request, server):
    from playwright.sync_api import sync_playwright
    _logs = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.on("console", lambda m: _logs.append(f"[{m.type}] {m.text}") if m.type=="error" else None)
        pg.on("pageerror", lambda e: _logs.append(f"PAGEERROR {e}"))
        pg.goto(server + "/report", wait_until="networkidle")
        yield pg
        if request.node.rep_call.failed:
            print("\n=== BROWSER LOGS ===" + "\n".join(_logs))
        browser.close()


def test_e01_calibrate_from_issues(page):
    """E-01：问题清单点校准 → 填值+原因 → 保存，问题转 confirmed。"""
    # 月份自动选中 202610；切到问题清单
    page.click('.tabs-tab[data-tab="issues"]')
    page.wait_for_selector('#review-issues-list table tbody tr')
    rows = page.locator('#review-issues-list table tbody tr')
    assert rows.count() == 2

    # 第一条（行0，合同编号空）点校准
    page.locator('#review-issues-list table tbody tr').first.locator(
        'button:has-text("校准")').click()
    page.wait_for_selector('#calibration-modal', state='visible')
    # 校验对话框只读字段
    assert page.input_value('#cal-col') == '合同编号'
    assert page.input_value('#cal-original') == ''
    # 填校准值 + 原因
    page.fill('#cal-value', 'C-FIXED-001')
    page.fill('#cal-reason', '源表合同编号缺失，人工补充')
    page.click('#calibration-modal button:has-text("保存校准")')

    # toast 成功
    page.wait_for_selector('#toastContainer >> text=校准已保存')
    page.wait_for_selector('#calibration-modal', state='hidden')

    # 等待该 issue 变 confirmed（重新渲染）
    page.wait_for_function(
        """() => {
          const trs = document.querySelectorAll('#review-issues-list table tbody tr');
          return [...trs].some(tr => tr.innerText.includes('confirmed'));
        }""")
    # 仍剩 1 条 pending（行1 bad-date）
    body = page.locator('#review-issues-stats').inner_text()
    assert '待处理 1' in body


def test_e06_dynamic_sheet_dropdown(page, server):
    """E-06：数据浏览 Sheet 下拉来自接口（动态），与 /sheets 一致。"""
    import json
    import urllib.request
    with urllib.request.urlopen(server + "/api/report/sheets/202610") as r:
        sheets = json.load(r)["sheets"]
    page.click('.tabs-tab[data-tab="browse"]')
    page.wait_for_function(
        """(n) => {
          const sel = document.getElementById('view-sheet');
          return sel && sel.options.length === n;
        }""", arg=len(sheets))
    options = page.locator('#view-sheet option')
    assert options.count() == len(sheets)
    assert options.first.inner_text().startswith(sheets[0]["name"])


def test_e04_calibrate_from_browse_cell(page):
    """E-04：数据浏览点单元格发起校准并保存（行1 bad-date 修正）。"""
    page.click('.tabs-tab[data-tab="browse"]')
    page.wait_for_selector('#data-table-container table tbody tr')
    # 第二数据行（0-based 行1）的「签约日期」列单元格：用表头定位列号
    page.wait_for_function(
        """() => {
          const heads = [...document.querySelectorAll('#data-table-container table thead th')];
          const idx = heads.findIndex(h => h.innerText.trim() === '签约日期');
          if (idx < 0) return false;
          const cell = document.querySelectorAll('#data-table-container table tbody tr')[1].cells[idx];
          cell.click();
          return true;
        }""")
    page.wait_for_selector('#calibration-modal', state='visible')
    assert page.input_value('#cal-col') == '签约日期'
    assert page.input_value('#cal-row') == '1'
    page.fill('#cal-value', '2026-06-05')
    page.fill('#cal-reason', '日期格式错误修正')
    page.click('#calibration-modal button:has-text("保存校准")')
    page.wait_for_selector('#toastContainer >> text=校准已保存')
    # 切问题清单确认 pending 归零（两条都已修复）
    page.click('.tabs-tab[data-tab="issues"]')
    page.wait_for_selector('#review-issues-stats')
    page.wait_for_function(
        """() => document.getElementById('review-issues-stats').innerText.includes('待处理 0')""")
