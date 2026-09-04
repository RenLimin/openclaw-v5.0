#!/usr/bin/env python3
"""ONES 数据采集器 — osascript 自动化版

基于 00-02 成功经验固化为可复用脚本。
通过 osascript 执行 Chrome JavaScript 操作 ONES 筛选器 + 导出。

前置条件：
  1. Chrome 已打开 ONES 页面（https://ones.bangcle.com）
  2. Chrome 菜单「显示 → 开发者 → 允许 Apple 事件中的 JavaScript」已开启
  3. ONES 已登录（IAM SSO 或 cookie 有效）

关键经验（09-02）：
  - JS 必须纯英文（中文字符串 → missing value）
  - 用索引点击筛选器 tab（不能靠文本匹配）
  - 导出流程：more-menu-icon → dropdown-menu-item-label[10] → button[7]
  - ONES 导出无 1000 行限制

筛选器索引（左侧导航子 tab）：
  - 签约项目统计: 163-165
  - POC&提前实施统计: 166-168
  - 异常处置: 172-174
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

EXPORT_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# === 筛选器配置 ===
FILTERS = [
    {
        "name": "sign",
        "label": "签约项目统计",
        "tab_index": 163,  # 左侧导航 tab 的索引范围 163-165
        "output_csv": "签约项目统计.csv",
    },
    {
        "name": "poc",
        "label": "POC&提前实施统计",
        "tab_index": 166,  # 166-168
        "output_csv": "poc_提前实施.csv",
    },
    {
        "name": "abnormal",
        "label": "异常处置",
        "tab_index": 172,  # 172-174
        "output_csv": "异常处置.csv",
    },
]


def run_js(js_code: str, timeout: int = 30) -> str:
    """通过 osascript 在 Chrome 中执行 JavaScript（纯英文）"""
    # 转义单引号
    escaped = js_code.replace("'", "'\\''")
    cmd = [
        "osascript", "-e",
        f'tell application "Google Chrome" to execute front window\'s active tab JavaScript "{escaped}"'
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            print(f"  [osascript error] {result.stderr.strip()[:200]}")
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"  [timeout] osascript 执行超时 ({timeout}s)")
        return ""
    except Exception as e:
        print(f"  [error] {e}")
        return ""


def open_ones_page():
    """打开 ONES 页面（如果还没打开）"""
    print("[Step 0] 确保 Chrome 已打开 ONES...")
    # 检查 Chrome 是否运行
    check = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to (name of processes) contains "Google Chrome"'],
        capture_output=True, text=True, timeout=5
    )
    if "true" not in check.stdout.lower():
        print("  Chrome 未运行，启动中...")
        subprocess.run(["open", "-a", "Google Chrome", "https://ones.bangcle.com/project/#/home/project"])
        time.sleep(15)
    else:
        # 打开新标签
        subprocess.run(["open", "-a", "Google Chrome", "--args", "--new-tab", "https://ones.bangcle.com/project/#/home/project"])
        time.sleep(10)
    print("  ✅ ONES 页面已打开")


def click_filter_tab(tab_index: int) -> bool:
    """通过索引点击筛选器 tab"""
    print(f"  [导航] 点击筛选器 tab (index={tab_index})...")
    # 用索引定位 tab 元素（纯英文 JS）
    js = f"""
    (function() {{
        var tabs = document.querySelectorAll('[role="tab"], .tab-item, .ant-tabs-tab, [class*="tab"]');
        if (tabs.length > {tab_index}) {{
            tabs[{tab_index}].click();
            return 'clicked index {tab_index}';
        }}
        // Fallback: query all clickable elements with text
        var allElements = document.querySelectorAll('a, span, div, li');
        var count = 0;
        for (var i = 0; i < allElements.length; i++) {{
            if (allElements[i].offsetParent !== null) {{
                if (count === {tab_index}) {{
                    allElements[i].click();
                    return 'clicked fallback {tab_index}';
                }}
                count++;
            }}
        }}
        return 'not found';
    }})()
    """
    result = run_js(js, timeout=10)
    print(f"    结果: {result}")
    time.sleep(5)
    return "clicked" in result.lower()


def click_more_menu() -> bool:
    """点击更多菜单图标"""
    print("  [导出] 点击更多菜单...")
    js = """
    (function() {
        var menu = document.querySelector('[class*="more-menu-icon"]');
        if (!menu) {
            // Fallback: find by class containing 'more'
            var all = document.querySelectorAll('[class*="more"]');
            for (var i = 0; i < all.length; i++) {
                if (all[i].querySelector('svg, i, span') || all[i].textContent.length < 5) {
                    all[i].click();
                    return 'clicked more (fallback)';
                }
            }
            return 'more menu not found';
        }
        menu.click();
        return 'clicked more menu';
    })()
    """
    result = run_js(js, timeout=10)
    print(f"    结果: {result}")
    time.sleep(2)
    return "clicked" in result.lower()


def click_export_item() -> bool:
    """点击导出工作项（dropdown-menu-item-label[10]）"""
    print("  [导出] 点击导出工作项...")
    js = """
    (function() {
        var items = document.querySelectorAll('[class*="dropdown-menu-item-label"]');
        if (items.length > 10) {
            items[10].click();
            return 'clicked export item 10';
        }
        // Fallback: find by index
        var allItems = document.querySelectorAll('[class*="menu-item"], [class*="dropdown"] li');
        if (allItems.length > 10) {
            allItems[10].click();
            return 'clicked export item 10 (fallback)';
        }
        return 'export item not found, count=' + items.length;
    })()
    """
    result = run_js(js, timeout=10)
    print(f"    结果: {result}")
    time.sleep(3)
    return "clicked" in result.lower()


def click_confirm() -> bool:
    """点击确认按钮（button[7]）"""
    print("  [导出] 点击确认...")
    js = """
    (function() {
        var buttons = document.querySelectorAll('button');
        if (buttons.length > 7) {
            buttons[7].click();
            return 'clicked confirm button 7';
        }
        return 'confirm button not found, count=' + buttons.length;
    })()
    """
    result = run_js(js, timeout=10)
    print(f"    结果: {result}")
    return "clicked" in result.lower()


def wait_for_download(timeout: int = 60) -> str:
    """等待下载完成，返回最新下载文件路径"""
    print(f"  [等待] 等待下载完成（最多 {timeout}s）...")
    download_dir = Path.home() / "Downloads"
    # 记录当前文件
    before = set(download_dir.glob("*.csv"))
    before_times = {f: f.stat().st_mtime for f in before}

    for i in range(timeout // 3):
        time.sleep(3)
        after = set(download_dir.glob("*.csv"))
        new_files = after - before
        if new_files:
            # 找最新的
            latest = max(new_files, key=lambda f: f.stat().st_mtime)
            # 等待文件写入完成
            time.sleep(2)
            if latest.stat().st_size > 0:
                print(f"  ✅ 下载完成: {latest.name} ({latest.stat().st_size:,} bytes)")
                return str(latest)
        # 也检查已有文件是否更新
        for f in download_dir.glob("*.csv"):
            if f in before_times and f.stat().st_mtime > before_times[f] + 5:
                print(f"  ✅ 文件更新: {f.name} ({f.stat().st_size:,} bytes)")
                return str(f)

    print("  ❌ 下载超时")
    return ""


def rename_and_move(src_path: str, output_name: str) -> str:
    """重命名并移动到 EXPORT_DIR"""
    src = Path(src_path)
    dst = EXPORT_DIR / output_name
    # 如果目标已存在，先备份
    if dst.exists():
        backup = dst.with_suffix(f".bak-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        dst.rename(backup)
        print(f"  [备份] 旧文件 → {backup.name}")
    # 移动
    import shutil
    shutil.move(str(src), str(dst))
    print(f"  ✅ 已保存: {dst}")
    return str(dst)


def export_filter(filter_config: dict) -> str:
    """导出单个筛选器"""
    name = filter_config["name"]
    tab_index = filter_config["tab_index"]
    output_csv = filter_config["output_csv"]

    print(f"\n{'='*50}")
    print(f" 导出: {filter_config['label']} → {output_csv}")
    print(f"{'='*50}")

    # Step 1: 点击筛选器 tab
    if not click_filter_tab(tab_index):
        print(f"  ⚠️ 点击 tab 失败，尝试继续...")

    # Step 2: 点击更多菜单
    if not click_more_menu():
        print(f"  ❌ 更多菜单未找到")
        return ""

    # Step 3: 点击导出工作项
    if not click_export_item():
        print(f"  ❌ 导出项未找到")
        return ""

    # Step 4: 点击确认
    if not click_confirm():
        print(f"  ⚠️ 确认按钮未找到，可能自动开始下载")

    # Step 5: 等待下载
    downloaded = wait_for_download(timeout=90)
    if not downloaded:
        return ""

    # Step 6: 重命名并移动
    result = rename_and_move(downloaded, output_csv)
    return result


def collect_all(filters: list = None) -> list:
    """导出所有筛选器"""
    if filters is None:
        filters = FILTERS

    open_ones_page()
    results = []
    for f in filters:
        path = export_filter(f)
        if path:
            results.append(path)
        time.sleep(3)  # 间隔避免冲突

    return results


def verify_export(path: str) -> dict:
    """验证导出文件"""
    import pandas as pd
    df = pd.read_csv(path, low_memory=False)
    return {
        "path": path,
        "rows": len(df),
        "columns": len(df.columns),
        "size_kb": Path(path).stat().st_size // 1024,
    }


if __name__ == "__main__":
    print("=" * 60)
    print(" ONES 数据采集器 — osascript 自动化版")
    print(f" 导出目录: {EXPORT_DIR}")
    print(f" 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if len(sys.argv) > 1:
        # 导出指定筛选器
        target = sys.argv[1]
        matching = [f for f in FILTERS if f["name"] == target]
        if not matching:
            print(f"未知筛选器: {target}")
            print(f"可用: {[f['name'] for f in FILTERS]}")
            sys.exit(1)
        open_ones_page()
        result = export_filter(matching[0])
        if result:
            info = verify_export(result)
            print(f"\n✅ 完成: {info['rows']} 行 × {info['columns']} 列 ({info['size_kb']} KB)")
        else:
            print("\n❌ 导出失败")
    else:
        # 导出全部
        results = collect_all()
        print(f"\n{'='*60}")
        print(f" 导出完成: {len(results)}/{len(FILTERS)}")
        for r in results:
            info = verify_export(r)
            print(f"  ✅ {Path(r).name}: {info['rows']} 行 × {info['columns']} 列")
        if not results:
            print("  ❌ 全部失败")
