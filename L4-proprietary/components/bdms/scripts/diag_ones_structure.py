#!/usr/bin/env python3
"""探索：ONES 项目空间/筛选器页面结构，定位筛选器导航路径。

目标：找到「2026周报-签约项目统计」等筛选器所在页面的 URL 结构。
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

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from bdms.modules.integration.adapters.browser_adapter import BrowserAdapter, ONES_BASE

print("=== 探索 ONES 项目空间/筛选器结构 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器...")
    adapter.launch()
    page = adapter._page

    print("[2] 访问 ONES 工作台...")
    page.goto(ONES_BASE + "/project/#/workspace/home", timeout=60000, wait_until="domcontentloaded")
    time.sleep(8)

    url = page.url
    print(f"[3] URL: {url}")
    print(f"    title: {page.title()}")
    pwd = page.locator("input[type=password]").count()
    print(f"    密码框: {pwd}")
    if pwd > 0:
        print("[!] 未登录，SSO 未完成，退出")
        sys.exit(1)

    # dump 页面上的项目链接（左侧项目列表）
    print("\n[4] 工作台左侧导航链接（前 30 个 a 标签）:")
    links = page.evaluate("""
        Array.from(document.querySelectorAll('a')).slice(0, 30).map(function(a){
            return {text:(a.innerText||'').trim().slice(0,40), href:a.getAttribute('href')||''};
        })
    """)
    for i, l in enumerate(links):
        if l['text'] or l['href']:
            print(f"    [{i}] text={l['text']!r} href={l['href']}")

    # 找所有含 workspace/team/project 的 URL
    print("\n[5] 尝试常见项目空间 URL...")
    candidates = [
        ONES_BASE + "/project/#/workspace/home",
        ONES_BASE + "/project/#/workspace/project/list",
        ONES_BASE + "/project/#/project",
        ONES_BASE + "/project/#/team/RZxvwUZ8",
        ONES_BASE + "/project/#/team/RZxvwUZ8/home",
    ]
    for cand in candidates:
        page.goto(cand, timeout=30000, wait_until="domcontentloaded")
        time.sleep(5)
        links2 = page.evaluate("""
            Array.from(document.querySelectorAll('a')).slice(0, 25).map(function(a){
                return (a.innerText||'').trim().slice(0,40);
            }).filter(Boolean)
        """)
        tabs = page.evaluate("document.querySelectorAll('.url-foldable-tabs-new-link').length")
        print(f"  {cand}")
        print(f"    -> url={page.url[:70]} | a_count={len(links2)} | filter_tabs={tabs}")
        # 找含 筛选器 相关文本
        filter_links = [t for t in links2 if any(k in t for k in ['签约','POC','筛选','统计','异常'])]
        if filter_links:
            print(f"    -> 筛选器链接: {filter_links}")
            break

finally:
    adapter.close()
    print("[done]")
