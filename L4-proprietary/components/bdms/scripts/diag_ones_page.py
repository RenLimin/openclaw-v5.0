#!/usr/bin/env python3
"""诊断：ONES 页面加载状态 — 登录态 / 筛选器标签 / 页面结构。

逐秒 dump：URL、标题、登录元素、a标签文本，定位标签未加载根因。
"""
import sys
import time
import signal
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

def handler(*_):
    raise SystemExit("TIMEOUT 150s")
signal.signal(signal.SIGALRM, handler)
signal.alarm(150)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from bdms.modules.integration.adapters.browser_adapter import BrowserAdapter, ONES_BASE

print("=== 诊断: ONES 页面加载状态 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器 (fallback 新浏览器)...")
    adapter.launch()
    print("[2] 访问 ONES...")
    adapter.navigate(ONES_BASE + "/project/#/workspace/home", wait_network_idle=False, timeout=30000)

    for sec in range(1, 16):
        time.sleep(3)
        page = adapter._page
        url = page.url
        title = page.title()
        # 检查登录元素
        login_els = page.locator("input[type=password]").count()
        # 统计 a 标签
        a_count = page.evaluate("document.querySelectorAll('a').length")
        # 筛选器标签
        tab_count = page.evaluate("document.querySelectorAll('.url-foldable-tabs-new-link').length")
        # 页面主体文本前 80 字符
        body = page.evaluate("(document.body.innerText||'').replace(/\\s+/g,' ').trim().slice(0,120)")
        print(f"[{sec*3}s] url={url[:60]} | title={title[:30]} | pwd_input={login_els} | a_tags={a_count} | filter_tabs={tab_count} | body={body}")
        if tab_count > 0:
            # 列出所有筛选器 tab 文本
            tabs = page.evaluate("""
                Array.from(document.querySelectorAll('.url-foldable-tabs-new-link'))
                    .map(t => (t.innerText||'').trim()).filter(Boolean)
            """)
            print(f"    filter tabs: {tabs}")
            break
        if "login" in url or "auth" in url:
            print("[!] 被重定向到登录页 — Cookie 未生效!")
            break
finally:
    adapter.close()
    print("[done] 浏览器已关闭")
