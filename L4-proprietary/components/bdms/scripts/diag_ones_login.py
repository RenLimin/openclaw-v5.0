#!/usr/bin/env python3
"""诊断 ONES 自己的登录页 (#/auth/login) 结构。

SSO 重定向目标是 ones.bangcle.com/project/#/auth/login，
这是 ONES 独立登录页（邮箱+密码），不是 IAM 登录页。
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

print("=== 诊断 ONES 独立登录页结构 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器...")
    adapter.launch()
    page = adapter._page

    print("[2] 访问 ONES（触发 SSO 重定向到 ONES 登录页）...")
    page.goto(ONES_BASE + "/project/#/workspace/home", timeout=60000, wait_until="domcontentloaded")
    time.sleep(10)

    url = page.url
    print(f"[3] URL: {url[:80]}")
    print(f"    title: {page.title()}")

    print("\n[4] 所有 input 元素:")
    inputs = page.evaluate("""
        Array.from(document.querySelectorAll('input')).map(function(i){
            return {type:i.type, placeholder:i.placeholder, name:i.name, id:i.id, visible:i.offsetParent!==null};
        })
    """)
    for i, el in enumerate(inputs):
        print(f"    [{i}] type={el['type']} placeholder={el['placeholder']!r} name={el['name']!r} id={el['id']!r} visible={el['visible']}")

    print("\n[5] 所有 button 元素:")
    buttons = page.evaluate("""
        Array.from(document.querySelectorAll('button')).map(function(b,i){
            return {idx:i, text:(b.innerText||'').trim().slice(0,30), type:b.type, visible:b.offsetParent!==null};
        })
    """)
    for b in buttons:
        print(f"    [{b['idx']}] type={b['type']} text={b['text']!r} visible={b['visible']}")

    print("\n[6] 登录按钮选择器探测:")
    checks = [
        ("button[type=submit]", page.locator("button[type=submit]").count()),
        ("[class*=login] button", page.locator("[class*=login] button").count()),
        ("button.ant-btn-primary", page.locator("button.ant-btn-primary").count()),
        ("[class*=submit]", page.locator("[class*=submit]").count()),
        ("form button", page.locator("form button").count()),
    ]
    for sel, cnt in checks:
        print(f"    {sel}: {cnt}")

finally:
    adapter.close()
    print("[done]")
