#!/usr/bin/env python3
"""验证 ONES 会话 token 存储位置：cookie vs localStorage。

SSO 登录成功后，dump localStorage/sessionStorage keys + cookie names，
确认 ONES 会话认证依赖什么，以决定修复方案。
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

from bdms.modules.integration.adapters.browser_adapter import (
    BrowserAdapter, ONES_BASE, _iam_credentials,
)

print("=== 验证 ONES 会话 token 存储位置 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器...")
    adapter.launch()
    page = adapter._page

    print("[2] 访问 ONES 工作台...")
    page.goto(ONES_BASE + "/project/#/workspace/home", timeout=60000, wait_until="domcontentloaded")
    time.sleep(3)
    if page.locator("input[type=password]").count() > 0:
        print("[3] 需要登录，走 IAM 登录流...")
        _ds_user, _ds_pass = _iam_credentials()
        page.locator("input[type=text]").first.fill(_ds_user)
        page.locator("input[type=password]").first.fill(_ds_pass)
        page.locator("button").nth(1).click()
        time.sleep(3)
        captcha = page.locator("input[placeholder*=验证码],input[placeholder*=captcha]")
        if captcha.count() > 0:
            print("[4] 出现验证码，自动获取...")
            from bdms.modules.integration.adapters.browser_adapter import _fetch_iam_captcha
            code = _fetch_iam_captcha()
            print(f"    验证码: {code}")
            if code:
                captcha.first.fill(code)
                page.locator("button").nth(1).click()
                time.sleep(3)

    print("[5] 等待 SSO 回跳 ONES...")
    for _ in range(12):
        time.sleep(3)
        url = page.url
        if "ones.bangcle.com" in url and page.locator("input[type=password]").count() == 0:
            break
    print(f"    final url={page.url[:70]}")

    # dump localStorage keys (ones domain)
    print("\n[6] localStorage keys (ones):")
    ls = page.evaluate("Object.keys(localStorage).map(k => k + '=' + (localStorage.getItem(k)||'').slice(0,60))")
    for k in ls:
        print(f"    {k}")

    print("\n[7] sessionStorage keys (ones):")
    ss = page.evaluate("Object.keys(sessionStorage).map(k => k + '=' + (sessionStorage.getItem(k)||'').slice(0,60))")
    for k in ss:
        print(f"    {k}")

    print("\n[8] cookies:")
    for c in adapter._context.cookies():
        print(f"    domain={c['domain']} name={c['name']} len={len(c['value'])}")

finally:
    adapter.close()
    print("[done]")
