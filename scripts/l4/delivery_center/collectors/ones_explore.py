#!/usr/bin/env python3
"""ONES 页面结构探索脚本

分步执行 ONES 操作，每步输出页面 DOM 结构信息。
用于精确定位元素选择器，供 ones_collector.py 使用。

用法：
  python3 ones_explore.py

输出：
  每步的元素列表（tab、按钮、导航项、导出按钮等）
"""

import json, time, signal, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path('/Users/bangcle/.openclaw/data/ones_exports')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
AUTH_FILE = Path.home() / '.openclaw' / 'data' / 'oa_exports' / 'ones_auth.json'

def handler(signum, frame):
    print('\n[TIMEOUT]')
    sys.exit(1)
signal.signal(signal.SIGALRM, handler)
signal.alarm(180)

def load_cookies():
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text(encoding='utf-8'))
        return data.get('cookies', [])
    return []

def explore(page, label):
    """探索当前页面结构"""
    info = page.evaluate('''() => {
        const result = {label: "''' + label + '''"};
        
        // 1. 所有 tab 元素
        const tabSelectors = [
            '[role="tab"]', '.ant-tabs-tab', '.el-tabs__item',
            '[class*="tab-item"]', '[class*="tabItem"]',
            'li[class*="tab"]', 'div[class*="tab"]'
        ];
        result.tabs = [];
        for (const sel of tabSelectors) {
            document.querySelectorAll(sel).forEach(el => {
                result.tabs.push({
                    sel: sel,
                    tag: el.tagName,
                    text: el.textContent.trim().substring(0, 40),
                    cls: (el.className || '').substring(0, 60),
                    active: el.className && (el.className.includes('active') || el.className.includes('current')),
                });
            });
        }
        
        // 2. 所有按钮
        result.buttons = [];
        document.querySelectorAll('button, .ant-btn, .el-btn, [class*="btn"]').forEach(el => {
            const text = el.textContent.trim();
            if (text && text.length < 30) {
                result.buttons.push({
                    tag: el.tagName,
                    text: text,
                    cls: (el.className || '').substring(0, 60),
                    visible: el.offsetParent !== null,
                });
            }
        });
        
        // 3. 左侧导航
        result.nav = [];
        document.querySelectorAll('.ant-menu-item, .el-menu-item, [class*="nav"] a, [class*="sidebar"] a, [class*="menu"] a, nav a, aside a').forEach(el => {
            const text = el.textContent.trim();
            if (text && text.length < 30) {
                result.nav.push({
                    text: text,
                    href: el.href || '',
                    cls: (el.className || '').substring(0, 50),
                    active: el.className && (el.className.includes('active') || el.className.includes('selected') || el.className.includes('current')),
                });
            }
        });
        
        // 4. 包含"导出"的元素
        result.exports = [];
        document.querySelectorAll('*').forEach(el => {
            const t = el.textContent.trim();
            if ((t === '导出' || t === '导出原始数据' || t.includes('导出')) && el.children.length < 3 && t.length < 20) {
                result.exports.push({
                    tag: el.tagName,
                    text: t,
                    cls: (el.className || '').substring(0, 60),
                    visible: el.offsetParent !== null,
                });
            }
        });
        
        // 5. 包含"筛选器"的元素
        result.filters = [];
        document.querySelectorAll('*').forEach(el => {
            const t = el.textContent.trim();
            if (t.includes('筛选器') && el.children.length < 5 && t.length < 30) {
                result.filters.push({
                    tag: el.tagName,
                    text: t,
                    cls: (el.className || '').substring(0, 60),
                });
            }
        });
        
        // 6. 包含"工作台"的元素
        result.workspaces = [];
        document.querySelectorAll('*').forEach(el => {
            const t = el.textContent.trim();
            if (t.includes('工作台') && el.children.length < 5 && t.length < 20) {
                result.workspaces.push({
                    tag: el.tagName,
                    text: t,
                    cls: (el.className || '').substring(0, 60),
                });
            }
        });
        
        // 7. 表格信息
        result.tables = document.querySelectorAll('table').length;
        result.tableRows = document.querySelectorAll('table tbody tr, tr').length;
        
        return result;
    }''')
    
    print(f'\n=== {label} ===')
    print(f'  URL: {page.url[:80]}')
    print(f'  Tabs ({len(info.get("tabs", []))}):')
    for t in info.get('tabs', [])[:15]:
        active = ' ← ACTIVE' if t.get('active') else ''
        print(f'    [{t["tag"]}] "{t["text"]}" cls={t["cls"][:40]}{active}')
    print(f'  Buttons ({len(info.get("buttons", []))}):')
    for b in info.get('buttons', [])[:15]:
        print(f'    [{b["tag"]}] "{b["text"]}" cls={b["cls"][:40]} visible={b["visible"]}')
    print(f'  Nav ({len(info.get("nav", []))}):')
    for n in info.get('nav', [])[:15]:
        active = ' ← ACTIVE' if n.get('active') else ''
        print(f'    "{n["text"]}" href={n["href"][:50]} cls={n["cls"][:30]}{active}')
    print(f'  Export ({len(info.get("exports", []))}):')
    for e in info.get('exports', [])[:10]:
        print(f'    [{e["tag"]}] "{e["text"]}" cls={e["cls"][:40]} visible={e["visible"]}')
    print(f'  Filter ({len(info.get("filters", []))}):')
    for f in info.get('filters', [])[:10]:
        print(f'    [{f["tag"]}] "{f["text"]}" cls={f["cls"][:40]}')
    print(f'  Workspace ({len(info.get("workspaces", []))}):')
    for w in info.get('workspaces', [])[:10]:
        print(f'    [{w["tag"]}] "{w["text"]}" cls={w["cls"][:40]}')
    print(f'  Tables: {info.get("tables")}, Rows: {info.get("tableRows")}')
    
    return info

print('=' * 60)
print(' ONES 页面结构探索')
print('=' * 60)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
    context = browser.new_context(accept_downloads=True, viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    
    try:
        # Step 1: Cookie 注入 + 访问 ONES
        print('\n[Step 1] Cookie 注入...')
        cookies = load_cookies()
        for c in cookies:
            try:
                context.add_cookies([{
                    'name': c['name'], 'value': c['value'],
                    'domain': c.get('domain', '.ones.bangcle.com'),
                    'path': c.get('path', '/'),
                }])
            except: pass
        
        page.goto('https://ones.bangcle.com/project/#/home/project', timeout=20000)
        time.sleep(8)
        
        # 探索初始页面
        explore(page, "初始页面（项目列表）")
        
        # Step 2: 点击"我的工作台"
        print('\n[Step 2] 点击 我的工作台...')
        ws = page.locator('a, span, div, li').filter(has_text='我的工作台').first
        if ws.count() > 0:
            ws.click()
            time.sleep(5)
            explore(page, "我的工作台")
        else:
            print('  未找到 我的工作台')
        
        # Step 3: 点击"筛选器" tab
        print('\n[Step 3] 点击 筛选器 tab...')
        ft = page.locator('[role=tab], a, span, div, li').filter(has_text='筛选器').first
        if ft.count() > 0:
            ft.click()
            time.sleep(5)
            explore(page, "筛选器 tab")
        else:
            print('  未找到 筛选器 tab')
        
        # Step 4: 点击"2026周报-签约项目"
        print('\n[Step 4] 点击 2026周报-签约项目...')
        sub = page.locator('[role=tab], a, span, div, li').filter(has_text='2026周报-签约项目').first
        if sub.count() > 0:
            sub.click()
            time.sleep(5)
            explore(page, "2026周报-签约项目")
        else:
            # 尝试部分匹配
            sub = page.locator('a, span, div, li').filter(has_text='签约项目').first
            if sub.count() > 0:
                sub.click()
                time.sleep(5)
                explore(page, "签约项目（部分匹配）")
            else:
                print('  未找到 2026周报-签约项目')
        
        # Step 5: 查找导出按钮
        print('\n[Step 5] 查找导出按钮...')
        export = page.locator('button, a, span, div').filter(has_text='导出原始数据').first
        if export.count() > 0:
            print(f'  找到导出按钮: {export.text_content()[:30]}')
            # 不点击，只记录信息
        else:
            export = page.locator('button, a, span, div').filter(has_text='导出').first
            if export.count() > 0:
                print(f'  找到导出按钮: {export.text_content()[:30]}')
            else:
                print('  未找到导出按钮')
        
    except Exception as e:
        print(f'ERROR: {e}')
        import traceback
        traceback.print_exc()
    finally:
        browser.close()

print('\n[DONE]')
