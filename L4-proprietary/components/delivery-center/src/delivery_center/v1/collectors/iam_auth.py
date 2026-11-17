"""IAM 认证管理

Cookie 池复用：登录一次 IAM，ONES/OA/工时门户共享 Cookie。
有效期 12 小时，自动刷新。

IAM 面板点击跳转说明：
  - IAM 首页的应用面板（OA/ONES/工时等）点击后会打开新标签页
  - 用 context.on("page", callback) 监听新页面事件
  - 直接 context.pages 检查可能遗漏（事件循环延迟）
  - 面板点击方式：locator.click() 或 locator.click(force=True)
  - mouse.click(center) 不触发跳转
  - ONES 面板点击后先打开 OA 标签页，再跳转到 ONES（经过 OA shell SSO 中转）
  - 工时门户面板点击后直接打开 OA 工时系统标签页
"""

import json
import time
from pathlib import Path
from typing import Optional

COOKIE_FILE = Path.home() / ".openclaw" / "data" / "iam_cookies.json"
SECRETS_DIR = Path.home() / ".openclaw" / "secrets"


def iam_credentials() -> tuple:
    """从 secrets 读取 IAM (username, password)，无则返回空串。"""
    u = SECRETS_DIR / "iam.username"
    w = SECRETS_DIR / "iam.password"
    return (
        u.read_text(encoding="utf-8").strip() if u.exists() else "",
        w.read_text(encoding="utf-8").replace("\n", "").strip() if w.exists() else "",
    )


def ones_credentials() -> tuple:
    """从 secrets 读取 ONES (email, password)。

    优先 ones.basic（两行 email/password），回退 iam.email_username/email_password。
    """
    basic = SECRETS_DIR / "ones.basic"
    if basic.exists():
        lines = basic.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) >= 2:
            return lines[0].strip(), lines[1].strip()
    e = SECRETS_DIR / "iam.email_username"
    w = SECRETS_DIR / "iam.email_password"
    return (
        e.read_text(encoding="utf-8").strip() if e.exists() else "",
        w.read_text(encoding="utf-8").strip() if w.exists() else "",
    )
COOKIE_TTL = 12 * 3600  # 12 小时

# Cookie 域名 keys
DOMAINS = ["iam.bangcle.com", "ones.bangcle.com", "oa.bangcle.com"]


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




def _fetch_email_captcha(timeout: int = 90, since_ts: Optional[float] = None) -> Optional[str]:
    """IMAP 直读网易企业邮箱，获取 IAM 二步验证 6 位验证码。

    优先复用 bdms 的 email_captcha 适配器（config.json 驱动）；
    失败则回退到 secrets 直读（iam.email_username/iam.email_password）。
    取码失败返回 None（调用方按超时处理，不假报成功）。
    """
    import ssl
    import imaplib
    import re
    from email import message_from_bytes
    from email.header import decode_header

    host, port = "hwhzimap.qiye.163.com", 993
    sender, keyword = "imb@bangcle.com", "登录验证码"
    username = password = ""
    try:
        sys_path_hack = None  # noqa: F841
        from bdms.core import config  # type: ignore
        cfg = (config.get("integrations.iam.email", {}) or {})
        imap = cfg.get("imap", {}) or {}
        cred = cfg.get("credentials", {}) or {}
        host = imap.get("host", host)
        port = int(imap.get("port", port))
        sender = imap.get("sender", sender)
        keyword = imap.get("subject_keyword", keyword)
        uf = Path(cred.get("username_file", "")).expanduser()
        pf = Path(cred.get("password_file", "")).expanduser()
        if uf.exists():
            username = uf.read_text(encoding="utf-8").strip()
        if pf.exists():
            password = pf.read_text(encoding="utf-8").strip()
    except Exception:
        uf = SECRETS_DIR / "iam.email_username"
        pf = SECRETS_DIR / "iam.email_password"
        if uf.exists():
            username = uf.read_text(encoding="utf-8").strip()
        if pf.exists():
            password = pf.read_text(encoding="utf-8").strip()
    if not username or not password:
        print("  ⚠️ 邮箱凭据缺失，无法自动取码")
        return None

    def _dec(v) -> str:
        if not v:
            return ""
        out = ""
        for part, enc in decode_header(v):
            out += part.decode(enc or "utf-8", "replace") if isinstance(part, bytes) else part
        return out

    def _body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
        payload = msg.get_payload(decode=True)
        return payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""

    try:
        ctx = ssl.create_default_context()
        mail = imaplib.IMAP4_SSL(host=host, port=port, ssl_context=ctx)
        mail.login(username, password)
        mail.select("INBOX")
        status, data = mail.search(None, "ALL")
        ids = data[0].split() if status == "OK" else []
        # 最近 10 封里找验证码邮件
        for mid in ids[-10:]:
            st, raw = mail.fetch(mid, "(RFC822)")
            if st != "OK" or not raw or not raw[0]:
                continue
            msg = message_from_bytes(raw[0][1])
            subj = _dec(msg.get("Subject", ""))
            frm = _dec(msg.get("From", ""))
            if sender not in frm or keyword not in subj:
                continue
            if since_ts is not None:
                try:
                    from email.utils import parsedate_to_datetime
                    if parsedate_to_datetime(msg.get("Date")).timestamp() <= since_ts:
                        continue
                except Exception:
                    pass
            text = _body(msg)
            m = re.search(r"(?:验证码|code)[^0-9]{0,20}(\d{6,8})", text, re.I) or re.search(r"(?<!\d)(\d{6})(?!\d)", text)
            if m:
                mail.logout()
                return m.group(1)
        mail.logout()
    except Exception as e:
        print(f"  ⚠️ IMAP 取码失败: {e}")
    return None


def _wait_login_form(page, timeout: int = 30000):
    """等待 IAM 登录表单（账号/密码框）真正可见。

    IAM 经 OA SSO 中转，约 5-8s 才渲染表单；过早 fill 命中
    'element is not visible'。兼容顶层与 iframe。
    返回 (user_locator, pass_locator)。
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        up = page.locator("input[type=text]").first
        pp = page.locator("input[type=password]").first
        try:
            if up.count() and pp.count() and up.is_visible() and pp.is_visible():
                return up, pp
        except Exception as e:
            last = e
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            try:
                fu = fr.locator("input[type=text]").first
                fp = fr.locator("input[type=password]").first
                if fu.count() and fp.count() and fu.is_visible() and fp.is_visible():
                    return fu, fp
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"IAM 登录表单 {timeout}s 内未可见（最后错误：{last}）")


def login_iam(username: str, password: str, verify_timeout: int = 300) -> bool:
    """登录 IAM 获取 Cookie。

    适配 2026-11 起的二步验证：账号密码 → 邮箱 6 位验证码。
    密码提交后若进入验证码页，则等待人工完成验证（headful 下在浏览器输入，
    或 headless 下通过 verify_code 回调/环境变量注入），最长 verify_timeout 秒。

    Args:
        username: IAM 用户名
        password: IAM 密码
        verify_timeout: 等待二步验证完成的最长秒数（默认 300）

    Returns:
        登录成功返回 True
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright 未安装：pip install playwright && playwright install chromium")
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto("https://iam.bangcle.com/#/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)

            user_box, pass_box = _wait_login_form(page)
            user_box.fill(username)
            pass_box.fill(password)
            # 按钮文案可能是「下一步」或「登录」
            nxt = page.locator("button").filter(has_text="下一步")
            if nxt.count():
                nxt.first.click()
            else:
                login_btn = page.locator("button").filter(has_text="登录")
                (login_btn.first if login_btn.count() else page.locator("button").nth(1)).click()

            # 检测是否进入二步验证
            t0 = time.time()
            two_fa = False
            while time.time() - t0 < 10:
                body = page.inner_text("body")
                if "验证并登录" in body or "验证码" in body or "邮箱安全验证" in body:
                    two_fa = True
                    break
                if "/home" in page.url:
                    break
                time.sleep(1)

            if two_fa:
                print("  ⚠️ IAM 已启用二步验证（邮箱 6 位验证码）")
                print(f"  → 请在 {verify_timeout}s 内完成邮箱验证（headful 浏览器输入，"
                      f"或通过 IAM_VERIFY_CODE 环境变量/邮件读取）")
                # 支持环境变量一次性注入（自动化场景）
                import os
                code = os.environ.get("IAM_VERIFY_CODE", "").strip()
                if not code:
                    print("  → 自动从邮箱获取验证码（IMAP）...")
                    code = _fetch_email_captcha(timeout=75, since_ts=t0) or ""
                if code:
                    try:
                        box = page.locator(
                            "input[placeholder*='6 位邮箱验证码']"
                        )
                        if box.count() == 0:
                            box = page.locator("input[type=text]").first
                        box.first.fill(code)
                        btn = page.locator("button").filter(has_text="验证并登录")
                        (btn.first if btn.count() else page.locator("button").nth(1)).click()
                        print(f"  ✅ 已注入验证码（{code[:2]}****）")
                    except Exception as e:
                        print(f"  ⚠️ 验证码注入失败: {e}")
                # 等待离开登录页
                t1 = time.time()
                while time.time() - t1 < verify_timeout:
                    time.sleep(3)
                    if "/login" not in page.url:
                        break
                    if "验证并登录" not in page.inner_text("body") and "/home" in page.url:
                        break
                else:
                    print("  ❌ 二步验证超时，登录失败")
                    return False
            else:
                try:
                    page.wait_for_url("**/home/**", timeout=15000)
                except Exception:
                    pass

            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)

            all_cookies = context.cookies()
            print(f"  获取到 {len(all_cookies)} 个 Cookie")
            domain_cookies = {}
            for c in all_cookies:
                d = c.get("domain", "").lstrip(".")
                domain_cookies.setdefault(d, []).append(f"{c['name']}={c['value']}")
            for d, pairs in domain_cookies.items():
                set_cookie(d, "; ".join(pairs))
            full_cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
            for domain in DOMAINS:
                set_cookie(domain, full_cookie_str)
            print("IAM 登录成功，Cookie 已保存")
            return True

        except Exception as e:
            print(f"IAM 登录失败: {e}")
            return False
        finally:
            browser.close()


def login_ones(email: str, password: str) -> bool:
    """登录 ONES（邮箱+密码）
    
    Args:
        email: ONES 邮箱
        password: ONES 密码
    
    Returns:
        登录成功返回 True
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright 未安装")
        return False
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            page.goto("https://ones.bangcle.com/project/#/auth/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(3)
            
            # 填写邮箱
            email_input = page.locator('input[placeholder*="邮箱"]')
            if email_input.count() == 0:
                email_input = page.locator('input[type="text"]').first
            email_input.first.fill(email)
            
            # 填写密码
            pwd_input = page.locator('input[type="password"]')
            pwd_input.first.fill(password)
            
            # 点击登录
            login_btn = page.locator('button').filter(has_text='登录')
            if login_btn.count() == 0:
                login_btn = page.locator('button.ones-button-primary')
            login_btn.first.click()
            
            # 等待跳转
            try:
                page.wait_for_url('**/workspace**', timeout=30000)
            except:
                time.sleep(10)
            
            # 保存 cookie
            cookies = context.cookies()
            cookie_file = Path.home() / ".openclaw" / "data" / "oa_exports" / "ones_auth.json"
            cookie_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cookie_file, 'w') as f:
                json.dump({"timestamp": time.time(), "url": page.url, "cookies": cookies}, f, indent=2, ensure_ascii=False)
            
            # 同时更新 cookie 池
            ones_cookies = context.cookies("https://ones.bangcle.com")
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in ones_cookies)
            set_cookie("ones.bangcle.com", cookie_str)
            
            print(f"ONES 登录成功，Cookie 已保存")
            return True
            
        except Exception as e:
            print(f"ONES 登录失败: {e}")
            return False
        finally:
            browser.close()


def ensure_logged_in() -> bool:
    """确保已登录（Cookie 有效）"""
    for domain in DOMAINS:
        if not is_cookie_valid(domain):
            print(f"{domain} Cookie 已过期，需要重新登录")
            return False
    return True

def inject_cookies_to_context(context):
    """将保存的 Cookie 注入到 Playwright context
    
    Args:
        context: Playwright browser context
    """
    cookies = _load_cookies()
    if not cookies:
        return False
    
    # 获取任意域名的 Cookie 字符串
    cookie_str = None
    for domain in DOMAINS:
        if domain in cookies and cookies[domain].get("cookie"):
            cookie_str = cookies[domain]["cookie"]
            break
    
    if not cookie_str:
        return False
    
    # 注入到所有域名
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
