"""IAM 认证管理

Cookie 池复用：登录一次 IAM，ONES/OA/工时门户共享 Cookie。
有效期 12 小时，自动刷新。
"""

import json
import time
from pathlib import Path
from typing import Optional

COOKIE_FILE = Path.home() / ".openclaw" / "data" / "iam_cookies.json"
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


def login_iam(username: str, password: str) -> bool:
    """登录 IAM 获取 Cookie

    Args:
        username: IAM 用户名
        password: IAM 密码

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
            page.goto("https://iam.bangcle.com/#/home/index", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # 填写登录表单（具体选择器需根据实际页面调整）
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')

            page.wait_for_load_state("networkidle", timeout=15000)

            # 获取 Cookie
            all_cookies = context.cookies()
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)

            for domain in DOMAINS:
                set_cookie(domain, cookie_str)

            print("IAM 登录成功，Cookie 已保存")
            return True

        except Exception as e:
            print(f"IAM 登录失败: {e}")
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
