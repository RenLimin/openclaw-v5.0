#!/usr/bin/env python3
"""ONES 202609 数据导出 - 独立脚本，不影响其他 Chrome 进程。

启动方式：
  python3 ones_export_202609.py

退出码：
  0 = 全部成功
  1 = 部分失败
"""
import os
import sys
import time
import shutil
import socket
import subprocess
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CDP_PORT = 9229  # 用不同端口，避免和 OA 导出的 9222 冲突
USER_DIR = "/Users/bangcle/.chrome-ones-profile"
OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "raw" / "202609"
DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"

FILTERS = [
    {"name": "sign", "tab": 7, "file": "ones_sign_202609.csv"},
    {"name": "poc", "tab": 8, "file": "ones_poc_202609.csv"},
    {"name": "abnormal", "tab": 10, "file": "ones_abnormal_202609.csv"},
]

IAM_USER = "limin.ren"
IAM_PASS = "REDACTED_SECRET"

# ── 工具函数 ──────────────────────────────────────────

def log(msg):
    print(msg, flush=True)

def wait_cdp(port, timeout=30):
    """等待 CDP 端口就绪"""
    for _ in range(timeout):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except:
            time.sleep(1)
    return False

def start_chrome():
    """启动专用 Chrome CDP 实例"""
    # 清理旧 profile
    if Path(USER_DIR).exists():
        shutil.rmtree(USER_DIR)
    os.makedirs(USER_DIR, exist_ok=True)

    proc = subprocess.Popen(
        [CHROME,
         f"--remote-debugging-port={CDP_PORT}",
         f"--user-data-dir={USER_DIR}",
         "--no-first-run",
         "--disable-extensions",
         "--disable-sync",
         "--disable-background-networking",
         "--disable-gpu"],
        stdout=open("/tmp/chrome_ones.log", "w"),
        stderr=subprocess.STDOUT,
    )
    log(f"  Chrome PID: {proc.pid}")

    if not wait_cdp(CDP_PORT):
        raise RuntimeError(f"Chrome CDP 启动失败，端口 {CDP_PORT}")

    log(f"  CDP ready on port {CDP_PORT}")
    return proc

def login_iam_via_cdp(browser):
    """通过已有 CDP 浏览器登录 IAM（不启动新浏览器）"""
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()

    log("  导航到 IAM 登录页...")
    page.goto("https://iam.bangcle.com/#/login", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)

    log("  填写凭据...")
    page.locator("input[type=text]").first.fill(IAM_USER)
    page.locator("input[type=password]").first.fill(IAM_PASS)
    page.locator("button").nth(1).click()

    page.wait_for_url("**/home/**", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(3)

    log(f"  ✅ 登录成功: {page.title()}")

    # 保存 cookies 到所有域名
    all_cookies = ctx.cookies()
    log(f"  获取 {len(all_cookies)} cookies")

    # 注入 cookies 到 .bangcle.com 域名
    for c in all_cookies:
        for domain in ["iam.bangcle.com", "ones.bangcle.com", "oa.bangcle.com",
                       ".bangcle.com", "bangcle.com"]:
            try:
                ctx.add_cookies([{
                    "name": c["name"],
                    "value": c["value"],
                    "domain": domain,
                    "path": "/",
                }])
            except:
                pass

    return ctx, page

def navigate_to_ones(ctx):
    """导航到 ONES 项目页面"""
    page = ctx.new_page()
    log("  导航到 ONES...")
    page.goto("https://ones.bangcle.com/project/#/workspace/home", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(5)
    log(f"  ONES 已加载: {page.title()}")
    return page

def click_filter_tab(page, tab_index):
    """点击筛选器子 tab"""
    log(f"  点击筛选 tab {tab_index}...")
    result = page.evaluate("""(function(idx) {
        var tabs = document.querySelectorAll('.url-foldable-tabs-new-link');
        if (tabs.length > idx) {
            tabs[idx].click();
            return 'clicked ' + idx;
        }
        return 'not found, count=' + tabs.length;
    })($IDX$)""".replace("$IDX$", str(tab_index)))
    log(f"  Tab 结果: {result}")
    time.sleep(5)

def click_reset(page):
    """点击还原按钮"""
    log("  点击还原按钮...")
    result = page.evaluate("""(function() {
        var buttons = document.querySelectorAll('button, a');
        for (var i = 0; i < buttons.length; i++) {
            var text = (buttons[i].innerText || '').trim().toLowerCase();
            if (text.indexOf('还原') >= 0 || text.indexOf('重置') >= 0) {
                buttons[i].click();
                return 'clicked: ' + text;
            }
        }
        return 'not found';
    })()""")
    log(f"  还原结果: {result}")
    time.sleep(10)  # 等待数据重新加载

def click_export(page):
    """点击更多菜单 → 导出工作项"""
    log("  点击更多菜单...")
    result = page.evaluate("""(function() {
        var icon = document.querySelector('.more-menu-icon');
        if (icon) { icon.click(); return 'clicked'; }
        return 'not found';
    })()""")
    log(f"  更多菜单: {result}")
    time.sleep(2)

    log("  点击导出工作项...")
    result = page.evaluate("""(function() {
        var items = document.querySelectorAll('.ones-dropdown-menu-item-content');
        for (var i = 0; i < items.length; i++) {
            var text = items[i].innerText || '';
            if (text.indexOf('导出') >= 0 && text.indexOf('工作项') >= 0) {
                items[i].click();
                return 'clicked: ' + text;
            }
        }
        return 'not found';
    })()""")
    log(f"  导出工作项: {result}")
    time.sleep(3)

def click_confirm_and_download(page, timeout=600):
    """点击确认并等待下载"""
    log("  等待下载...")
    with page.expect_download(timeout=timeout * 1000) as download_info:
        # 点击确认按钮
        page.evaluate("""(function() {
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {
                var text = (buttons[i].innerText || '').trim();
                if (text === '确定' || text === '确认') {
                    buttons[i].click();
                    return 'clicked: ' + text;
                }
            }
            return 'not found';
        })()""")

    download = download_info.value
    return download

def export_filter(browser, filter_config, output_dir):
    """导出单个筛选器"""
    name = filter_config["name"]
    tab = filter_config["tab"]
    output_file = filter_config["file"]

    log(f"\n{'='*50}")
    log(f"导出: {name}")
    log(f"{'='*50}")

    ctx = browser.contexts[0]

    # 导航到 ONES
    page = navigate_to_ones(ctx)

    # 点击筛选 tab
    click_filter_tab(page, tab)

    # 点击还原
    click_reset(page)

    # 点击导出
    click_export(page)

    # 确认并下载
    download = click_confirm_and_download(page)

    # 保存文件
    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / output_file
    dest.unlink(missing_ok=True)
    download.save_as(dest)

    size_mb = dest.stat().st_size / 1024 / 1024
    lines = sum(1 for _ in open(dest, encoding="utf-8-sig"))
    log(f"  ✅ 保存: {output_file} ({size_mb:.2f} MB, {lines} 行)")

    return dest

def main():
    log("="*60)
    log("ONES 202609 数据导出")
    log("="*60)

    # Step 1: 启动 Chrome
    log("\n[1/4] 启动 Chrome CDP...")
    chrome_proc = start_chrome()

    try:
        # Step 2: 连接 Playwright
        log("\n[2/4] 连接 Playwright...")
        from playwright.sync_api import sync_playwright
        playwright = sync_playwright().start()
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
        log(f"  已连接, {len(browser.contexts)} contexts")

        # Step 3: 登录 IAM
        log("\n[3/4] 登录 IAM...")
        ctx, page = login_iam_via_cdp(browser)

        # Step 4: 导出所有筛选器
        log("\n[4/4] 导出 ONES 数据...")
        results = {}
        for f in FILTERS:
            try:
                dest = export_filter(browser, f, OUTPUT_DIR)
                results[f["name"]] = dest
            except Exception as e:
                log(f"  ❌ {f['name']} 失败: {e}")
                import traceback
                traceback.print_exc()
                results[f["name"]] = None

        # 汇总
        log("\n" + "="*60)
        log("导出结果汇总")
        log("="*60)
        all_ok = True
        for f in FILTERS:
            name = f["name"]
            dest = results.get(name)
            if dest and dest.exists():
                size_mb = dest.stat().st_size / 1024 / 1024
                lines = sum(1 for _ in open(dest, encoding="utf-8-sig"))
                log(f"  ✅ {name}: {f['file']} ({size_mb:.2f} MB, {lines} 行)")
            else:
                log(f"  ❌ {name}: 失败")
                all_ok = False

        # 关闭 Playwright，但不杀 Chrome（保持可复用）
        browser.close()
        playwright.stop()
        log("\n✅ 导出完成（Chrome 保持运行，端口 {}）".format(CDP_PORT))
        sys.exit(0 if all_ok else 1)

    except Exception as e:
        log(f"\n❌ 致命错误: {e}")
        import traceback
        traceback.print_exc()
        # 清理 Chrome
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=10)
        except:
            chrome_proc.kill()
        sys.exit(1)

if __name__ == "__main__":
    main()
