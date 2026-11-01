#!/usr/bin/env python3
"""E2E：ONES 自动 SSO 登录 → 筛选器标签加载 → 导出。

验证修复后的完整链路：
1. BrowserAdapter 启动新浏览器
2. ones_ensure_tab → 自动 SSO 登录（含验证码）
3. ones_click_filter_tab → 筛选器标签匹配
4. 导出流程
"""
import sys
import time
import signal
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

def handler(*_):
    raise SystemExit("TIMEOUT 240s")
signal.signal(signal.SIGALRM, handler)
signal.alarm(240)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from bdms.modules.integration.adapters.browser_adapter import BrowserAdapter

print("=== E2E: ONES 自动 SSO 登录 + 筛选器 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器 (fallback 新浏览器)...")
    adapter.launch()

    print("[2] ones_ensure_tab (触发自动 SSO 登录)...")
    ok = adapter.ones_ensure_tab()
    print(f"    ensure_tab = {ok}")
    if not ok:
        print("[❌] SSO 登录失败")
        sys.exit(1)

    print("[3] 等待筛选器导航加载...")
    time.sleep(8)
    url = adapter._page.url
    print(f"    url: {url[:70]}")
    pwd = adapter._page.locator("input[type=password]").count()
    print(f"    pwd input: {pwd}")

    # dump 左侧导航链接，确认筛选器在页面结构里
    links = adapter._page.evaluate("""
        Array.from(document.querySelectorAll('a')).map(function(a){
            return (a.innerText||'').trim();
        }).filter(Boolean)
    """)
    print(f"    a标签文本（前 20）: {links[:20]}")

    print("[4] ones_click_filter_tab (签约项目统计)...")
    ok = adapter.ones_click_filter_tab(label="2026周报-签约项目统计", tab_index=7)
    print(f"    click_filter_tab = {ok}")

finally:
    adapter.close()
    print("[done] 浏览器已关闭")
