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
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from bdms.core import config
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


def _fetch_iam_captcha() -> Optional[str]:
    """通过 IMAP 直读网易企业邮箱获取 IAM 登录验证码。

    配置来源（config.json → integrations.iam.email）：
      imap: host/port/sender/subject_keyword/code_length/poll_timeout
      credentials: username_file/password_file（~/.openclaw/secrets/ 下 600 权限文件）

    Returns:
        6 位验证码；失败返回 None
    """
    try:
        from bdms.core import config
        email_config = config.get("integrations.iam.email", {}) or {}
        imap_cfg = email_config.get("imap", {}) or {}
        cred_cfg = email_config.get("credentials", {}) or {}

        username = ""
        password = ""
        try:
            uf = Path(cred_cfg.get("username_file", "")).expanduser()
            pf = Path(cred_cfg.get("password_file", "")).expanduser()
            if uf.exists():
                username = uf.read_text(encoding="utf-8").strip()
            if pf.exists():
                password = pf.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error("读取 IMAP 凭据文件失败: %s", e)
            return None

        if not username or not password:
            logger.error("IMAP 凭据未配置（%s / %s）",
                         cred_cfg.get("username_file", ""),
                         cred_cfg.get("password_file", ""))
            return None

        from .email_captcha import fetch_latest_captcha
        return fetch_latest_captcha(
            imap_host=imap_cfg.get("host", "hwhzimap.qiye.163.com"),
            imap_port=int(imap_cfg.get("port", 993)),
            username=username,
            password=password,
            sender=imap_cfg.get("sender", "imb@bangcle.com"),
            subject_keyword=imap_cfg.get("subject_keyword", "登录验证码"),
            code_length=int(imap_cfg.get("code_length", 6)),
            poll_timeout=int(imap_cfg.get("poll_timeout", 90)),
        )
    except Exception as e:
        logger.error("获取 IAM 邮件验证码异常: %s", e)
        return None


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
            page.goto(IAM_BASE + "/#/login", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(5)

            page.locator("input[type=text]").first.fill(username)
            page.locator("input[type=password]").first.fill(password)
            page.locator("button").nth(1).click()
            time.sleep(3)

            # 检查是否需要邮件验证码
            captcha_locator = page.locator("input[placeholder*=验证码],input[placeholder*=captcha]")
            if captcha_locator.count() > 0:
                logger.info("IAM 登录需要邮件验证码，正在获取...")
                try:
                    captcha = _fetch_iam_captcha()
                    if not captcha:
                        logger.error("无法获取 IAM 邮件验证码")
                        return False
                    logger.info("成功获取验证码：%s", captcha)
                    # 填入验证码
                    captcha_locator.first.fill(captcha)
                    page.locator("button").nth(1).click()
                    time.sleep(3)
                except Exception as e:
                    logger.error("获取邮件验证码失败：%s", e)
                    return False

            page.wait_for_url("**/home/**", timeout=20000)
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


def _iam_credentials() -> tuple:
    """从 secrets 目录读取 IAM 登录凭据。"""
    base = Path.home() / ".openclaw" / "secrets"
    u = base / "iam.username"
    p = base / "iam.password"
    username = u.read_text(encoding="utf-8").strip() if u.exists() else ""
    password = p.read_text(encoding="utf-8").strip() if p.exists() else ""
    return username, password


def _ones_credentials() -> tuple:
    """从 secrets 目录读取 ONES 登录凭据（两行：邮箱 + 密码）。"""
    base = Path.home() / ".openclaw" / "secrets"
    u = base / "ones.basic"
    if u.exists():
        lines = u.read_text(encoding="utf-8").strip().split("\n")
        if len(lines) >= 2:
            return lines[0].strip(), lines[1].strip()
    return "", ""


def ensure_logged_in() -> bool:
    """Ensure logged in (cookies valid)"""
    for domain in DOMAINS:
        if not is_cookie_valid(domain):
            logger.warning("%s Cookie expired, re-login required", domain)
            return False
    return True


def inject_cookies_to_context(context):
    """Inject saved cookies into Playwright context.

    除 cookie 外，还处理 ONES 的 localStorage['ct']：
    ONES 前端路由守卫依赖 localStorage['ct']（SSO 登录时自动写入），
    仅注入 cookie 跨实例时会因 ct 缺失跳登录页。
    这里用 add_init_script 在页面加载前把 cookie 里的 ct 同步到 localStorage。
    """
    cookies = _load_cookies()
    if not cookies:
        return False

    cookie_str = None
    ct_value = None
    for domain in DOMAINS:
        if domain in cookies and cookies[domain].get("cookie"):
            cookie_str = cookies[domain]["cookie"]
            # 提取 ONES 会话关键 cookie ct
            if domain in ("ones.bangcle.com", ".ones.bangcle.com"):
                for item in cookie_str.split("; "):
                    if item.startswith("ct="):
                        ct_value = item[len("ct="):]
                        break
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

    # ONES 会话认证还依赖 localStorage['ct']（SSO 登录时自动写入）
    # 在页面加载前把 cookie 里的 ct 同步到 localStorage，避免前端跳登录页
    if ct_value:
        import json as _json
        safe_ct = _json.dumps(ct_value)
        try:
            context.add_init_script(
                """(function() {
                    try {
                        if (location.hostname.indexOf('ones.bangcle.com') !== -1) {
                            if (!localStorage.getItem('ct')) {
                                localStorage.setItem('ct', %s);
                            }
                        }
                    } catch (e) {}
                })();""" % safe_ct
            )
            logger.info("已注入 ONES localStorage ct (len=%d)", len(ct_value))
        except Exception as e:
            logger.warning("注入 localStorage ct 失败: %s", e)

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

        try:
            self._playwright = sync_playwright().start()
            env = {**os.environ, "NO_PROXY": "*", "no_proxy": "*"}

            if cdp_url:
                try:
                    self._browser = self._playwright.chromium.connect_over_cdp(cdp_url)
                    self._context = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
                except Exception as e:
                    logger.warning("CDP 连接失败，回退到启动新浏览器: %s", e)
                    cdp_url = None
                    # fall through to launch new browser
            if not cdp_url:
                self._browser = self._playwright.chromium.launch(
                    headless=self.headless,
                    args=["--start-maximized", "--remote-debugging-port=9222"] if not self.headless else [],
                    env=env,
                )
                self._context = self._browser.new_context(
                    accept_downloads=True,
                    viewport={"width": 1920, "height": 1080},
                )

            inject_cookies_to_context(self._context)
            self._page = self._context.new_page()
        except Exception:
            # 捕获同步 API 在异步循环使用异常：It looks like you are using Playwright Sync API inside the asyncio loop.
            # 不影响后续流程，直接抛出给上层处理，让外层降级
            raise

    def login(self, username: str, password: str) -> bool:
        """Login to IAM and inject cookies"""
        return login_iam(username, password)

    # --- SSO 自动登录 ---

    def _save_context_cookies(self) -> None:
        """保存当前浏览器上下文全部 cookie 到 Cookie 池。"""
        try:
            all_cookies = self._context.cookies()
            domain_cookies = {}
            for c in all_cookies:
                d = c.get("domain", "").lstrip(".")
                if d not in domain_cookies:
                    domain_cookies[d] = []
                domain_cookies[d].append(c["name"] + "=" + c["value"])
            for d, pairs in domain_cookies.items():
                cookie_str = "; ".join(pairs)
                set_cookie(d, cookie_str)
            logger.info("已保存 %d 个域的 cookie", len(domain_cookies))
        except Exception as e:
            logger.warning("保存 cookie 失败: %s", e)

    def _sso_login_if_needed(self) -> bool:
        """检测登录页并自动执行登录（支持 ONES 独立登录页与 IAM 登录页）。

        实测结论：新浏览器访问 ONES 会被重定向到 ONES 自己的登录页
        （ones.bangcle.com/project/#/auth/login），用 ONES 凭据（邮箱+密码）
        直接登录即可，无需验证码。跨实例注入 cookie 无效（ONES 服务端会
        覆盖 localStorage ct 并跳登录页），必须走完整登录流。

        ⚠️ ONES SPA 存在渲染竞态：初始会短暂渲染工作台外壳（无密码框），
        随后才渲染登录表单。因此必须先等 SPA 稳定（12s）再检测，
        避免误判"无需登录"。

        ONES 登录页结构（诊断确认）：
          input[type=text] 邮箱 (placeholder=请输入你的邮箱)
          input[type=password] 密码
          input[placeholder*=图形验证码]（默认 hidden，出现时需要人工/图形码）
          button[type=submit] 登录

        IAM 登录页结构（诊断确认）：
          input[type=text] 用户名 / input[type=password] 密码
          button[0]重置 / button[1]下一步 / button[2]刷新二维码
          登录触发邮件验证码时：input[placeholder*=验证码] + 下一步

        Returns:
            True 表示已登录（或无需登录）；False 登录失败
        """
        try:
            page = self._page

            # 等待 SPA 稳定渲染（消除竞态），最长 ~18s
            ones_login = False
            iam_login = False
            for _ in range(6):
                time.sleep(3)
                url = page.url
                pwd = page.locator("input[type=password]").count()
                if "ones.bangcle.com" in url and "auth/login" in url and pwd > 0:
                    ones_login = True
                    break
                if "iam.bangcle.com" in url and pwd > 0:
                    iam_login = True
                    break
                if "ones.bangcle.com" in url and "auth/login" not in url and pwd == 0:
                    # 已登录（ONES 业务页且无登录表单）；但需排除"加载中"外壳
                    has_business = page.evaluate(
                        "document.querySelectorAll('.url-foldable-tabs-new-link, [class*=user], [class*=avatar], [class*=project]').length > 0"
                    )
                    if has_business:
                        logger.info("已登录，检测到业务元素: %s", url[:70])
                        return True
                    # 否则可能是加载中，继续等待

            # 6 轮后仍无法确认，做最终判定
            url = page.url
            pwd = page.locator("input[type=password]").count()
            if not ones_login and not iam_login:
                if "ones.bangcle.com" in url and "auth/login" not in url and pwd == 0:
                    logger.info("未检测到登录表单，视为已登录: %s", url[:70])
                    return True
                logger.error("无法确认登录状态，URL: %s, pwd=%d", url[:70], pwd)
                return False

            if ones_login:
                logger.info("检测到 ONES 独立登录页，用 ONES 凭据自动登录...")
                email, password = _ones_credentials()
                if not email or not password:
                    logger.error("无 ONES 凭据（~/.openclaw/secrets/ones.basic），无法自动登录")
                    return False
                page.wait_for_selector("input[type=text]", timeout=20000)
                time.sleep(2)
                page.locator("input[type=text]").first.fill(email)
                page.locator("input[type=password]").first.fill(password)
                submit = page.locator("button[type=submit]")
                if submit.count() > 0:
                    submit.first.click()
                else:
                    page.locator("button").filter(has_text="登录").first.click()
                time.sleep(5)

                # 若出现图形验证码（无法自动处理），返回失败并提示人工
                graphic = page.locator("input[placeholder*=图形验证码]")
                if graphic.count() > 0 and graphic.first.is_visible():
                    logger.error("ONES 登录需要图形验证码，无法自动处理，需人工登录一次")
                    return False
            else:
                logger.info("检测到 IAM 登录页，执行自动 SSO 登录（含验证码）...")
                username, password = _iam_credentials()
                if not username or not password:
                    logger.error("无 IAM 凭据，无法自动登录")
                    return False

                # 等待登录表单就绪
                page.wait_for_selector("input[type=text]", timeout=20000)
                time.sleep(2)

                # 填充用户名密码
                page.locator("input[type=text]").first.fill(username)
                page.locator("input[type=password]").first.fill(password)

                # 点击"下一步"登录按钮（优先文本匹配，回退索引）
                next_btn = page.locator("button").filter(has_text="下一步")
                if next_btn.count() > 0:
                    next_btn.first.wait_for(state="visible", timeout=15000)
                    next_btn.first.click()
                else:
                    page.locator("button").nth(1).wait_for(state="visible", timeout=15000)
                    page.locator("button").nth(1).click()
                time.sleep(4)

                # 检测验证码并自动获取
                captcha = page.locator("input[placeholder*=验证码],input[placeholder*=captcha]")
                if captcha.count() > 0:
                    logger.info("IAM 登录需要邮件验证码，自动获取...")
                    code = _fetch_iam_captcha()
                    if not code:
                        logger.error("无法获取 IAM 验证码")
                        return False
                    logger.info("成功获取验证码：%s", code)
                    captcha.first.fill(code)
                    # 验证码输入后点击确认/登录按钮
                    confirm = page.locator("button").filter(has_text="确认")
                    if confirm.count() > 0:
                        confirm.first.click()
                    else:
                        next_btn = page.locator("button").filter(has_text="下一步")
                        if next_btn.count() > 0:
                            next_btn.first.click()
                        else:
                            page.locator("button").nth(1).click()
                    time.sleep(4)

            # 等待登录成功（URL 回到 ONES 业务页且无密码框，最多 40s）
            for _ in range(13):
                time.sleep(3)
                url = page.url
                pwd = page.locator("input[type=password]").count()
                if "ones.bangcle.com" in url and pwd == 0 and "auth/login" not in url:
                    logger.info("登录成功，已进入 ONES: %s", url[:70])
                    self._save_context_cookies()
                    return True
            logger.error("登录超时（未进入 ONES），最后 URL: %s", page.url[:70])
            return False
        except Exception as e:
            logger.error("自动登录异常: %s", e)
            return False

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
        """Ensure ONES filter list tab is open, auto SSO login if needed.

        修正：必须进入筛选器列表页，才能找到目标筛选器标签。
        团队 ID 硬编码（当前团队 ID: RZxvwUZ8），后续可配置化。
        """
        for page in self._context.pages:
            if "ones.bangcle.com/filter" in page.url:
                self._page = page
                # 检测是否需要登录（登录页会跳 IAM）
                return self._sso_login_if_needed()

        self._page = self._context.new_page()
        # 直接导航到筛选器列表页，避免后续导航覆盖
        filter_url = ONES_BASE + "/project/#/workspace/team/RZxvwUZ8/filter"
        self.navigate(filter_url, wait_network_idle=False, timeout=60000)
        # 等待 SPA 加载后检测登录状态，必要时自动 SSO 登录
        time.sleep(3)
        ok = self._sso_login_if_needed()
        if not ok:
            return False
        return True

    def ones_click_filter_tab(self, label: str = "", tab_index: int = -1) -> bool:
        """Click ONES filter sub-tab by label (preferred) or index (fallback).

        优先用文本匹配（label 包含匹配），匹配失败时用 tab_index 作为 fallback。文本匹配更可靠，
        因为 tab 顺序会随 ONES 版本或权限变化。在整个页面找所有 a 标签，支持不同页面结构（列表页和详情页）。
        """
        # 优先：文本匹配
        if label:
            js = "(function() {"
            # 在整个页面找所有 a 标签：既支持筛选器列表页，也支持单个筛选器详情页
            js += "  var tabs = document.querySelectorAll('a');"
            js += "  var target = '" + label.replace("'", "\\'") + "';"
            js += "  for (var i = 0; i < tabs.length; i++) {"
            js += "    var text = (tabs[i].innerText || '').trim();\n"
            js += "    if (!text) continue;"
            js += "    if (text.indexOf(target) >= 0) {"
            js += "      tabs[i].click();"
            js += "      return 'clicked: ' + text + ' (index=' + i + ')';"
            js += "    }"
            js += "  }"
            js += "  return 'label not found, count=' + tabs.length;"
            js += "})()"
            result = self.evaluate(js)
            if "clicked" in str(result).lower():
                time.sleep(5)
                return True
            logger.warning("按标签匹配失败: %s, 结果: %s", label, result)

        # fallback：按索引
        if tab_index >= 0:
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

        return False

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

    def ones_click_reset(self) -> bool:
        """Click ONES reset button to restore all data (before export)"""
        js = """(function() {
            var buttons = document.querySelectorAll('button, a');
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].innerText || '').trim().toLowerCase();
                if (text.indexOf('还原') >= 0 || text.indexOf('重置') >= 0) {
                    buttons[i].click();
                    return 'clicked: ' + text;
                }
            }
            return 'not found';
        })()"""
        result = self.evaluate(js)
        time.sleep(2)
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
