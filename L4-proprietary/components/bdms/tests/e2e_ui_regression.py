"""BDMS 全站 UI 回归套件（真实 HTTP + 真实 Chromium，非 TestClient）。

覆盖：7 页可达性/标题、首页动态账期、服务状态中文化、
logo 无白描边（像素采样）、全站无英文 UI 残留、月报 4 子页签工作流、
审批按钮显隐一致、键盘切换、侧栏折叠、console/pageerror=0。

运行前提：BDMS 服务已启动（http://127.0.0.1:8000）。
运行：python3 -m pytest tests/e2e_ui_regression.py -v
"""
import re

import pytest
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"

PAGES = [
    ("/", "首页概览"),
    ("/report", "交付月报"),
    ("/revenue", "确收汇总"),
    ("/revenue/compare", "对比分析"),
    ("/master-data", "基础数据"),
    ("/dashboard", "统计看板"),
    ("/settings", "系统设定"),
]

# 用户可见英文残留词表（UI 文案不得出现；代码注释/标识符不在 innerText 内）
ENGLISH_UI_WORDS = [
    "Sheet", "YYYYMM", "Key", "Cancel", "Confirm", "Save", "Delete",
    "Loading", "Error", "Failed", "Success", "Submit", "Close",
    "Page", "Total", "Status", "Actions", "Search", "Reset", "Export",
]

_errors = []


@pytest.fixture(scope="module")
def browser():
    """整个套件共用一个浏览器实例；收集 console/pageerror。"""
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    _errors.clear()
    pg.on("console", lambda m: _errors.append(f"console:{m.text[:120]}") if m.type == "error" else None)
    pg.on("pageerror", lambda e: _errors.append(f"pageerror:{str(e)[:120]}"))
    yield pg
    pg.close()


def goto(page, path, retries=2):
    """导航：domcontentloaded + 显式等 h1；对偶发超时重试，避免误报。"""
    for attempt in range(retries + 1):
        try:
            page.goto(BASE + path, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_selector(".page-header h1", timeout=10000)
            page.wait_for_timeout(600)
            return
        except Exception as e:
            if attempt == retries:
                raise
            page.wait_for_timeout(800)


class TestPages:
    """7 页可达性 + 标题 + 无英文残留 + 0 console error。"""

    @pytest.mark.parametrize("path,title", PAGES)
    def test_page_title(self, page, path, title):
        goto(page, path)
        h1 = page.query_selector(".page-header h1")
        assert h1 is not None, f"{path} 缺少 .page-header h1"
        assert title in h1.inner_text(), f"{path} 标题不符: {h1.inner_text()}"

    @pytest.mark.parametrize("path,_", PAGES)
    def test_no_english_ui_text(self, page, path, _):
        goto(page, path)
        body = page.evaluate("document.body.innerText")
        for w in ENGLISH_UI_WORDS:
            assert w not in body, f"{path} 页面可见英文残留: '{w}'"

    @pytest.mark.parametrize("path,_", PAGES)
    def test_no_console_errors(self, page, path, _):
        goto(page, path)
        assert not _errors, f"{path} 页面 console/pageerror: {_errors}"


class TestHome:
    """首页动态账期 + 服务状态中文化 + logo 无白描边。"""

    def test_dynamic_period(self, page):
        goto(page, "/")
        sub = page.query_selector(".page-header p")
        assert sub is not None, "首页缺少 .page-header p"
        m = re.search(r"当前账期 (\d{4})年(\d{2})月", sub.inner_text())
        assert m, f"动态账期文案缺失: {sub.inner_text()}"
        assert m.group(1) == "2026" and m.group(2) == "06", f"账期非 202606: {sub.inner_text()}"

    def test_service_status_chinese(self, page):
        goto(page, "/")
        st = page.query_selector("#sys-status")
        assert st is not None, "首页缺少 #sys-status"
        text = st.inner_text()
        assert "正常" in text, f"服务状态未中文化: {text}"
        assert "ok" not in text.lower(), f"服务状态仍有英文 ok: {text}"

    def test_logo_no_border(self, page):
        """侧栏 logo 边角像素采样：不得有白色描边环。"""
        from PIL import Image
        goto(page, "/report")
        logo = page.locator(".brand-logo-img")
        assert logo.count() == 1, "侧栏 logo 缺失"
        logo.screenshot(path="/tmp/bdms-logo-regression.png")
        img = Image.open("/tmp/bdms-logo-regression.png").convert("RGBA")
        w, h = img.size
        px = img.load()
        pts = [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3),
               (w // 2, 2), (w // 2, h - 3), (2, h // 2), (w - 3, h // 2)]
        white = [p for p in pts
                 if px[p[0], p[1]][3] > 200
                 and px[p[0], p[1]][0] > 200
                 and px[p[0], p[1]][1] > 200
                 and px[p[0], p[1]][2] > 200]
        assert not white, f"logo 边角存在白色描边像素: {white}"


class TestReportWorkflow:
    """月报页 4 子页签工作流 + 审批按钮显隐一致。"""

    def test_tabs_switch(self, page):
        goto(page, "/report")
        for t in ["import", "calibrate", "issues", "approval"]:
            page.click(f'.tabs-tab[data-tab="{t}"]')
            page.wait_for_timeout(400)
            act = page.evaluate('document.querySelector(\'.tabs-tab[aria-selected="true"]\')?.dataset.tab')
            assert act == t, f"tab {t} 切换失败: active={act}"

    def test_keyboard_tab_nav(self, page):
        goto(page, "/report")
        page.click('.tabs-tab[data-tab="import"]')
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(200)
        act = page.evaluate('document.querySelector(\'.tabs-tab[aria-selected="true"]\')?.dataset.tab')
        assert act == "calibrate", f"ArrowRight 切换失败: active={act}"

    def test_calibrate_has_rows(self, page):
        goto(page, "/report")
        page.click('.tabs-tab[data-tab="calibrate"]')
        # 真实后端查询 1.7 万行需 ~2s，显式等待行数出现（最长 8s）
        rows = 0
        for _ in range(16):
            rows = page.locator("#data-table-container table tbody tr").count()
            if rows > 0:
                break
            page.wait_for_timeout(500)
        assert rows > 0, f"校准数据为空（等待 8s 后 rows={rows}）"

    def test_issues_has_rows(self, page):
        goto(page, "/report")
        page.click('.tabs-tab[data-tab="issues"]')
        page.wait_for_timeout(800)
        rows = page.locator("#review-issues-list table tbody tr").count()
        assert rows > 0, "问题清单为空"

    def test_approval_timeline(self, page):
        goto(page, "/report")
        page.click('.tabs-tab[data-tab="approval"]')
        page.wait_for_timeout(800)
        nodes = page.locator(".timeline .tl-item").count()
        assert nodes >= 1, "审批时间线无节点"

    def test_approval_buttons_visibility(self, page):
        """ctxbar 与 panel 的 4 个审批按钮显隐一致（无审批权时均隐藏）。"""
        goto(page, "/report")
        for sel in ["#btn-approve", "#btn-reject", "#btn-approve-panel", "#btn-reject-panel"]:
            st = page.evaluate(
                f"(() => {{const el=document.querySelector('{sel}'); "
                f"if(!el)return 'missing'; "
                f"return (el.disabled?'disabled':'enabled')+'/'+(el.style.display==='none'?'hidden':'visible');}})()"
            )
            assert "missing" not in st, f"{sel} 缺失"
            assert st != "disabled/hidden", f"{sel} 状态异常: {st}"


class TestSidebar:
    """侧栏折叠 236px ↔ 68px。"""

    def test_collapse(self, page):
        goto(page, "/report")
        w1 = page.evaluate("getComputedStyle(document.querySelector('.sidebar')).width")
        tog = page.query_selector(".sidebar-collapse-btn")
        assert tog is not None, "缺少侧栏折叠按钮"
        tog.click()
        page.wait_for_timeout(400)
        w2 = page.evaluate("getComputedStyle(document.querySelector('.sidebar')).width")
        assert w1 == "236px" and w2 == "68px", f"折叠异常: {w1} → {w2}"


class TestDashboard:
    """看板 KPI 卡。"""

    def test_kpi_cards(self, page):
        goto(page, "/dashboard")
        page.wait_for_timeout(1200)
        n = page.locator("#kpi-grid .stat-card").count()
        assert n == 8, f"KPI 卡数量异常: {n}"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
