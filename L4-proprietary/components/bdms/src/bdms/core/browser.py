"""浏览器上下文管理，支持：
1. 预存 Cookie 连接
2. 连接本地已打开 Chrome 实例（复用登录态）
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext

from bdms.core.paths import get_data_path

_browser_contexts: Dict[str, BrowserContext] = {}

def _get_cookie_path(context_name: str) -> Path:
    data_dir = get_data_path()
    return data_dir / "browser" / f"{context_name}_cookies.json"

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
