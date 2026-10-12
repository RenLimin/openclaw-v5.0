"""浏览器上下文管理，支持：
1. 预存 Cookie 连接
2. 连接本地已打开 Chrome 实例（复用登录态）
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext

from bdms.core.paths import DATA_DIR

_browser_contexts: Dict[str, BrowserContext] = {}

def _get_cookie_path(context_name: str) -> Path:
    return DATA_DIR / "browser" / f"{context_name}_cookies.json"

def save_browser_cookies(context_name: str, cookies: list) -> None:
    """保存浏览器 Cookie 到本地，供后续连接使用。"""
    cookie_path = _get_cookie_path(context_name)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")

def get_browser_context(context_name: str) -> Optional[BrowserContext]:
    """获取浏览器上下文，优先使用已保存 Cookie，其次看是否连接了本地 Chrome。"""
    if context_name in _browser_contexts:
        return _browser_contexts[context_name]
    
    cookie_path = _get_cookie_path(context_name)
    if cookie_path.exists():
        cookies = json.loads(cookie_path.read_text(encoding="utf-8"))
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context()
            context.add_cookies(cookies)
            _browser_contexts[context_name] = context
            return context
    
    return None

def connect_local_chrome(context_name: str, port: int = 9222) -> BrowserContext:
    """连接本地打开的 Chrome 实例，复用其已有的登录态。"""
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
        # 取第一个上下文（就是当前打开的 Chrome 用户实例）
        context = browser.contexts[0]
        # 保存 cookies 下来，后续可以复用
        cookies = context.cookies()
        save_browser_cookies(context_name, cookies)
        # 缓存上下文
        _browser_contexts[context_name] = context
        return context


def import_wecom_mac_cookies(context_name: str = "wecom") -> bool:
    """从企微 Mac 客户端 CEF 缓存中提取企微文档 Cookie，注入到浏览器上下文。

    利用企微 Mac 客户端的登录态，无需额外登录企业账号。
    返回是否成功提取到有效 Cookie。
    """
    import sqlite3
    import glob

    # 企微 CEF Cookie 候选路径（按企业主账号优先）
    cef_cookie_pattern = "/Users/bangcle/Library/Containers/com.tencent.WeWorkMac/Data/Documents/cefcache/wew_*/Cookies"
    cookie_files = sorted(glob.glob(cef_cookie_pattern), reverse=True)

    all_cookies = []
    for cf in cookie_files:
        try:
            conn = sqlite3.connect(cf)
            cur = conn.cursor()
            cur.execute(
                """SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
                   FROM cookies
                   WHERE host_key LIKE '%.doc.weixin.qq.com%'
                      OR host_key LIKE '%.drive.weixin.qq.com%'
                      OR host_key LIKE '%.weixin.qq.com%'"""
            )
            rows = cur.fetchall()
            conn.close()
            for r in rows:
                cookie = {
                    "name": r[0],
                    "value": r[1],
                    "domain": r[2],
                    "path": r[3],
                    "expires": r[4] / 1000000 - 11644473600 if r[4] else -1,
                    "secure": bool(r[5]),
                    "httpOnly": bool(r[6]),
                }
                all_cookies.append(cookie)
        except Exception:
            continue

    if not all_cookies:
        return False

    # 去重（同名同域取第一个）
    seen = set()
    unique = []
    for c in all_cookies:
        key = (c["name"], c["domain"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    # 保存到本地 Cookie 文件
    save_browser_cookies(context_name, unique)
    return True
