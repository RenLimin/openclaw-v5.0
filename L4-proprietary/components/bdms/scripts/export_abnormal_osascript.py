#!/usr/bin/env python3
"""Export 异常处置 from ONES using osascript - Chrome already open."""

import subprocess
import time
from pathlib import Path

DOWNLOAD_DIR = Path.home() / "Downloads"
TARGET_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
TARGET_DIR.mkdir(parents=True, exist_ok=True)

def run_js(js):
    cmd = [
        'osascript', '-e',
        f'tell application "Google Chrome" to execute (first tab of first window whose name contains "2026-签约项目异常处置") javascript "{js}"'
    ]
    print(f"→ Running: {cmd}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        print(f"  Output: {r.stdout.strip()}")
    if r.stderr:
        print(f"  Error: {r.stderr.strip()}")
    return r.returncode == 0

# 1. 找到并点击异常处置标签页（根据SKILL.md，tab_index是10，对应左侧索引23）
# 先查找包含异常处置的链接
print("\n=== Step 1: 查找异常处置链接 ===")
found = run_js("""
var r = [];
document.querySelectorAll('a').forEach(function(a, i) {
    var t = a.textContent.trim();
    if (t.indexOf('异常处置') !== -1) {
        r.push({i: i, t: t});
    }
});
JSON.stringify(r);
""")

# 点击链接
print("\n=== Step 2: 点击异常处置链接 ===")
time.sleep(2)
# 使用索引23，按SKILL.md
clicked = run_js("document.querySelectorAll('a')[23].click(); 'ok';")
time.sleep(10)  # 等待数据加载

# 3. 点击更多操作
print("\n=== Step 3: 点击更多操作 ===")
time.sleep(2)
run_js("document.querySelectorAll('[class*=more-menu-icon]')[0].click(); 'clicked';")
time.sleep(3)

# 4. 点击导出工作项
print("\n=== Step 4: 点击导出工作项 ===")
time.sleep(2)
run_js("document.querySelectorAll('[class*=dropdown-menu-item-label]')[10].click(); 'clicked';")
time.sleep(5)

# 5. 点击确定导出
print("\n=== Step 5: 点击确定，等待下载完成 ===")
time.sleep(2)
run_js("document.querySelectorAll('button')[7].click(); 'clicked';")
time.sleep(15)  # 等待下载完成

# 6. 移动文件到目标目录
print("\n=== Step 6: 移动文件到目标目录 ===")
# 找到最新下载的csv
csv_files = list(DOWNLOAD_DIR.glob("*.csv"))
if not csv_files:
    print("❌ 没有找到下载的CSV文件")
    exit(1)

newest = max(csv_files, key=lambda f: f.stat().st_mtime)
print(f"  最新下载文件: {newest}")

# 重命名
dest = TARGET_DIR / "异常处置.csv"
if dest.exists():
    dest.unlink()

import shutil
shutil.move(newest, dest)
print(f"✅ 文件已保存到: {dest}")

print("\n🎉 导出完成！")
