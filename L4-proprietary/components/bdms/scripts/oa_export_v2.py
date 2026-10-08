#!/usr/bin/env python3
"""OA export using existing iam_auth infrastructure."""
import os, sys, time, json
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','all_proxy','ALL_PROXY']:
    os.environ.pop(k, None)
os.environ['no_proxy'] = '*'

from pathlib import Path
from playwright.sync_api import sync_playwright

# Import existing IAM auth infrastructure
sys.path.insert(0, "/Users/bangcle/.openclaw/workspace/L4-proprietary/components/delivery-center/src")
from delivery_center.v1.collectors.iam_auth import inject_cookies_to_context, is_cookie_valid

print("=== Checking cookie status ===")
print(f"IAM valid: {is_cookie_valid('iam.bangcle.com')}")
print(f"OA valid: {is_cookie_valid('oa.bangcle.com')}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(accept_downloads=True)
    
    # Inject saved cookies
    print("=== Injecting cookies ===")
    inject_cookies_to_context(context)
    
    page = context.new_page()
    
    # Navigate to OA
    print("=== Navigating to OA ===")
    page.goto("https://oa.bangcle.com", timeout=30000, wait_until="networkidle")
    time.sleep(3)
    print(f"OA URL: {page.url[:100]}")
    print(f"OA Title: {page.title()}")
    
    # Navigate to contract ledger via menu
    print("=== Navigating to contract ledger ===")
    menu_path = ["门户", "销售合同管理系统", "合同基本信息管理", "合同台账"]
    for label in menu_path:
        item = page.locator(f"text={label}").first
        if item.count() > 0:
            item.click()
            print(f"  Clicked: {label}")
            time.sleep(2)
        else:
            item = page.locator(".ant-menu-item, .ant-menu-submenu-title").filter(has_text=label).first
            if item.count() > 0:
                item.click()
                print(f"  Clicked (fuzzy): {label}")
                time.sleep(2)
            else:
                print(f"  NOT FOUND: {label}")
                all_text = page.locator(".ant-menu").text_content()
                print(f"  Menu text: {all_text[:200]}")
                browser.close()
                sys.exit(1)
    
    # Wait for table
    print("=== Waiting for table ===")
    page.wait_for_selector(".ant-table", timeout=15000)
    print("Table loaded!")
    
    # Click export button
    print("=== Triggering export ===")
    export_btn = page.locator("button:has-text('导出')").first
    if export_btn.count() > 0:
        export_btn.click()
        print("Export triggered!")
    else:
        print("Export button not found")
        browser.close()
        sys.exit(1)
    
    # Wait for progress modal
    print("=== Waiting for progress modal ===")
    page.wait_for_selector(".ant-modal", timeout=10000)
    print("Progress modal appeared")
    
    # Poll for completion
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
        dl = page.locator("a:has-text('下载'), a[href*='download']").first
        if dl.count() > 0:
            print("  Download link found!")
            break
    
    # Download
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
print("=== Done ===")
