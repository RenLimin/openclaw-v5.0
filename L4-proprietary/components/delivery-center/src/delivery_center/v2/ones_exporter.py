#!/usr/bin/env python3
"""
ONES 浏览器自动化导出工具
通过 osascript 控制已打开的 Chrome 浏览器，从 ONES 筛选器导出 CSV 数据

前置条件：
- Chrome 已打开 ONES 页面（https://ones.bangcle.com/），并且已登录
- macOS 系统（使用 osascript）
- Python 3.8+
"""

import subprocess
import time
import os
from pathlib import Path
from typing import List, Dict, Optional

DOWNLOADS_DIR = Path.home() / "Downloads"
TARGET_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"

# 确保目标目录存在
TARGET_DIR.mkdir(parents=True, exist_ok=True)


def run_js(js: str) -> str:
    """
    在 Chrome 的 ONES 标签页执行 JavaScript
    """
    cmd = [
        "osascript", "-e",
        'tell application "Google Chrome" to execute (first tab of first window whose URL contains "ones.bangcle.com") javascript "' + js.replace('"', '\\"') + '"'
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def click_menu_item(menu_text: str) -> bool:
    """
    点击左侧功能树中包含指定文本的菜单
    通过文本匹配找到正确的链接，而不是依赖固定索引
    """
    # 查找所有包含目标文本的a标签
    js_find = """
var results = [];
document.querySelectorAll('a').forEach(function(el, idx) {
    var text = el.textContent.trim();
    if (text.indexOf('%s') !== -1) {
        results.push({
            index: idx,
            text: text,
            href: el.getAttribute('href')
        });
    }
});
JSON.stringify(results);
""" % menu_text

    result = run_js(js_find)
    if not result:
        print(f"❌ 未找到包含 '{menu_text}' 的菜单")
        return False

    try:
        items = eval(result)  # 解析JSON结果
    except Exception:
        print(f"❌ 解析菜单结果失败: {result}")
        return False

    if not items:
        print(f"❌ 未找到包含 '{menu_text}' 的菜单")
        return False

    # 点击第一个匹配项
    idx = items[0]['index']
    print(f"✅ 找到 '{menu_text}'，索引: {idx}，点击中...")
    run_js(f"document.querySelectorAll('a')[{idx}].click();")
    # ONES SPA 需要较长时间加载数据
    print("⏳ 等待页面加载 (15秒)...")
    time.sleep(15)
    return True


def click_export_button() -> bool:
    """
    点击导出流程: 更多操作 → 导出工作项 → 确定
    """
    # 1. 点击更多操作
    print("🔘 点击更多操作...")
    run_js("document.querySelectorAll('[class*=more-menu-icon]')[0].click();")
    time.sleep(3)

    # 2. 点击导出工作项
    print("🔘 点击导出工作项...")
    run_js("document.querySelectorAll('[class*=dropdown-menu-item-label]')[10].click();")
    time.sleep(5)

    # 3. 点击确定开始导出
    print("🔘 点击确定开始导出...")
    run_js("document.querySelectorAll('button')[7].click();")
    return True


def wait_for_download(timeout_minutes: int = 10) -> Optional[Path]:
    """
    等待下载完成，返回最新的CSV文件路径
    超时返回 None
    """
    print(f"⏳ 等待下载完成，最长等待 {timeout_minutes} 分钟...")
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60

    # 记录下载前已有的csv文件
    existing_csv = set([f.name for f in DOWNLOADS_DIR.glob("*.csv")])

    while (time.time() - start_time) < timeout_seconds:
        # 查找新出现的csv文件
        new_csv = [f for f in DOWNLOADS_DIR.glob("*.csv") if f.name not in existing_csv]
        if new_csv:
            # 取最新修改的文件
            newest = max(new_csv, key=os.path.getmtime)
            print(f"✅ 下载完成: {newest}")
            return newest
        time.sleep(10)  # 每10秒检查一次

    print(f"❌ 下载超时，{timeout_minutes} 分钟内未完成")
    return None


def move_to_target_dir(source_file: Path, menu_text: str) -> Path:
    """
    将下载文件移动到目标目录，重命名为可读名称
    """
    # 生成文件名：YYYY-MM-菜单名称.csv
    from datetime import datetime
    date_prefix = datetime.now().strftime("%Y%m%d")
    safe_name = menu_text.replace(' ', '-').replace('/', '-')
    target_file = TARGET_DIR / f"{date_prefix}-{safe_name}.csv"

    # 如果文件已存在，加序号
    counter = 1
    while target_file.exists():
        target_file = TARGET_DIR / f"{date_prefix}-{safe_name}-{counter}.csv"
        counter += 1

    source_file.replace(target_file)
    print(f"📦 文件已移动到: {target_file}")
    return target_file


def export_filter(menu_text: str) -> Optional[Path]:
    """
    导出指定筛选器的数据
    流程: 点击左侧菜单 → 点击导出按钮 → 等待下载 → 移动文件
    """
    print(f"\n🚀 开始导出: {menu_text}")

    # 1. 点击左侧菜单切换筛选器
    if not click_menu_item(menu_text):
        return None

    # 2. 点击导出流程
    if not click_export_button():
        return None

    # 3. 等待下载完成
    csv_file = wait_for_download(10)
    if not csv_file:
        return None

    # 4. 移动到目标目录
    return move_to_target_dir(csv_file, menu_text)


def list_available_filters() -> None:
    """
    列出当前页面所有可点击的筛选器链接
    """
    print("🔍 列出当前页面左侧筛选器:")
    result = run_js("""
var results = [];
document.querySelectorAll('a').forEach(function(el, idx) {
    var text = el.textContent.trim();
    if (text.length > 0 && el.getAttribute('href') && el.getAttribute('href').indexOf('/filter/') !== -1) {
        results.push({
            index: idx,
            text: text,
            href: el.getAttribute('href')
        });
    }
});
JSON.stringify(results);
""")

    if not result:
        print("   未找到任何筛选器链接")
        return

    try:
        items = eval(result)
    except Exception:
        print(f"   解析失败: {result}")
        return

    for item in items:
        print(f"   [{item['index']:>3d}] {item['text']} → {item['href']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="ONES 筛选器数据导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  python ones_exporter.py --list          列出当前页面所有筛选器
  python ones_exporter.py export "签约项目统计"    导出签约项目统计
  python ones_exporter.py export "POC&提前实施统计"
        """
    )
    sub = parser.add_subparsers(dest="command", help="命令")

    # list
    p_list = sub.add_parser("list", help="列出当前页面所有筛选器")
    p_list.set_defaults(func=lambda args: list_available_filters())

    # export
    p_export = sub.add_parser("export", help="导出指定筛选器")
    p_export.add_argument("menu_text", help="菜单文本（部分匹配即可）")
    p_export.set_defaults(func=lambda args: export_filter(args.menu_text))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "list":
        list_available_filters()
        return 0

    if args.command == "export":
        result = export_filter(args.menu_text)
        if result:
            print(f"\n🎉 导出成功！文件位置: {result}")
            return 0
        else:
            print(f"\n❌ 导出失败，请检查页面状态后重试")
            return 1


if __name__ == "__main__":
    exit(main())
