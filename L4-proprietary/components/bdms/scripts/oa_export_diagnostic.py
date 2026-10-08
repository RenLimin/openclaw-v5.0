"""Diagnostic script to understand OA export flow."""
import subprocess
import time
import json
from pathlib import Path


def run_js(js_code):
    """Execute JS in OA tab via osascript."""
    safe = js_code.replace('\n', ' ').replace('\r', '').strip().replace('"', '\\"')
    cmd = [
        "osascript", "-e",
        f'tell application "Google Chrome" to execute '
        f'(first tab of first window whose URL contains "oa.bangcle.com") '
        f'javascript "{safe}"'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip()[:200]}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "TIMEOUT"


def main():
    downloads_dir = Path.home() / "Downloads"
    
    # Check current URL
    url_js = "window.location.href"
    url = run_js(url_js)
    print(f"Current URL: {url}")
    
    # Navigate to contract ledger
    print("\nNavigating to contract ledger...")
    menu_path = ["门户", "销售合同管理系统", "合同基本信息管理", "合同台账"]
    for label in menu_path:
        js = (
            f"var found = false;"
            f"document.querySelectorAll('.ant-menu-item, .ant-menu-submenu-title, a[role=menuitem]').forEach(el => {{"
            f"  if (el.textContent.trim().indexOf('{label}') !== -1 && !found) {{ el.click(); found = true; }}"
            f"}});"
            f"found;"
        )
        res = run_js(js)
        print(f"  Click '{label}': {res}")
        time.sleep(2)
    
    # Wait for table
    time.sleep(3)
    
    # Check for export button
    print("\nLooking for export button...")
    btn_js = (
        "var buttons = [];"
        "document.querySelectorAll('button, a').forEach((b, i) => {"
        "  var t = b.textContent.trim();"
        "  if (t.indexOf('导出') !== -1) buttons.push({i: i, t: t, tag: b.tagName});"
        "});"
        "JSON.stringify(buttons);"
    )
    btns = run_js(btn_js)
    print(f"Export buttons: {btns}")
    
    # Click first export button
    click_js = (
        "var found = false;"
        "document.querySelectorAll('button, a').forEach((b) => {"
        "  if (b.textContent.trim().indexOf('导出') !== -1 && !found) { b.click(); found = true; }"
        "});"
        "found;"
    )
    res = run_js(click_js)
    print(f"Clicked export: {res}")
    
    # Poll page state every 10 seconds
    print("\nPolling page state for export progress...")
    initial_csv = set(downloads_dir.glob("*.csv"))
    
    for i in range(30):  # 5 minutes max
        time.sleep(10)
        
        # Check for modal/progress
        modal_js = (
            "var modals = document.querySelectorAll('.ant-modal-body, .ant-modal-content, .ant-modal-wrap');"
            "var texts = [];"
            "modals.forEach(m => { if (m.textContent.trim()) texts.push(m.textContent.trim().substring(0, 100)); });"
            "JSON.stringify(texts);"
        )
        modal_text = run_js(modal_js)
        
        # Check for download links
        dl_js = (
            "var links = [];"
            "document.querySelectorAll('a').forEach(a => {"
            "  var t = a.textContent.trim();"
            "  if (t.indexOf('下载') !== -1 || (a.href && a.href.indexOf('download') !== -1)) links.push({t: t, href: a.href.substring(0, 100)});"
            "});"
            "JSON.stringify(links);"
        )
        dl_links = run_js(dl_js)
        
        # Check Downloads
        current_csv = set(downloads_dir.glob("*.csv"))
        new_files = current_csv - initial_csv
        
        print(f"\n[{(i+1)*10}s] Modal: {modal_text[:100] if modal_text else 'none'}")
        print(f"  Download links: {dl_links[:100] if dl_links else 'none'}")
        print(f"  New CSV files: {[f.name for f in new_files]}")
        
        # If we found a download link, try clicking it
        if dl_links and dl_links != "[]" and dl_links != "missing value":
            print("\nFound download link! Clicking...")
            click_dl_js = (
                "var found = false;"
                "document.querySelectorAll('a').forEach(a => {"
                "  var t = a.textContent.trim();"
                "  if ((t.indexOf('下载') !== -1 || (a.href && a.href.indexOf('download') !== -1)) && !found) { a.click(); found = true; }"
                "});"
                "found;"
            )
            run_js(click_dl_js)
            time.sleep(10)
            
            # Check downloads again
            current_csv = set(downloads_dir.glob("*.csv"))
            new_files = current_csv - initial_csv
            if new_files:
                for f in new_files:
                    print(f"Downloaded: {f.name} ({f.stat().st_size} bytes)")
                return
        
        # If modal is gone, progress might be done
        if modal_text == "[]" or modal_text == "missing value":
            print("\nModal disappeared. Export might be complete.")
            
            # Check for download button
            dl_btn_js = (
                "var found = false;"
                "document.querySelectorAll('button, a').forEach(b => {"
                "  if (b.textContent.trim().indexOf('下载') !== -1) found = true;"
                "});"
                "found;"
            )
            if run_js(dl_btn_js) == "true":
                print("Download button found! Clicking...")
                click_dl_js = (
                    "var found = false;"
                    "document.querySelectorAll('button, a').forEach(b => {"
                    "  if (b.textContent.trim().indexOf('下载') !== -1 && !found) { b.click(); found = true; }"
                    "});"
                    "found;"
                )
                run_js(click_dl_js)
                time.sleep(10)


if __name__ == "__main__":
    main()
