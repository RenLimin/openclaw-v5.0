#!/usr/bin/env python3
"""
OA 浏览器自动化导出工具
通过 osascript 控制已打开的 Chrome 浏览器，点击左侧菜单触发导出，等待下载完成后获取CSV文件

特点：
- 复用已登录的Chrome，不用重新登录
- 点击左侧功能树菜单项触发导出
- 支持最长等待10分钟（符合实际导出速度）
- 自动获取Downloads目录中新生成的CSV文件
- macOS + Chrome 环境（osascript）
"""

import subprocess
import time
import os
from pathlib import Path
from typing import List, Dict, Optional

# 配置
DOWNLOADS_DIR = Path.home() / "Downloads"


def run_js(js: str) -> str:
    """
    在 Chrome 的 OA 标签页执行 JavaScript
    默认匹配第一个包含 "bangcle" 在URL中的标签页（适配所有内部系统）
    """
    cmd = [
        "osascript", "-e",
        'tell application "Google Chrome" to execute (first tab of first window whose URL contains "bangcle") javascript "' + js.replace('"', '\\"') + '"'
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout.strip()


def click_menu_by_text(menu_text: str, wait_seconds: int = 15) -> bool:
    """
    点击左侧功能树中包含指定文本的菜单项
    通过文本匹配找到正确链接，不依赖固定索引
    点击后等待页面/数据加载
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
""" % menu_text.replace("'", "\\'")

    result = run_js(js_find)
    if not result:
        print(f"❌ 未找到包含 '{menu_text}' 的菜单")
        return False

    # 解析结果
    try:
        import json
        items = json.loads(result)
    except Exception as e:
        # 兼容之前写法
        try:
            items = eval(result)
        except Exception as e2:
            print(f"❌ 解析菜单结果失败: {result}, error: {e2}")
            return False

    if not items:
        print(f"❌ 未找到包含 '{menu_text}' 的菜单")
        return False

    # 点击第一个匹配项（通常就是要找的）
    idx = items[0]['index']
    matched_text = items[0]['text']
    print(f"✅ 找到菜单 '{matched_text}' (索引: {idx})，点击中...")
    run_js(f"document.querySelectorAll('a')[{idx}].click();")

    # 等待加载完成
    print(f"⏳ 等待页面数据加载 ({wait_seconds} 秒)...")
    time.sleep(wait_seconds)
    return True


def click_menus_recursive(menu_texts: List[str], wait_seconds: int = 10) -> bool:
    """
    逐级点击多级左侧菜单
    例如: ['门户', '销售合同管理系统', '合同基本信息管理', '合同台账（销售）']
    """
    for i, menu_text in enumerate(menu_texts):
        print(f"\n📂 第 {i+1} 级菜单: {menu_text}")
        if not click_menu_by_text(menu_text, wait_seconds):
            return False
    return True


def click_export_button(
    more_menu_selector: str = "[class*=more-menu-icon]",
    more_menu_index: int = 0,
    export_item_selector: str = "[class*=dropdown-menu-item-label]",
    export_item_index: int = 10,
    confirm_button_selector: str = "button",
    confirm_button_index: int = 7,
    wait_after_more: int = 3,
    wait_after_export: int = 5
) -> bool:
    """
    通用导出按钮点击流程：更多操作 → 导出 → 确定
    允许自定义选择器和索引，适配不同页面结构
    """
    # 1. 点击更多操作按钮
    print(f"🔘 点击更多操作 (索引 {more_menu_index})...")
    run_js(f"document.querySelectorAll('{more_menu_selector}')[{more_menu_index}].click();")
    time.sleep(wait_after_more)

    # 2. 点击导出菜单项
    print(f"🔘 点击导出选项 (索引 {export_item_index})...")
    run_js(f"document.querySelectorAll('{export_item_selector}')[{export_item_index}].click();")
    time.sleep(wait_after_export)

    # 3. 点击确定开始导出
    print(f"🔘 点击确认按钮开始导出 (索引 {confirm_button_index})...")
    run_js(f"document.querySelectorAll('{confirm_button_selector}')[{confirm_button_index}].click();")
    return True


def wait_for_csv_download(timeout_minutes: int = 10) -> Optional[Path]:
    """
    等待下载完成，返回Downloads目录中新生成的CSV文件路径
    超时返回 None，默认超时10分钟（满足大数据量导出）
    """
    print(f"⏳ 等待CSV下载完成，最长等待 {timeout_minutes} 分钟...")
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60

    # 记录下载前已有的csv文件
    existing_csv = set([f.name for f in DOWNLOADS_DIR.glob("*.csv")])

    while (time.time() - start_time) < timeout_seconds:
        # 查找新出现的csv文件
        new_csv = [f for f in DOWNLOADS_DIR.glob("*.csv") if f.name not in existing_csv]
        if new_csv:
            # 取最新修改的文件（一定是刚下载的）
            newest = max(new_csv, key=lambda f: os.path.getmtime(f))
            print(f"✅ 下载完成: {newest}")
            # 检查文件大小（排除0字节文件）
            if newest.stat().st_size == 0:
                print("⚠️  文件大小为0，可能导出失败，等待重试...")
                time.sleep(10)
                continue
            return newest
        # 每10秒检查一次
        time.sleep(10)

    print(f"❌ 下载超时，{timeout_minutes} 分钟内未完成")
    return None


def export_contract_list(
    menu_text: str,
    output_dir: Path = None,
    timeout_minutes: int = 10,
) -> Optional[Path]:
    """
    主流程：点击左侧菜单 → 点击导出按钮 → 等待下载完成 → 返回文件路径
    单级菜单版本（兼容旧用法）
    """
    print(f"\n🚀 开始导出OA合同清单，菜单项: {menu_text}")

    # 1. 点击左侧菜单切换页面
    if not click_menu_by_text(menu_text):
        return None

    # 2. 点击导出按钮触发下载（适配合同清单页面结构）
    if not click_export_oa_contract():
        return None

    # 3. 等待下载完成
    csv_file = wait_for_csv_download(timeout_minutes)
    if not csv_file:
        return None

    # 4. 如果指定了输出目录，复制过去
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        target_file = output_dir / csv_file.name
        # 如果文件存在加序号
        counter = 1
        while target_file.exists():
            stem = csv_file.stem
            ext = csv_file.suffix
            target_file = output_dir / f"{stem}_{counter}{ext}"
            counter += 1
        import shutil
        shutil.copy(csv_file, target_file)
        print(f"📦 文件已复制到: {target_file}")
        return target_file

    return csv_file


def export_contract_list_recursive(
    menu_texts: List[str],
    output_dir: Path = None,
    timeout_minutes: int = 10,
) -> Optional[Path]:
    """
    主流程：逐级点击多级左侧菜单 → 点击导出按钮 → 等待下载完成 → 返回文件路径
    OA合同台账需要四级菜单逐级点击
    """
    print(f"\n🚀 开始导出OA合同清单，逐级菜单: {' → '.join(menu_texts)}")

    # 1. 逐级点击左侧菜单进入目标页面
    if not click_menus_recursive(menu_texts, 10):
        return None

    # 2. 点击OA导出按钮（OA结构和ONES不同，直接点顶部导出按钮）
    if not click_export_oa_contract():
        return None

    # 3. 等待下载完成
    csv_file = wait_for_csv_download(timeout_minutes)
    if not csv_file:
        return None

    # 4. 如果指定了输出目录，复制过去
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        target_file = output_dir / csv_file.name
        # 如果文件存在加序号
        counter = 1
        while target_file.exists():
            stem = csv_file.stem
            ext = csv_file.suffix
            target_file = output_dir / f"{stem}_{counter}{ext}"
            counter += 1
        import shutil
        shutil.copy(csv_file, target_file)
        print(f"📦 文件已复制到: {target_file}")
        return target_file

    return csv_file


def click_export_oa_contract() -> bool:
    """
    点击OA合同台账导出按钮
    OA结构：按钮是 .ant-btn-primary，和搜索并列，直接点击即可
    """
    print("🔘 点击顶部导出按钮 (ant-btn-primary)...")
    # 找到第一个 ant-btn-primary 包含"导出"文字的按钮点击
    run_js("""
document.querySelectorAll('.ant-btn-primary').forEach(function(btn) {
    var text = btn.textContent.trim();
    if (text.indexOf('导出') !== -1) {
        btn.click();
    }
});
""")
    return True


def list_current_menu_items() -> None:
    """
    列出当前页面所有可点击的菜单项，方便确认文本
    """
    print("🔍 当前页面所有包含href的菜单项:")
    result = run_js("""
var results = [];
document.querySelectorAll('a').forEach(function(el, idx) {
    var text = el.textContent.trim();
    if (text.length > 0 && el.getAttribute('href')) {
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
        print("   未找到任何链接，请检查页面是否加载完成")
        return

    try:
        import json
        items = json.loads(result)
    except Exception:
        try:
            items = eval(result)
        except Exception:
            print(f"   解析失败: {result}")
            return

    for item in items:
        href = item.get('href', 'N/A')
        if len(href) > 60:
            href = href[:57] + "..."
        print(f"   [{item['index']:>3d}] {item['text']} → {href}")


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="OA 合同清单CSV导出工具（Chrome浏览器自动化）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  1. 先列出当前页面所有菜单项确认文本：
    python oa_csv_exporter.py list

  2. 单级菜单导出合同清单：
    python oa_csv_exporter.py export "合同清单"

  3. 多级菜单逐级导出（OA合同台账专用）：
    python oa_csv_exporter.py export-recursive "门户" "销售合同管理系统" "合同基本信息管理" "合同台账（销售）" -o ./data

  4. 指定输出目录：
    python oa_csv_exporter.py export "合同清单" --output-dir ./data
"""
    )
    sub = parser.add_subparsers(dest="command", help="命令")

    # list
    p_list = sub.add_parser("list", help="列出当前页面所有可点击菜单项")
    p_list.set_defaults(func=lambda args: list_current_menu_items())

    # export (single level)
    p_export = sub.add_parser("export", help="导出合同清单CSV（单级菜单）")
    p_export.add_argument("menu_text", help="左侧菜单文本（部分匹配即可，例如：合同清单）")
    p_export.add_argument("--output-dir", "-o", type=str, help="输出目录（可选，默认不复制，返回原始下载路径）")
    p_export.add_argument("--timeout", "-t", type=int, default=10, help="导出超时时间（分钟，默认10）")
    p_export.set_defaults(func=lambda args: export_contract_list(
        menu_text=args.menu_text,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        timeout_minutes=args.timeout
    ))

    # export-recursive (multiple levels, for OA contract)
    p_export_recursive = sub.add_parser("export-recursive", help="逐级导出合同清单CSV（多级菜单，OA专用）")
    p_export_recursive.add_argument("menu_texts", nargs="+", help="逐级菜单文本，例如：门户 销售合同管理系统 合同基本信息管理 合同台账（销售）")
    p_export_recursive.add_argument("--output-dir", "-o", type=str, help="输出目录（可选，默认不复制，返回原始下载路径）")
    p_export_recursive.add_argument("--timeout", "-t", type=int, default=15, help="导出超时时间（分钟，默认15，含各级菜单加载时间）")
    p_export_recursive.set_defaults(func=lambda args: export_contract_list_recursive(
        menu_texts=args.menu_texts,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        timeout_minutes=args.timeout
    ))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    result = args.func(args)
    if result:
        if isinstance(result, Path):
            print(f"\n🎉 导出成功！\n文件位置: {result.resolve()}")
        return 0
    else:
        print(f"\n❌ 导出失败，请检查：\n1. Chrome 是否已打开OA页面并登录\n2. 页面是否加载完成\n3. 菜单文本是否正确")
        return 1


if __name__ == "__main__":
    exit(main())
