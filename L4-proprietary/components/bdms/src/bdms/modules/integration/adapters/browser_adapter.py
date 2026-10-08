"""统一浏览器自动化适配器 — Playwright CDP + IAM Cookie 池。

对齐 DESIGN-OUTLINE-BROWSER-AUTOMATION-TECH-SELECTION-v1.0.md §4.1。
统一 OA/ONES/工时门户的浏览器自动化，复用已验证的 oa_collector.py 最佳实践。

关键设计：
  - CDP 复用已登录 Chrome（保留 SSO 登录态）
  - 长存活 background 进程（绕过 exec 5 分钟超时）
  - NO_PROXY=* 绕过本地代理干扰
  - IAM Cookie 池：login_iam() 一次登录，多系统共享
"""

import json
import logging
import os
import time
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from bdms.core.paths import DATA_DIR

logger = logging.getLogger(__name__)

class ExportError(Exception):
    """导出失败异常。"""
    pass


# ─── 常量 ───

IAM_BASE = "https://iam.bangcle.com"
ONES_BASE = "https://ones.bangcle.com"
OA_BASE = "https://oa.bangcle.com"
TIMESHEET_BASE = "https://timesheet.bangcle.com"

COOKIE_FILE = Path.home() / ".openclaw" / "data" / "iam_cookies.json"
COOKIE_TTL = 12 * 3600  # 12 小时

DOMAINS = ["iam.bangcle.com", "ones.bangcle.com", "oa.bangcle.com", "timesheet.bangcle.com"]


# ─── Cookie 池管理 ───


def _load_cookies() -> dict:
    """加载 Cookie 池"""
    if COOKIE_FILE.exists():
        return json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cookies(cookies: dict):
    """保存 Cookie 池"""
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")


def is_cookie_valid(domain: str) -> bool:
    """检查 Cookie 是否有效"""
    cookies = _load_cookies()
    if domain not in cookies:
        return False
    ts = cookies[domain].get("timestamp", 0)
    return (time.time() - ts) < COOKIE_TTL


def get_cookie(domain: str) -> Optional[str]:
    """获取指定域名的 Cookie 字符串"""
    cookies = _load_cookies()
    if domain in cookies:
        return cookies[domain].get("cookie", "")
    return None


def set_cookie(domain: str, cookie: str):
    """设置指定域名的 Cookie"""
    cookies = _load_cookies()
    cookies[domain] = {"cookie": cookie, "timestamp": time.time()}
    _save_cookies(cookies)


def login_iam(username: str, password: str) -> bool:
    """登录 IAM 获取 Cookie — 一次登录，多系统共享。

    Args:
        username: IAM 用户名（如 limin.ren）
        password: IAM 密码

    Returns:
        登录成功返回 True
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright 未安装：pip install playwright && playwright install chromium")
        return False

    # 绕过代理干扰
    env = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, env=env)
        context = browser.new_context()
        page = context.new_page()

        try:
            # 导航到登录页（不是首页！）
            page.goto(f"{IAM_BASE}/#/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)

            # 填写登录表单
            page.locator("input[type=text]").first.fill(username)
            page.locator("input[type=password]").first.fill(password)
            # 点击登录按钮（button[1] = 登录）
            page.locator("button").nth(1).click()

            # 等待跳转到首页（确认登录成功）
            page.wait_for_url("**/home/**", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)

            # 获取所有 Cookie（包括所有域名）
            all_cookies = context.cookies()
            logger.info(f"  获取到 {len(all_cookies)} 个 Cookie")

            # 按域名分组保存
            domain_cookies = {}
            for c in all_cookies:
                d = c.get("domain", "").lstrip(".")
                if d not in domain_cookies:
                    domain_cookies[d] = []
                domain_cookies[d].append(f"{c['name']}={c['value']}")

            # 保存每个域名的 Cookie
            for d, pairs in domain_cookies.items():
                cookie_str = "; ".join(pairs)
                set_cookie(d, cookie_str)
                logger.info(f"  {d}: {len(pairs)} 个 Cookie, 长度 {len(cookie_str)}")

            # 同时保存全量 Cookie 到所有目标域名
            full_cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
            for domain in DOMAINS:
                set_cookie(domain, full_cookie_str)

            logger.info(f"  全量 Cookie 长度: {len(full_cookie_str)}")
            logger.info("IAM 登录成功，Cookie 已保存")
            return True

        except Exception as e:
            logger.error(f"IAM 登录失败: {e}")
            return False
        finally:
            browser.close()


def ensure_logged_in() -> bool:
    """确保已登录（Cookie 有效）"""
    for domain in DOMAINS:
        if not is_cookie_valid(domain):
            logger.warning(f"{domain} Cookie 已过期，需要重新登录")
            return False
    return True


def inject_cookies_to_context(context):
    """将保存的 Cookie 注入到 Playwright context"""
    cookies = _load_cookies()
    if not cookies:
        return False

    cookie_str = None
    for domain in DOMAINS:
        if domain in cookies and cookies[domain].get("cookie"):
            cookie_str = cookies[domain]["cookie"]
            break

    if not cookie_str:
        return False

    for item in cookie_str.split("; "):
        if "=" in item:
            k, v = item.split("=", 1)
            for domain in DOMAINS:
                try:
                    context.add_cookies([{"name": k, "value": v, "domain": domain, "path": "/"}])
                    context.add_cookies([{"name": k, "value": v, "domain": ".bangcle.com", "path": "/"}])
                except Exception:
                    pass

    return True


# ─── 统一浏览器适配器 ───


class BrowserAdapter:
    """统一浏览器自动化适配器 — Playwright CDP + Cookie 池。

    使用方式：
      adapter = BrowserAdapter()
      adapter.login("limin.ren", "June-123")  # 一次登录
      adapter.navigate("https://oa.bangcle.com/...")
      data = adapter.evaluate("document.querySelector(...).textContent")
      adapter.click_export_and_download()
    """

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        """关闭浏览器"""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

    # ─── 生命周期 ───

    def launch(self, cdp_url: Optional[str] = None):
        """启动浏览器。

        Args:
            cdp_url: CDP 端点 URL（如 http://localhost:9222）。
                     为 None 则自启动新浏览器。
        """
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        env = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}

        if cdp_url:
            # CDP 复用已登录 Chrome
            self._browser = self._playwright.chromium.connect_over_cdp(cdp_url)
            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        else:
            # 自启动新浏览器
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--start-maximized"] if not self.headless else [],
                env=env,
            )
            self._context = self._browser.new_context(
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
            )

        # 注入 Cookie
        inject_cookies_to_context(self._context)

        self._page = self._context.new_page()

    def login(self, username: str, password: str) -> bool:
        """登录 IAM 并注入 Cookie"""
        return login_iam(username, password)

    # ─── 页面操作 ───

    def navigate(self, url: str, wait_network_idle: bool = True, timeout: int = 30000):
        """导航到 URL"""
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 launch()")
        self._page.goto(url, timeout=timeout)
        if wait_network_idle:
            self._page.wait_for_load_state("networkidle", timeout=min(timeout, 15000))

    def evaluate(self, js: str, *args) -> Any:
        """在页面中执行 JavaScript"""
        return self._page.evaluate(js, *args)

    def click(self, selector: str, timeout: int = 10000):
        """点击元素"""
        self._page.locator(selector).first.click(timeout=timeout)

    def fill(self, selector: str, value: str, timeout: int = 10000):
        """填写输入框"""
        self._page.locator(selector).first.fill(value, timeout=timeout)

    def wait_for_url(self, url_pattern: str, timeout: int = 15000):
        """等待 URL 匹配"""
        self._page.wait_for_url(url_pattern, timeout=timeout)

    def wait_for_text(self, text: str, timeout: int = 10000) -> bool:
        """等待页面包含指定文本"""
        try:
            self._page.locator(f"text={text}").first.wait_for(timeout=timeout)
            return True
        except Exception:
            return False

    # ─── iframe 操作 ───

    def find_frame(self, url_pattern: str, timeout: int = 30000):
        """查找匹配 URL 的 iframe"""
        start = time.time()
        while time.time() - start < timeout:
            for frame in self._page.frames:
                if url_pattern in frame.url:
                    frame.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(2)
                    return frame
            time.sleep(2)
        return None

    def frame_evaluate(self, frame, js: str, *args) -> Any:
        """在 iframe 中执行 JavaScript"""
        return frame.evaluate(js, *args)

    def frame_click(self, frame, selector: str, timeout: int = 10000):
        """在 iframe 中点击元素"""
        frame.locator(selector).first.click(timeout=timeout)

    # ─── 下载操作 ───

    def expect_download(self, timeout: int = 600) -> Optional[Path]:
        """等待下载完成，返回文件路径"""
        start = time.time()
        downloads_dir = Path.home() / "Downloads"
        initial_files = set(downloads_dir.glob("*"))

        while time.time() - start < timeout:
            time.sleep(3)
            current_files = set(downloads_dir.glob("*"))
            new_files = current_files - initial_files
            for f in new_files:
                # 等待文件写入完成
                size1 = f.stat().st_size
                time.sleep(1)
                size2 = f.stat().st_size
                if size1 == size2 and size1 > 100:
                    return f
        return None

    def click_and_download(self, frame_or_page, selector: str, timeout: int = 600) -> Optional[Path]:
        """点击导出按钮并等待下载"""
        frame_or_page.locator(selector).first.click()
        time.sleep(3)
        return self.expect_download(timeout=timeout)

    # ─── OA 专用操作 ───

    def oa_dismiss_dialogs(self):
        """关闭 OA 首页弹窗/遮罩"""
        self._page.evaluate("""() => {
            ['.ant-modal-wrap', '.wea-dialog', '[role=dialog]', '.ant-modal', '.ant-modal-mask'].forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
            document.querySelectorAll('*').forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.position === 'fixed' && parseInt(style.zIndex) > 100) {
                    el.remove();
                }
            });
        }""")
        time.sleep(1)

    def oa_click_menu(self, text: str) -> bool:
        """点击 OA 左侧菜单项"""
        self.oa_dismiss_dialogs()
        result = self._page.evaluate("""(t) => {
            const spans = document.querySelectorAll('span');
            for (const span of spans) {
                if (span.textContent.trim().includes(t)) {
                    const rect = span.getBoundingClientRect();
                    if (rect.x < 350 && rect.width > 50) {
                        span.click();
                        return {clicked: true, text: span.textContent.trim()};
                    }
                }
            }
            return {clicked: false};
        }""", text)
        time.sleep(2)
        return result.get('clicked', False)

    def oa_click_card_iam(self, card_text: str, context) -> Optional[Any]:
        """点击 IAM 首页的应用卡片，打开新标签页"""
        # 确保在「应用入口」tab
        try:
            self._page.get_by_text("应用入口", exact=False).first.click()
            time.sleep(2)
        except Exception:
            pass

        # 找卡片
        card = self._page.evaluate("""(text) => {
            const candidates = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            let node;
            while (node = walker.nextNode()) {
                const t = (node.textContent || '').trim();
                if (t.includes(text) && !t.includes('CRM') && !t.includes('EHR')) {
                    const rect = node.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 20 && rect.width < 600 && rect.height < 300) {
                        candidates.push({
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height),
                            area: rect.width * rect.height
                        });
                    }
                }
            }
            candidates.sort((a, b) -> a.area - b.area);
            return candidates.length > 1 ? candidates[1] : (candidates[0] || null);
        }""", card_text)

        if not card:
            return None

        pages_before = len(context.pages)
        # 点击卡片右下角
        self._page.mouse.click(card['x'] + card['w'] - 15, card['y'] + card['h'] / 2)
        time.sleep(5)

        if len(context.pages) > pages_before:
            new_page = context.pages[-1]
            new_page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            return new_page

        # 备选：点击中心
        pages_before = len(context.pages)
        self._page.mouse.click(card['x'] + card['w'] / 2, card['y'] + card['h'] / 2)
        time.sleep(5)

        if len(context.pages) > pages_before:
            new_page = context.pages[-1]
            new_page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            return new_page

        return None

    # ─── ONES 专用操作 ───

    def ones_ensure_tab(self) -> bool:
        """确保 Chrome 已打开 ONES 标签页"""
        # 在已启动的浏览器中检查
        for page in self._context.pages:
            if "ones.bangcle.com" in page.url:
                self._page = page
                return True

        # 打开新标签页
        self._page = self._context.new_page()
        self.navigate(f"{ONES_BASE}/project/#/workspace/home")
        return True

    def ones_click_filter_tab(self, tab_index: int) -> bool:
        """点击 ONES 筛选器子 tab"""
        js = f"""
        (function() {{
            var tabs = document.querySelectorAll('.url-foldable-tabs-new-link');
            if (tabs.length > {tab_index}) {{
                tabs[{tab_index}].click();
                return 'clicked index {tab_index}';
            }}
            return 'not found, count=' + tabs.length;
        }})()
        """
        result = self.evaluate(js)
        time.sleep(5)
        return "clicked" in str(result).lower()

    def ones_click_more_menu(self) -> bool:
        """点击 ONES 更多菜单"""
        js = """
        (function() {
            var icon = document.querySelector('.more-menu-icon');
            if (icon) {
                icon.click();
                return 'clicked';
            }
            return 'not found';
        })()
        """
        result = self.evaluate(js)
        time.sleep(1)
        return "clicked" in str(result).lower()

    def ones_click_export_item(self) -> bool:
        """点击 ONES 导出工作项"""
        js = """
        (function() {
            var items = document.querySelectorAll('.ones-dropdown-menu-item-content');
            for (var i = 0; i < items.length; i++) {
                var text = items[i].innerText || '';
                if (text.indexOf('导出') >= 0 && text.indexOf('工作项') >= 0) {
                    items[i].click();
                    return 'clicked: ' + text;
                }
            }
            return 'not found';
        })()
        """
        result = self.evaluate(js)
        time.sleep(3)
        return "clicked" in str(result).lower()

    def ones_click_confirm(self) -> bool:
        """点击确认按钮"""
        js = """
        (function() {
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].innerText || '').trim();
                if (text === '确定' || text === '确认') {
                    buttons[i].click();
                    return 'clicked: ' + text;
                }
            }
            return 'not found';
        })()
        """
        result = self.evaluate(js)
        time.sleep(1)
        return "clicked" in str(result).lower()


# ─── 便捷函数 ───


def create_browser_adapter(headless: bool = False) -> BrowserAdapter:
    """创建并启动浏览器适配器"""
    adapter = BrowserAdapter(headless=headless)
    adapter.launch()
    return adapter


@contextmanager
def browser_session(headless: bool = False):
    """浏览器会话上下文管理器"""
    adapter = BrowserAdapter(headless=headless)
    try:
        adapter.launch()
        yield adapter
    finally:
        adapter.close()
