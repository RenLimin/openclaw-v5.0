#!/usr/bin/env python3
"""聚焦自测：BrowserAdapter 新浏览器 + Cookie 注入 → ONES 可访问性。

验证 CDP fallback 修复后，无需手动开 Chrome 即可自动化访问 ONES。
"""
import sys
import signal
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

def handler(*_):
    raise SystemExit("TIMEOUT 120s")
signal.signal(signal.SIGALRM, handler)
signal.alarm(120)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from bdms.modules.integration.adapters.browser_adapter import BrowserAdapter, ONES_BASE

print("=== 自测: BrowserAdapter 新浏览器启动 + ONES 访问 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器 (无 CDP，走 fallback 新浏览器)...")
    adapter.launch()  # 不传 cdp_url，走新浏览器
    print("[2] 启动成功，注入 IAM Cookie...")

    print("[3] 访问 ONES...")
    adapter.navigate(ONES_BASE + "/project/#/workspace/home", wait_network_idle=False, timeout=30000)
    title = adapter._page.title()
    print(f"[4] 页面标题: {title}")

    url = adapter._page.url
    print(f"[5] 当前 URL: {url}")

    if "login" in url or "auth" in url:
        print("[6] ❌ 被重定向到登录页，Cookie 未生效")
    else:
        print("[6] ✅ 成功访问 ONES 工作台")
finally:
    adapter.close()
    print("[7] 浏览器已关闭")
