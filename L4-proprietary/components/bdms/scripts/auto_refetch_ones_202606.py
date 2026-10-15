#!/usr/bin/env python3
"""ONES 202606 自动重新导出（Playwright 自动新开 Chrome）。

完全自动化流程：
1. 打开 ONES workspace → 找到三个筛选器视图 → 逐个还原视图
2. 导出 → 等待下载 → 移动到 raw_data_202606/
"""
import subprocess
import sys
import time
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

DOWNLOAD_CANDIDATES = [
    Path.home() / "Downloads",
    Path.home() / "Desktop",
]


def find_newest_csv(since: float) -> Path | None:
    """查找 since 之后最新修改的 CSV。"""
    best = None
    best_m = since
    for d in DOWNLOAD_CANDIDATES:
        if not d.exists():
            continue
        for f in d.glob("*.csv"):
            m = f.stat().st_mtime
            if m > best_m:
                best = f
                best_m = m
    return best


def main():
    base_dir = Path(__file__).resolve().parent.parent
    out_dir = base_dir / "raw_data_202606"
    out_dir.mkdir(exist_ok=True)

    ones_workspace_url = "https://ones.bangcle.com/project/#/workspace/team/RZxvwUZ8"
    filter_info = [
        # (filter_id, output_name)
        ("5wY9X4m8", "202606周报-签约项目统计.csv"),
        ("KxnjPRY7", "202606周报-POC&提前实施统计.csv"),
        ("NWPaa48w", "202606-签约项目异常处置.csv"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--no-default-browser-check",
                "--password-store=basic",
            ]
        )
        context = browser.new_context(
            viewport=None,
            accept_downloads=True,
        )
        page = context.new_page()

        print(f"=== 打开 ONES workspace: {ones_workspace_url}")
        page.goto(ones_workspace_url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(8000)

        # 等待页面加载完成，点击登录（如果页面提示需要登录，停在这里）
        print("=== 检查是否需要登录 ===")
        if page.get_by_text("登录").count() > 0:
            print("❌ 需要手动登录后，重新运行脚本")
            browser.close()
            sys.exit(1)
        print("✅ 已登录，继续")

        for (filter_id, out_name) in filter_info:
            filter_url = f"https://ones.bangcle.com/project/#/workspace/team/RZxvwUZ8/filter/view/{filter_id}"
            print(f"\n=== 打开筛选器 {filter_id} → {out_name} ===")
            page.goto(filter_url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(12000)  # 等待视图加载

            # 1. 还原视图（找到还原按钮，点击）
            print("  尝试还原视图 → 找还原按钮")
            try:
                restore_btn = page.get_by_text("还原").first
                if restore_btn.is_visible(timeout=3000):
                    restore_btn.click()
                    page.wait_for_timeout(5000)
                    print("  ✅ 已点击还原")
                else:
                    print("  ⚠️ 还原按钮不可见，跳过")
            except Exception as e:
                print(f"  ⚠️ 还原失败: {e}")

            # 2. 点击更多操作 → 导出
            print("  点击更多操作 → 导出工作项")
            try:
                more_menu = page.locator("[class*=more-menu-icon]").first
                more_menu.click()
                page.wait_for_timeout(3000)

                export_item = page.locator("[class*=dropdown-menu-item-label]").filter(has_text="导出").filter(has_text="工作项").first
                if not export_item.is_visible(timeout=2000):
                    print("❌ 找不到导出工作项菜单项")
                    continue
                export_item.click()
                page.wait_for_timeout(4000)

                confirm_btn = page.get_by_role("button", name="确定").first
                confirm_btn.click()
                page.wait_for_timeout(2000)
                print("  ✅ 导出已触发，等待下载完成...")
            except Exception as e:
                print(f"❌ 导出失败: {e}")
                continue

            # 3. 等待下载完成
            since = time.time()
            wait_total = 35
            downloaded = None
            for i in range(wait_total):
                time.sleep(1)
                downloaded = find_newest_csv(since)
                if downloaded:
                    break
            if not downloaded:
                print(f"❌ {wait_total}s 后仍未找到下载文件")
                continue

            print(f"  下载完成: {downloaded.name} ({downloaded.stat().st_size:,} bytes)")

            # 4. 移动到目标目录
            dest = out_dir / out_name
            shutil.copy2(downloaded, dest)
            print(f"  ✅ 已保存到: {dest}")

            # 统计行数和列数
            import csv
            with open(dest, encoding='utf-8-sig') as fh:
                reader = csv.reader(fh)
                header = next(reader)
                n_rows = sum(1 for _ in reader)
            print(f"  内容: {n_rows} 行 × {len(header)} 列")

        browser.close()
        print("\n=== ONES 自动导出完成 ===")


if __name__ == "__main__":
    main()
