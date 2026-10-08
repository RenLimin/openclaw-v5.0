"""Playwright-based OA export script.

Uses connectOverCDP to reuse existing Chrome session (login state preserved).
Chrome must be started with --remote-debugging-port=9222.
"""
import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


def wait_for_export_complete(page, timeout=600):
    """Wait for OA async export progress dialog to reach 100%."""
    print("Waiting for OA export progress...")
    start = time.time()
    while time.time() - start < timeout:
        # Check progress text in modal
        progress = page.locator(".ant-modal-body, .ant-modal-content").all()
        for p in progress:
            text = p.text_content()
            if "导出进度" in text or "当前进度" in text:
                # Extract percentage
                import re
                m = re.search(r'(\d+)/(\d+)', text)
                if m:
                    cur, total = int(m.group(1)), int(m.group(2))
                    pct = cur / total * 100 if total > 0 else 0
                    print(f"  Progress: {cur}/{total} ({pct:.1f}%)")
                    if cur >= total:
                        return True
        # Check if download link appeared
        links = page.locator("a:has-text('下载'), a[href*='download']").all()
        if links:
            print("  Download link found!")
            return True
        time.sleep(3)
    return False


def main():
    downloads_dir = Path.home() / "Downloads"
    
    with sync_playwright() as p:
        # Connect to existing Chrome via CDP
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        except Exception as e:
            print(f"Cannot connect to Chrome CDP: {e}")
            print("Please start Chrome with: --remote-debugging-port=9222")
            sys.exit(1)
        
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        
        # Navigate to OA if not already there
        if "oa.bangcle.com" not in page.url:
            print("Navigating to OA...")
            page.goto("https://oa.bangcle.com", wait_until="networkidle", timeout=30000)
        
        # Navigate to contract ledger via menu clicks
        print("Navigating to contract ledger...")
        menu_path = ["门户", "销售合同管理系统", "合同基本信息管理", "合同台账"]
        for label in menu_path:
            # Find menu item by text
            item = page.locator(f"text={label}").first
            if item.count() > 0:
                item.click()
                time.sleep(2)
            else:
                # Fuzzy match
                item = page.locator(f"text=/{label}/").first
                if item.count() > 0:
                    item.click()
                    time.sleep(2)
                else:
                    print(f"  Menu item '{label}' not found!")
        
        # Wait for table to load
        page.wait_for_selector(".ant-table", timeout=15000)
        print("Table loaded")
        
        # Click export button
        print("Clicking export button...")
        export_btn = page.locator("button:has-text('导出')").first
        if export_btn.count() == 0:
            export_btn = page.locator("button:has-text('Export')").first
        
        if export_btn.count() > 0:
            export_btn.click()
            print("Export triggered")
        else:
            print("Export button not found!")
            sys.exit(1)
        
        # Wait for progress dialog
        page.wait_for_selector(".ant-modal", timeout=10000)
        
        # Wait for completion
        if wait_for_export_complete(page, timeout=600):
            print("Export complete!")
            
            # Click download link in dialog
            dl_link = page.locator("a:has-text('下载'), a[href*='download']").first
            if dl_link.count() > 0:
                print("Clicking download link...")
                
                # Set up download handler
                with page.expect_download(timeout=120000) as download_info:
                    dl_link.click()
                download = download_info.value
                
                # Save file
                save_path = downloads_dir / download.suggested_filename
                download.save_as(str(save_path))
                print(f"Saved to: {save_path} ({save_path.stat().st_size} bytes)")
            else:
                print("No download link found. Checking Downloads folder...")
                # Check for new files
                time.sleep(5)
                files = sorted(downloads_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
                if files:
                    print(f"Latest CSV: {files[0]}")
                else:
                    print("No CSV files found!")
        else:
            print("Export timed out!")


if __name__ == "__main__":
    main()
