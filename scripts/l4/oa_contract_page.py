#!/usr/bin/env python3
"""
OA - Access the contract ledger page directly
URL: /formmode/search/CustomSearchBySimple.jsp?customid=179
"""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

COOKIE_FILE = Path.home() / ".openclaw" / "data" / "iam_cookies.json"

print("=== OA Contract Page ===")

api_requests = []
api_responses = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    def on_request(req):
        url = req.url
        if "oa.bangcle.com" in url and not any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico"]):
            api_requests.append({
                "url": url,
                "method": req.method,
                "headers": {k: v for k, v in req.headers.items()},
                "post_data": req.post_data,
            })

    def on_response(resp):
        url = resp.url
        if "oa.bangcle.com" in url and "/api/" in url:
            try:
                body = resp.json()
                api_responses.append({"url": url, "status": resp.status, "body": body})
            except:
                pass

    page.on("request", on_request)
    page.on("response", on_response)

    # Login IAM -> OA portal
    page.goto("https://iam.bangcle.com/#/login", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    page.locator("input[type=text]").first.fill("limin.ren")
    page.locator("input[type=password]").first.fill("June-123")
    for btn in page.locator("button").all():
        if "登录" in (btn.text_content() or ""):
            btn.click()
            break
    page.wait_for_url("**/home/**", timeout=15000)
    time.sleep(3)

    # Click OA entry
    oa_el = page.get_by_text("OA协同办公平台", exact=False)
    oa_el.first.click()
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(5)
    
    pages = context.pages
    if len(pages) > 1:
        page = pages[-1]

    # Navigate directly to the contract ledger page
    print("[1] Navigate to contract ledger page...")
    page.goto("https://oa.bangcle.com/formmode/search/CustomSearchBySimple.jsp?customid=179", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(10)
    
    url = page.url
    body = page.text_content("body") or ""
    print(f"  URL: {url}")
    print(f"  Text length: {len(body)}")
    print(f"  First 2000: {body[:2000]}")
    
    # Check iframe
    iframes = page.locator("iframe").all()
    print(f"\n  Iframes: {len(iframes)}")
    for i, iframe in enumerate(iframes):
        src = iframe.get_attribute("src") or ""
        print(f"    iframe[{i}]: {src[:200]}")
        
        if src and src != "about:blank":
            try:
                frame = iframe.content_frame()
                if frame:
                    frame_body = frame.text_content("body") or ""
                    print(f"    Frame body: {len(frame_body)} chars")
                    print(f"    Frame text: {frame_body[:1000]}")
            except:
                pass
    
    # Check for export/download buttons
    print("\n[2] Check for export buttons...")
    buttons = page.locator("button, a").all()
    for btn in buttons:
        text = (btn.text_content() or "").strip()
        if "导出" in text or "下载" in text or "export" in text.lower() or "download" in text.lower():
            print(f"  Export: {text}")
    
    # Print API requests
    print(f"\n[3] API requests: {len(api_requests)}")
    for req in api_requests[:20]:
        print(f"  {req['method']} {req['url'][:120]}")
        if req["post_data"]:
            print(f"    POST: {req['post_data'][:300]}")

    print(f"\n[4] API responses: {len(api_responses)}")
    for resp in api_responses[:10]:
        print(f"  [{resp['status']}] {resp['url'][:120]}")
        body_str = json.dumps(resp["body"], ensure_ascii=False)[:200]
        print(f"    Body: {body_str}")

    # Screenshot
    page.screenshot(path="/tmp/oa_contract_page.png", full_page=True)
    print(f"\n[Screenshot: /tmp/oa_contract_page.png]")

    # Save cookies
    all_cookies = context.cookies()
    cookie_pairs = [f"{c['name']}={c['value']}" for c in all_cookies]
    cookie_str = "; ".join(cookie_pairs)
    cookies_data = {
        "iam.bangcle.com": {"cookie": cookie_str, "timestamp": time.time()},
        "ones.bangcle.com": {"cookie": cookie_str, "timestamp": time.time()},
        "oa.bangcle.com": {"cookie": cookie_str, "timestamp": time.time()},
    }
    COOKIE_FILE.write_text(json.dumps(cookies_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Cookie saved: {len(cookie_str)} chars]")

    browser.close()

print("\n=== Done ===")
