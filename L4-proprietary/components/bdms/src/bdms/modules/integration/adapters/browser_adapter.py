"""Unified browser automation adapter - Playwright CDP + IAM Cookie pool.

Aligns with DESIGN-OUTLINE-BROWSER-AUTOMATION-TECH-SELECTION-v1.0.md section 4.1.
Unifies OA/ONES/timesheet browser automation, reusing oa_collector.py best practices.

Key design:
  - CDP reuse of logged-in Chrome (preserve SSO session)
  - Long-running background process (bypass exec 5-min timeout)
  - NO_PROXY=* bypass local proxy interference
  - IAM Cookie pool: login_iam() once, share across all systems

NOTE: All Playwright page.evaluate() calls use ES5 syntax only (no arrow functions, const, let, template literals).
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
    """Export failure exception."""
    pass


# --- Constants ---

IAM_BASE = "https://iam.bangcle.com"
ONES_BASE = "https://ones.bangcle.com"
OA_BASE = "https://oa.bangcle.com"
TIMESHEET_BASE = "https://timesheet.bangcle.com"

COOKIE_FILE = Path.home() / ".openclaw" / "data" / "iam_cookies.json"
COOKIE_TTL = 12 * 3600  # 12 hours

DOMAINS = ["iam.bangcle.com", "ones.bangcle.com", "oa.bangcle.com", "timesheet.bangcle.com"]


# --- Cookie pool management ---


def _load_cookies() -> dict:
    """Load cookie pool"""
    if COOKIE_FILE.exists():
        return json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cookies(cookies: dict):
    """Save cookie pool"""
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")


def is_cookie_valid(domain: str) -> bool:
    """Check if cookie is valid"""
    cookies = _load_cookies()
    if domain not in cookies:
        return False
    ts = cookies[domain].get("timestamp", 0)
    return (time.time() - ts) < COOKIE_TTL


def get_cookie(domain: str) -> Optional[str]:
    """Get cookie string for specified domain"""
    cookies = _load_cookies()
    if domain in cookies:
        return cookies[domain].get("cookie", "")
    return None


def set_cookie(domain: str, cookie: str):
    """Set cookie for specified domain"""
    cookies = _load_cookies()
    cookies[domain] = {"cookie": cookie, "timestamp": time.time()}
    _save_cookies(cookies)


def login_iam(username: str, password: str) -> bool:
    """Login to IAM and get cookies - one login, shared across all systems.

    Args:
        username: IAM username (e.g. limin.ren)
        password: IAM password

    Returns:
        True if login successful
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed: pip install playwright && playwright install chromium")
        return False

    env = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, env=env)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(IAM_BASE + "/#/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)

            page.locator("input[type=text]").first.fill(username)
            page.locator("input[type=password]").first.fill(password)
            page.locator("button").nth(1).click()

            page.wait_for_url("**/home/**", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)

            all_cookies = context.cookies()
            logger.info("  Got %d cookies", len(all_cookies))

            domain_cookies = {}
            for c in all_cookies:
                d = c.get("domain", "").lstrip(".")
                if d not in domain_cookies:
                    domain_cookies[d] = []
                domain_cookies[d].append(c["name"] + "=" + c["value"])

            for d, pairs in domain_cookies.items():
                cookie_str = "; ".join(pairs)
                set_cookie(d, cookie_str)
                logger.info("  %s: %d cookies, length %d", d, len(pairs), len(cookie_str))

            full_cookie_str = "; ".join(c["name"] + "=" + c["value"] for c in all_cookies)
            for domain in DOMAINS:
                set_cookie(domain, full_cookie_str)

            logger.info("  Full cookie length: %d", len(full_cookie_str))
            logger.info("IAM login successful, cookies saved")
            return True

        except Exception as e:
            logger.error("IAM login failed: %s", e)
            return False
        finally:
            browser.close()


def ensure_logged_in() -> bool:
    """Ensure logged in (cookies valid)"""
    for domain in DOMAINS:
        if not is_cookie_valid(domain):
            logger.warning("%s Cookie expired, re-login required", domain)
            return False
    return True


def inject_cookies_to_context(context):
    """Inject saved cookies into Playwright context"""
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


# --- Unified browser adapter ---


class BrowserAdapter:
    """Unified browser automation adapter - Playwright CDP + Cookie pool.

    Usage:
      adapter = BrowserAdapter()
      adapter.login("limin.ren", "***")  # one-time login
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
        """Close browser"""
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

    # --- Lifecycle ---

    def launch(self, cdp_url: Optional[str] = None):
        """Launch browser.

        Args:
            cdp_url: CDP endpoint URL (e.g. http://localhost:9222).
                     If None, launch new browser.
        """
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        env = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}

        if cdp_url:
            self._browser = self._playwright.chromium.connect_over_cdp(cdp_url)
            self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        else:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=["--start-maximized"] if not self.headless else [],
                env=env,
            )
            self._context = self._browser.new_context(
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
            )

        inject_cookies_to_context(self._context)
        self._page = self._context.new_page()

    def login(self, username: str, password: str) -> bool:
        """Login to IAM and inject cookies"""
        return login_iam(username, password)

    # --- Page operations ---

    def navigate(self, url: str, wait_network_idle: bool = True, timeout: int = 30000):
        """Navigate to URL"""
        if not self._page:
            raise RuntimeError("Browser not launched, call launch() first")
        self._page.goto(url, timeout=timeout)
        if wait_network_idle:
            self._page.wait_for_load_state("networkidle", timeout=min(timeout, 15000))

    def evaluate(self, js: str, *args) -> Any:
        """Execute JavaScript in page"""
        return self._page.evaluate(js, *args)

    def click(self, selector: str, timeout: int = 10000):
        """Click element"""
        self._page.locator(selector).first.click(timeout=timeout)

    def fill(self, selector: str, value: str, timeout: int = 10000):
        """Fill input"""
        self._page.locator(selector).first.fill(value, timeout=timeout)

    def wait_for_url(self, url_pattern: str, timeout: int = 15000):
        """Wait for URL match"""
        self._page.wait_for_url(url_pattern, timeout=timeout)

    def wait_for_text(self, text: str, timeout: int = 10000) -> bool:
        """Wait for page to contain text"""
        try:
            self._page.locator("text=" + text).first.wait_for(timeout=timeout)
            return True
        except Exception:
            return False

    # --- iframe operations ---

    def find_frame(self, url_pattern: str, timeout: int = 30000):
        """Find iframe matching URL pattern.

        Waits for iframe to load from about:blank to actual URL.
        Checks both frame URLs and iframe src attributes.
        """
        start = time.time()
        while time.time() - start < timeout:
            # Check frame URLs (skip about:blank)
            for frame in self._page.frames:
                if url_pattern in frame.url and frame.url != "about:blank":
                    frame.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(3)
                    return frame

            # Check iframe src attributes (frame may not be in page.frames yet)
            iframes = self._page.locator("iframe")
            for i in range(iframes.count()):
                src = iframes.nth(i).get_attribute("src") or ""
                if url_pattern in src:
                    time.sleep(5)
                    for frame in self._page.frames:
                        if url_pattern in frame.url and frame.url != "about:blank":
                            frame.wait_for_load_state("networkidle", timeout=15000)
                            time.sleep(3)
                            return frame

            time.sleep(2)
        return None

    def frame_evaluate(self, frame, js: str, *args) -> Any:
        """Execute JavaScript in iframe"""
        return frame.evaluate(js, *args)

    def frame_click(self, frame, selector: str, timeout: int = 10000):
        """Click element in iframe"""
        frame.locator(selector).first.click(timeout=timeout)

    # --- Download operations ---

    def expect_download(self, timeout: int = 600) -> Optional[Path]:
        """Wait for download to complete, return file path"""
        start = time.time()
        downloads_dir = Path.home() / "Downloads"
        initial_files = set(downloads_dir.glob("*"))

        while time.time() - start < timeout:
            time.sleep(3)
            current_files = set(downloads_dir.glob("*"))
            new_files = current_files - initial_files
            for f in new_files:
                size1 = f.stat().st_size
                time.sleep(1)
                size2 = f.stat().st_size
                if size1 == size2 and size1 > 100:
                    return f
        return None

    def click_and_download(self, frame_or_page, selector: str, timeout: int = 600) -> Optional[Path]:
        """Click export button and wait for download"""
        frame_or_page.locator(selector).first.click()
        time.sleep(3)
        return self.expect_download(timeout=timeout)

    # --- OA specific operations ---

    def oa_dismiss_dialogs(self):
        """Close OA homepage dialogs/overlays"""
        self._page.evaluate("""function() {
            ['.ant-modal-wrap', '.wea-dialog', '[role=dialog]', '.ant-modal', '.ant-modal-mask'].forEach(function(sel) {
                document.querySelectorAll(sel).forEach(function(el) { el.remove(); });
            });
            document.querySelectorAll('*').forEach(function(el) {
                var style = window.getComputedStyle(el);
                if (style.position === 'fixed' && parseInt(style.zIndex) > 100) {
                    el.remove();
                }
            });
        }""")
        time.sleep(1)

    def oa_click_menu(self, text: str) -> bool:
        """Click OA left menu item"""
        self.oa_dismiss_dialogs()
        result = self._page.evaluate("""function(t) {
            var spans = document.querySelectorAll('span');
            for (var i = 0; i < spans.length; i++) {
                var span = spans[i];
                if (span.textContent.trim().indexOf(t) !== -1) {
                    var rect = span.getBoundingClientRect();
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
        """Click app card on IAM homepage, open new tab"""
        try:
            self._page.get_by_text("应用入口", exact=False).first.click()
            time.sleep(2)
        except Exception:
            pass

        card = self._page.evaluate("""function(text) {
            var candidates = [];
            var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            var node;
            while (node = walker.nextNode()) {
                var t = (node.textContent || '').trim();
                if (t.indexOf(text) !== -1 && t.indexOf('CRM') === -1 && t.indexOf('EHR') === -1) {
                    var rect = node.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 20 && rect.width < 600 && rect.height < 300) {
                        candidates.push({
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height),
                            area: rect.width * rect.height
                        });
                    }
                }
            }
            candidates.sort(function(a, b) { return a.area - b.area; });
            return candidates.length > 1 ? candidates[1] : (candidates[0] || null);
        }""", card_text)

        if not card:
            return None

        pages_before = len(context.pages)
        self._page.mouse.click(card['x'] + card['w'] - 15, card['y'] + card['h'] / 2)
        time.sleep(5)

        if len(context.pages) > pages_before:
            new_page = context.pages[-1]
            new_page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            return new_page

        pages_before = len(context.pages)
        self._page.mouse.click(card['x'] + card['w'] / 2, card['y'] + card['h'] / 2)
        time.sleep(5)

        if len(context.pages) > pages_before:
            new_page = context.pages[-1]
            new_page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            return new_page

        return None

    # --- ONES specific operations ---

    def ones_ensure_tab(self) -> bool:
        """Ensure ONES tab is open"""
        for page in self._context.pages:
            if "ones.bangcle.com" in page.url:
                self._page = page
                return True

        self._page = self._context.new_page()
        self.navigate(ONES_BASE + "/project/#/workspace/home")
        return True

    def ones_click_filter_tab(self, tab_index: int) -> bool:
        """Click ONES filter sub-tab"""
        js = "(function() {"
        js += "  var tabs = document.querySelectorAll('.url-foldable-tabs-new-link');"
        js += "  if (tabs.length > " + str(tab_index) + ") {"
        js += "    tabs[" + str(tab_index) + "].click();"
        js += "    return 'clicked index " + str(tab_index) + "';"
        js += "  }"
        js += "  return 'not found, count=' + tabs.length;"
        js += "})()"
        result = self.evaluate(js)
        time.sleep(5)
        return "clicked" in str(result).lower()

    def ones_click_more_menu(self) -> bool:
        """Click ONES more menu"""
        js = """(function() {
            var icon = document.querySelector('.more-menu-icon');
            if (icon) { icon.click(); return 'clicked'; }
            return 'not found';
        })()"""
        result = self.evaluate(js)
        time.sleep(1)
        return "clicked" in str(result).lower()

    def ones_click_export_item(self) -> bool:
        """Click ONES export work items"""
        js = """(function() {
            var items = document.querySelectorAll('.ones-dropdown-menu-item-content');
            for (var i = 0; i < items.length; i++) {
                var text = items[i].innerText || '';
                if (text.indexOf('导出') >= 0 && text.indexOf('工作项') >= 0) {
                    items[i].click();
                    return 'clicked: ' + text;
                }
            }
            return 'not found';
        })()"""
        result = self.evaluate(js)
        time.sleep(3)
        return "clicked" in str(result).lower()

    def ones_click_confirm(self) -> bool:
        """Click confirm button"""
        js = """(function() {
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].innerText || '').trim();
                if (text === '确定' || text === '确认') {
                    buttons[i].click();
                    return 'clicked: ' + text;
                }
            }
            return 'not found';
        })()"""
        result = self.evaluate(js)
        time.sleep(1)
        return "clicked" in str(result).lower()


# --- Convenience functions ---


def create_browser_adapter(headless: bool = False) -> BrowserAdapter:
    """Create and launch browser adapter"""
    adapter = BrowserAdapter(headless=headless)
    adapter.launch()
    return adapter


@contextmanager
def browser_session(headless: bool = False):
    """Browser session context manager"""
    adapter = BrowserAdapter(headless=headless)
    try:
        adapter.launch()
        yield adapter
    finally:
        adapter.close()
