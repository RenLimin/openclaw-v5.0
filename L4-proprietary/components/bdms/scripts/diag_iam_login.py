#!/usr/bin/env python3
"""诊断 IAM 登录页结构：按钮、输入框、表单元素。

定位 SSO 自动登录的正确选择器（直接访问 iam.bangcle.com/#/login）。
"""
import sys
import time
import signal
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

def handler(*_):
    raise SystemExit("TIMEOUT 120s")
signal.signal(signal.SIGALRM, handler)
signal.alarm(120)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from bdms.modules.integration.adapters.browser_adapter import BrowserAdapter, IAM_BASE

print("=== 诊断 IAM 登录页结构 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器...")
    adapter.launch()
    page = adapter._page

    print("[2] 访问 IAM 登录页...")
    page.goto(IAM_BASE + "/#/login", timeout=60000, wait_until="domcontentloaded")
    time.sleep(8)

    print(f"[3] URL: {page.url[:70]}")
    print(f"    title: {page.title()}")

    print("\n[4] 所有 input 元素:")
    inputs = page.evaluate("""
        Array.from(document.querySelectorAll('input')).map(function(i){
            return {type:i.type, placeholder:i.placeholder, name:i.name, id:i.id};
        })
    """)
    for i, el in enumerate(inputs):
        print(f"    [{i}] type={el['type']} placeholder={el['placeholder']!r} name={el['name']!r} id={el['id']!r}")

    print("\n[5] 所有 button 元素:")
    buttons = page.evaluate("""
        Array.from(document.querySelectorAll('button')).map(function(b,i){
            return {idx:i, text:(b.innerText||'').trim().slice(0,30), type:b.type};
        })
    """)
    for b in buttons:
        print(f"    [{b['idx']}] type={b['type']} text={b['text']!r}")

    print("\n[6] 登录按钮相关选择器探测:")
    checks = [
        ("button[type=submit]", page.locator("button[type=submit]").count()),
        ("button.primary", page.locator("button.primary").count()),
        (".login-button", page.locator(".login-button").count()),
        ("[class*=login] button", page.locator("[class*=login] button").count()),
        ("[class*=submit]", page.locator("[class*=submit]").count()),
    ]
    for sel, cnt in checks:
        print(f"    {sel}: {cnt}")

finally:
    adapter.close()
    print("[done]")
