#!/usr/bin/env python3
"""诊断 SSO 跳转场景的 IAM 登录页结构。

模拟：访问 ONES → 重定向到 IAM → dump 页面结构（URL/input/button）。
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

print("=== 诊断 SSO 场景 IAM 登录页结构 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器...")
    adapter.launch()
    page = adapter._page

    print("[2] 访问 ONES（触发 SSO 重定向）...")
    page.goto(ONES_BASE + "/project/#/workspace/home", timeout=60000, wait_until="domcontentloaded")
    time.sleep(8)

    for round_n in range(1, 6):
        url = page.url
        pwd = page.locator("input[type=password]").count()
        print(f"\n[round {round_n}] url={url[:80]} | pwd={pwd} | title={page.title()[:30]}")
        if "iam.bangcle.com" in url and pwd > 0:
            print("  到达 IAM 登录页，dump 结构:")
            inputs = page.evaluate("""
                Array.from(document.querySelectorAll('input')).map(function(i){
                    return {type:i.type, placeholder:i.placeholder};
                })
            """)
            print(f"    inputs: {inputs}")
            buttons = page.evaluate("""
                Array.from(document.querySelectorAll('button')).map(function(b,i){
                    return {idx:i, text:(b.innerText||'').trim().slice(0,20), type:b.type, visible: b.offsetParent!==null};
                })
            """)
            print(f"    buttons: {buttons}")
            break
        if "ones.bangcle.com" in url and pwd == 0:
            print("  已进入 ONES（无需登录）")
            break
        time.sleep(3)

finally:
    adapter.close()
    print("[done]")
