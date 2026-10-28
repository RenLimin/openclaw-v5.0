#!/usr/bin/env python3
"""验证：新浏览器完整 SSO 登录流 → 访问 ONES 工作台。

流程：fresh browser → ones.bangcle.com → IAM 登录（含验证码自动获取）→ 回跳 ONES → 保存全部 cookie。
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
    BrowserAdapter, IAM_BASE, ONES_BASE, set_cookie,
    _iam_credentials,
)
from bdms.core import config

print("=== SSO 全流程验证 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器...")
    adapter.launch()
    page = adapter._page

    print("[2] 访问 ONES（应重定向到 IAM 登录）...")
    page.goto(ONES_BASE + "/project/#/workspace/home", timeout=60000, wait_until="domcontentloaded")
    time.sleep(3)

    # 检查是否已到 IAM 登录页
    url = page.url
    print(f"[3] 当前 URL: {url}")
    pwd = page.locator("input[type=password]").count()
    print(f"    密码输入框数量: {pwd}")

    if pwd == 0 and "ones.bangcle.com" in url:
        print("[4] ✅ 直接访问 ONES 成功（可能已有会话），检查工作台...")
    else:
        # 登录 IAM
        print("[4] 填充 IAM 登录表单...")
        _ss_user, _ss_pass = _iam_credentials()
        page.locator("input[type=text]").first.fill(_ss_user)
        page.locator("input[type=password]").first.fill(_ss_pass)
        page.locator("button").nth(1).click()
        time.sleep(3)

        # 检查验证码
        captcha = page.locator("input[placeholder*=验证码],input[placeholder*=captcha]")
        if captcha.count() > 0:
            print("[5] 出现验证码，自动获取...")
            from bdms.modules.integration.adapters.browser_adapter import _fetch_iam_captcha
            code = _fetch_iam_captcha()
            print(f"    验证码: {code}")
            if code:
                captcha.first.fill(code)
                page.locator("button").nth(1).click()
                time.sleep(3)
        else:
            print("[5] 无需验证码")

    print("[6] 等待 SSO 回跳 ONES...")
    for _ in range(10):
        time.sleep(3)
        url = page.url
        title = page.title()
        login_input = page.locator("input[type=password]").count()
        filter_tabs = page.evaluate("document.querySelectorAll('.url-foldable-tabs-new-link').length") if "ones.bangcle.com" in url else 0
        print(f"    url={url[:70]} | title={title[:30]} | pwd={login_input} | filter_tabs={filter_tabs}")
        if "ones.bangcle.com" in url and login_input == 0:
            print("[7] ✅ SSO 成功，已进入 ONES")
            # 保存全部 cookie
            all_cookies = adapter._context.cookies()
            from bdms.modules.integration.adapters.browser_adapter import DOMAINS
            domain_cookies = {}
            for c in all_cookies:
                d = c.get("domain", "").lstrip(".")
                if d not in domain_cookies:
                    domain_cookies[d] = []
                domain_cookies[d].append(c["name"] + "=" + c["value"])
            for d, pairs in domain_cookies.items():
                cookie_str = "; ".join(pairs)
                set_cookie(d, cookie_str)
                print(f"    saved {d}: {len(pairs)} cookies, len={len(cookie_str)}")
            break
    else:
        print("[7] ❌ SSO 未完成")
finally:
    adapter.close()
    print("[done] 浏览器已关闭")
