#!/usr/bin/env python3
"""诊断：ONES 筛选器列表页结构 — 定位「2026周报-签约项目统计」链接。

登录成功进入工作台后：
1. 点击「筛选器」菜单项
2. dump 页面结构，找「签约项目统计」链接
3. 确认筛选器链接的 href/class，供 ones_click_filter_tab 使用
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

from bdms.modules.integration.adapters.browser_adapter import BrowserAdapter

print("=== 诊断 ONES 筛选器列表页 ===")
adapter = BrowserAdapter(headless=False)
try:
    print("[1] 启动浏览器 + 自动登录...")
    adapter.launch()
    ok = adapter.ones_ensure_tab()
    print(f"    ensure_tab = {ok}")
    if not ok:
        sys.exit(1)
    time.sleep(5)

    page = adapter._page

    # 找到「筛选器」菜单项并点击
    print("[2] 点击「筛选器」菜单...")
    clicked = page.evaluate("""
        (function() {
            var links = document.querySelectorAll('a, [class*=menu-item], [class*=nav-item]');
            for (var i = 0; i < links.length; i++) {
                var t = (links[i].innerText || '').trim();
                if (t === '筛选器') {
                    links[i].click();
                    return 'clicked: ' + links[i].tagName + ' ' + links[i].className;
                }
            }
            return 'not found, count=' + links.length;
        })()
    """)
    print(f"    点击结果: {clicked}")
    time.sleep(8)

    url = page.url
    print(f"[3] 当前 URL: {url[:80]}")
    print(f"    title: {page.title()}")

    # dump 所有 a 标签文本，找筛选器相关
    print("\n[4] 页面 a 标签（含 href）:")
    links = page.evaluate("""
        Array.from(document.querySelectorAll('a')).map(function(a){
            return {text:(a.innerText||'').trim().slice(0,40), href:(a.getAttribute('href')||'').slice(0,80)};
        }).filter(function(x){return x.text || x.href;})
    """)
    for i, l in enumerate(links[:40]):
        print(f"    [{i}] text={l['text']!r} href={l['href']}")

    # 找签约项目统计
    print("\n[5] 搜索「签约项目统计」链接:")
    sig = [l for l in links if '签约' in l['text'] or 'POC' in l['text'] or '异常' in l['text']]
    for l in sig:
        print(f"    MATCH: text={l['text']!r} href={l['href']}")
    if not sig:
        print("    未找到，dump 前 10 个完整链接")

finally:
    adapter.close()
    print("[done]")
