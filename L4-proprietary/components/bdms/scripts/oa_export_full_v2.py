#!/usr/bin/env python3
"""Self-contained OA export: start Chrome CDP, login, export, download.

Correct flow:
1. Login IAM https://iam.bangcle.com/#/login
2. On IAM home page, click "OA协同办公平台" app entry → open OA in new tab
3. In OA,逐级点击菜单: 门户 → 销售合同管理系统 → 合同基本信息管理 → 合同台账（销售）
4. Click export → wait progress complete → download CSV
"""
import os, sys, time, json, subprocess, signal
from pathlib import Path

# 1. Kill any existing Chrome CDP
print("=== Cleaning up old Chrome CDP ===")
subprocess.run(["pkill", "-9", "-f", "remote-debugging-port=9222"], capture_output=True)
time.sleep(2)

# 2. Start Chrome CDP as child process
print("=== Starting Chrome CDP ===")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
USER_DIR = "/Users/bangcle/.chrome-cdp-profile"
LOG = "/tmp/chrome-cdp-final.log"

# Remove old profile to avoid conflicts
import shutil
shutil.rmtree(USER_DIR, ignore_errors=True)

proc = subprocess.Popen(
    [CHROME, "--remote-debugging-port=9222", f"--user-data-dir={USER_DIR}",
     "--no-first-run", "--disable-extensions", "--disable-sync",
     "--disable-background-networking", "--disable-gpu"],
    stdout=open(LOG, "w"), stderr=subprocess.STDOUT,
    preexec_fn=os.setsid
)
print(f"Chrome CDP PID: {proc.pid}")

# 3. Wait for CDP port
print("=== Waiting for CDP port ===")
import socket
for _ in range(30):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect(("127.0.0.1", 9222))
            print("CDP port ready!")
            break
    except:
        time.sleep(1)
else:
    print("CDP port timeout!")
    sys.exit(1)

# 4. Playwright connection with NO proxy
print("=== Connecting Playwright ===")
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','all_proxy','ALL_PROXY']:
    os.environ.pop(k, None)
os.environ['no_proxy'] = '*'

from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    print(f"Connected! Contexts: {len(browser.contexts)}")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    # 5. Login to IAM
    print("=== Logging into IAM ===")
    page.goto("https://iam.bangcle.com/#/login", timeout=30000, wait_until="networkidle")
    time.sleep(2)

    # Fill credentials
    page.locator("input[type=text]").first.fill("limin.ren")
    page.locator("input[type=password]").first.fill("June-123")
    page.locator("button:has-text('登录')").first.click()
    # Wait longer for redirect to home after login
    print("  Waiting for redirect after login...")
    time.sleep(10)
    page.wait_for_load_state("networkidle", timeout=20000)
    time.sleep(5)
    print(f"Logged in: {page.title()}")
    print(f"Current URL: {page.url}")

    # 6. Click "OA协同办公平台" app entry on IAM home page
    print("=== Clicking OA app entry on IAM home ===")

    # Wait for app list to load
    page.wait_for_selector(".app-item, .app-name, [class*=app]", timeout=15000)
    time.sleep(3)

    # Try to find OA app
    app_found = False
    selectors = [
        "text=OA协同办公平台",
        "app-name:has-text('OA协同办公平台')",
        ".app-item:has-text('OA协同办公平台')",
        "div:has-text('OA协同办公平台')",
    ]
    for sel in selectors:
        item = page.locator(sel).first
        if item.count() > 0:
            # Listen for new page before click
            with ctx.expect_page() as p_info:
                item.click()
            new_page = p_info.value
            print(f"  Clicked OA app entry, opened new tab: {new_page.title()}")
            page = new_page
            page.wait_for_load_state("networkidle", timeout=30000)
            app_found = True
            break

    if not app_found:
        print("❌ OA app entry not found on IAM home page!")
        # Debug: list all app names
        print("\nDebug: current page all text containing 'OA':")
        all_elements = page.locator("div, span, a").all()
        for el in all_elements:
            txt = el.text_content()
            if "OA" in txt:
                print(f"  - {txt.strip()}")
        sys.exit(1)

    print(f"✅ OA loaded, URL: {page.url[:100]}")
    print(f"OA Title: {page.title()}")

    # 7. Navigate to contract ledger (逐级点击菜单)
    print("=== Navigating to contract ledger ===")
    menu_path = ["门户", "销售合同管理系统", "合同基本信息管理", "合同台账"]
    for label in menu_path:
        # Try multiple selectors (OA uses antd menu)
        selectors = [
            f"text={label}",
            f".ant-menu-item:has-text('{label}')",
            f".ant-menu-submenu-title:has-text('{label}')",
            f"a[role=menuitem]:has-text('{label}')",
            f"span:has-text('{label}')",
        ]
        found = False
        for sel in selectors:
            item = page.locator(sel).first
            if item.count() > 0:
                item.click()
                print(f"  Clicked: {label} (via {sel[:50]})")
                time.sleep(5)  # Wait for submenu / page to load
                found = True
                break
        if not found:
            # Fuzzy text search
            item = page.get_by_text(label, exact=False).first
            if item.count() > 0:
                item.click()
                print(f"  Clicked (fuzzy): {label}")
                time.sleep(5)
                found = True
            else:
                print(f"  ❌ NOT FOUND: {label}")
                # Debug: show all menu text
                menu_text = ""
                menu_el = page.locator(".ant-menu").first
                if menu_el.count() > 0:
                    menu_text = menu_el.text_content()
                print(f"  Debug: menu text (first 200 chars): {menu_text[:200]}")
                sys.exit(1)

    # 8. Wait for table
    print("=== Waiting for table to load ===")
    page.wait_for_selector(".ant-table, [class*=table]", timeout=20000)
    time.sleep(10)  # Extra wait for data to load
    print("✅ Table loaded!")

    # 9. Click export button
    print("=== Triggering export ===")
    export_found = False
    selectors = [
        "button:has-text('导出')",
        "button.ant-btn-primary:has-text('导出')",
        ".ant-btn-primary:has-text('导出')",
        "button:has-text('导 出')",  # space between chars
    ]
    for sel in selectors:
        export_btn = page.locator(sel).first
        if export_btn.count() > 0:
            export_btn.click()
            print(f"✅ Export triggered! (via {sel})")
            export_found = True
            break

    if not export_found:
        print("❌ Export button not found!")
        sys.exit(1)

    # 10. Wait for progress modal
    print("=== Waiting for progress modal to appear ===")
    page.wait_for_selector(".ant-modal, [class*=modal]", timeout=15000)
    print("✅ Progress modal appeared")
    time.sleep(3)

    # 11. Poll for completion (up to 10 minutes)
    print("=== Polling export progress ===")
    start = time.time()
    max_wait = 600  # 10 minutes
    download_url = None

    while time.time() - start < max_wait:
        time.sleep(10)

        # Check if download link appeared in modal
        download_link = page.locator(".ant-modal a:has-text('下载')")
        if download_link.count() > 0:
            download_url = download_link.get_attribute("href")
            print(f"✅ Export completed! Download URL: {download_url[:80]}...")
            break

        # Check progress
        modal_text = page.locator(".ant-modal-body, .ant-modal-content").first.text_content()
        import re
        m = re.search(r'(\d+)/(\d+)', modal_text)
        if m:
            cur, total = int(m.group(1)), int(m.group(2))
            pct = cur / total * 100 if total > 0 else 0
            print(f"  Progress: {cur}/{total} ({pct:.1f}%)")

    if not download_url:
        print(f"❌ Export not completed within {max_wait} seconds (10 minutes)")
        # Check current modal content
        modal_text = page.locator(".ant-modal").first.text_content()
        print(f"  Current modal content: {modal_text}")
        sys.exit(1)

    # 12. Download the CSV file
    print("=== Downloading CSV ===")
    output_dir = Path.home() / ".openclaw" / "data" / "oa_exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Click download link
    with page.expect_download(timeout=60000) as download_info:
        page.locator("a:has-text('下载')").first.click()
    download = download_info.value

    # Save file
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"oa_contract_ledger_{timestamp}.csv"
    output_path = output_dir / filename
    download.save_as(output_path)

    file_size = output_path.stat().st_size
    print(f"""
🎉 导出成功！
文件位置: {output_path.resolve()}
文件大小: {file_size / (1024*1024):.2f} MB
""")

    # Cleanup
    print("=== Cleaning up ===")
    browser.close()
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    sys.exit(0)
