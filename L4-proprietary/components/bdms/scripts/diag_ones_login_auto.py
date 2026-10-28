#!/usr/bin/env python3
"""诊断：用 ONES 凭据登录 ONES 独立登录页，确认验证码触发情况。

登录页结构（diag_ones_login 确认）：
  input[0] type=text      placeholder='请输入你的邮箱'
  input[1] type=password  placeholder='请输入你的密码'
  input[2] type=text      placeholder='请输入图形验证码' (hidden)
  button[0] type=submit   text='登录'
"""
import sys
import time
import signal
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

def handler(*_):
    raise SystemExit("TIMEOUT 180s")
signal.signal(signal.SIGALRM, handler)
signal.alarm(180)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from bdms.modules.integration.adapters.browser_adapter import BrowserAdapter, ONES_BASE

# 读取 ONES 凭据（两行：邮箱 + 密码）
ones_cred = Path.home() / ".openclaw" / "secrets" / "ones.basic"
if ones_cred.exists():
    lines = ones_cred.read_text(encoding="utf-8").strip().split("\n")
    email = lines[0].strip()
    password = lines[1].strip()
else:
    raise SystemExit("❌ 缺少 ONES 凭据：请配置 ~/.openclaw/secrets/ones.basic（两行 email/password）")
print(f"凭据: {email} / {password[:3]}***")

print("=== 诊断: ONES 登录页自动登录 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器...")
    adapter.launch()
    page = adapter._page

    print("[2] 访问 ONES（触发 SSO 重定向到登录页）...")
    page.goto(ONES_BASE + "/project/#/workspace/home", timeout=60000, wait_until="domcontentloaded")
    time.sleep(8)

    url = page.url
    pwd = page.locator("input[type=password]").count()
    print(f"[3] url={url[:70]} | pwd={pwd}")
    if pwd == 0:
        print("[4] 无需登录（已有会话）")
        sys.exit(0)

    print("[4] 填充 ONES 登录表单...")
    email_box = page.locator("input[type=text]").first
    email_box.fill(email)
    page.locator("input[type=password]").first.fill(password)

    print("[5] 点击登录按钮 (button[type=submit])...")
    submit = page.locator("button[type=submit]")
    if submit.count() > 0:
        submit.first.click()
    else:
        page.locator("button").filter(has_text="登录").first.click()
    time.sleep(5)

    for round_n in range(1, 8):
        time.sleep(3)
        url = page.url
        pwd = page.locator("input[type=password]").count()
        # 检查各种验证码输入框
        captcha_email = page.locator("input[placeholder*=验证码],input[placeholder*=验证码]").count()
        graphic_captcha = page.locator("input[placeholder*=图形验证码]").count()
        all_inputs = page.evaluate("""
            Array.from(document.querySelectorAll('input')).map(function(i){
                return {type:i.type, ph:i.placeholder, vis:i.offsetParent!==null};
            })
        """)
        visible_inputs = [i for i in all_inputs if i['vis']]
        print(f"[round {round_n}] url={url[:60]} | pwd={pwd} | email_captcha={captcha_email} | graphic={graphic_captcha}")
        print(f"    visible inputs: {visible_inputs}")
        if "ones.bangcle.com" in url and pwd == 0 and captcha_email == 0:
            print("[✅] 登录成功，已进入 ONES!")
            break
        # 如果有验证码输入框，尝试填
        if captcha_email > 0:
            print("[*] 检测到邮件验证码输入框，尝试自动获取...")
            from bdms.modules.integration.adapters.browser_adapter import _fetch_iam_captcha
            code = _fetch_iam_captcha()
            print(f"    验证码: {code}")
            if code:
                box = page.locator("input[placeholder*=验证码]").first
                box.fill(code)
                submit = page.locator("button[type=submit]")
                if submit.count() > 0:
                    submit.first.click()
                else:
                    page.locator("button").filter(has_text="登录").first.click()
                time.sleep(3)
            else:
                print("[!] 无法获取验证码")
                break
        if graphic_captcha > 0:
            print("[!] 需要图形验证码，无法自动处理，需人工")
            break
        if "auth/login" not in url and "iam.bangcle.com" in url:
            print("[*] 跳转到 IAM 登录页")
            break

finally:
    adapter.close()
    print("[done]")
