#!/usr/bin/env python3
"""Self-contained OA export: start Chrome CDP, login, export, download."""
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

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    print(f"Connected! Contexts: {len(browser.contexts)}")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    # 5. Login to IAM
    print("=== Logging into IAM ===")
    page.goto("https://iam.bangcle.com/#/login", timeout=30000, wait_until="networkidle")
    time.sleep(2)
    page.locator("input[type=text]").first.fill("limin.ren")
    page.locator("input[type=password]").first.fill("June-123")
    page.locator("button:has-text('登录')").first.click()
    page.wait_for_load_state("networkidle", timeout=20000)
    print(f"Logged in: {page.title()}")

    # 6. Navigate to OA
    print("=== Navigating to OA ===")
    page.goto("https://oa.bangcle.com", timeout=30000, wait_until="networkidle")
    time.sleep(3)
    print(f"OA URL: {page.url[:100]}")
    print(f"OA Title: {page.title()}")

    # 7. Navigate to contract ledger
    print("=== Navigating to contract ledger ===")
    menu_path = ["门户", "销售合同管理系统", "合同基本信息管理", "合同台账"]
    for label in menu_path:
        # Try multiple selectors
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
                print(f"  Clicked: {label} (via {sel[:30]})")
                time.sleep(2)
                found = True
                break
        if not found:
            # Fuzzy text search
            item = page.get_by_text(label, exact=False).first
            if item.count() > 0:
                item.click()
                print(f"  Clicked (fuzzy): {label}")
                time.sleep(2)
            else:
                print(f"  NOT FOUND: {label}")
                # Debug: show all menu text
                all_text = page.locator(".ant-menu").text_content()
                print(f"  Menu text: {all_text[:200]}")
                sys.exit(1)

    # 8. Wait for table
    print("=== Waiting for table ===")
    page.wait_for_selector(".ant-table", timeout=15000)
    print("Table loaded!")

    # 9. Click export
    print("=== Triggering export ===")
    export_btn = page.locator("button:has-text('导出')").first
    if export_btn.count() > 0:
        export_btn.click()
        print("Export triggered!")
    else:
        # Try other selectors
        export_btn = page.locator("button.ant-btn-primary").filter(has_text="导出").first
        if export_btn.count() > 0:
            export_btn.click()
            print("Export triggered (alt)!")
        else:
            print("Export button not found!")
            sys.exit(1)

    # 10. Wait for progress modal
    print("=== Waiting for progress modal ===")
    page.wait_for_selector(".ant-modal", timeout=10000)
    print("Progress modal appeared")

    # 11. Poll for completion
    start = time.time()
    while time.time() - start < 600:
        time.sleep(5)
        modal = page.locator(".ant-modal-body, .ant-modal-content").first
        if modal.count() > 0:
            text = modal.text_content()
            import re
            m = re.search(r'(\d+)/(\d+)', text)
            if m:
                cur, total = int(m.group(1)), int(m.group(2))
                pct = cur / total * 100 if total > 0 else 0
                print(f"  Progress: {cur}/{total} ({pct:.1f}%)")
                if cur >= total:
                    print("  COMPLETE!")
                    break
        # Check for download link
        dl = page.locator("a:has-text('下载'), a[href*='download']").first
        if dl.count() > 0:
            print("  Download link found!")
            break

    # 12. Download
    print("=== Downloading ===")
    dl = page.locator("a:has-text('下载'), a[href*='download']").first
    if dl.count() > 0:
        with page.expect_download(timeout=120000) as dl_info:
            dl.click()
        download = dl_info.value
        save_path = Path.home() / "Downloads" / download.suggested_filename
        download.save_as(str(save_path))
        print(f"SUCCESS: {save_path} ({save_path.stat().st_size} bytes)")
    else:
        print("No download link, checking Downloads folder...")
        files = sorted(Path.home().glob("Downloads/*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
        if files:
            print(f"Latest CSV: {files[0]} ({files[0].stat().st_size} bytes)")

    browser.close()

# 13. Kill Chrome CDP
print("=== Cleaning up ===")
os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
print("Done!")
