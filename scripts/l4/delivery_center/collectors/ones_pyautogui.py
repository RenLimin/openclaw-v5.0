#!/usr/bin/env python3
"""ONES 数据采集器 — pyautogui 版

用 macOS 原生 GUI 自动化（pyautogui）控制 Chrome 浏览器，
按照人工操作步骤实现 ONES 数据采集。

操作步骤：
  1. 登录 ONES（通过 IAM SSO）
  2. 点击左侧"我的工作台"
  3. 点击右侧"筛选器" tab
  4. 点击"2026周报-签约项目"
  5. 点击"导出原始数据"
  6. 点击"确认"

虚拟环境：/tmp/pyautogui-env
"""

import time, json, signal, sys, subprocess
from pathlib import Path

OUTPUT_DIR = Path('/Users/bangcle/.openclaw/data/ones_exports')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 全局超时
def handler(signum, frame):
    print('\n[TIMEOUT]')
    sys.exit(1)
signal.signal(signal.SIGALRM, handler)
signal.alarm(300)

def run_pyautogui(script: str) -> str:
    """在 pyautogui 虚拟环境中运行脚本"""
    result = subprocess.run(
        ['/tmp/pyautogui-env/bin/python3', '-c', script],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout + result.stderr

def step1_login():
    """Step 1: 打开 Chrome 并登录 ONES"""
    print('\n[Step 1] 打开 Chrome 并登录 ONES...')
    
    script = '''
import pyautogui, time, subprocess, json
from pathlib import Path

# 获取屏幕尺寸
screen_w, screen_h = pyautogui.size()
print(f"屏幕尺寸: {screen_w}x{screen_h}")

# 打开 Chrome（如果还没打开）
subprocess.run(["open", "-a", "Google Chrome", "--args", "--new-tab", "https://ones.bangcle.com/project/#/home/project"])
time.sleep(10)

# 检查是否需要登录
s = pyautogui.screenshot()
s.save("/Users/bangcle/.openclaw/data/ones_exports/pyauto_step1.png")
print("截图已保存")

# 获取当前窗口标题
import applescript
result = applescript.tell.app("System Events", "get name of first process whose frontmost is true")
print(f"前台应用: {result}")
'''
    output = run_pyautogui(script)
    print(output)

def step2_workspace():
    """Step 2: 点击"我的工作台\""""
    print("\\n[Step 2] 点击 我的工作台...")
    
    script = """
import pyautogui, time

# 截图查看当前状态
s = pyautogui.screenshot()
s.save("/Users/bangcle/.openclaw/data/ones_exports/pyauto_step2_before.png")
print("截图已保存")

# 尝试找到"我的工作台"并点击
# 通常在左侧导航栏
# 先尝试用快捷键 Command + F 搜索
pyautogui.hotkey("command", "f")
time.sleep(1)
pyautogui.typewrite("我的工作台", interval=0.1)
time.sleep(1)

s2 = pyautogui.screenshot()
s2.save("/Users/bangcle/.openclaw/data/ones_exports/pyauto_step2_search.png")
print("搜索截图已保存")

# 取消搜索
pyautogui.press("escape")
time.sleep(0.5)
"""
    output = run_pyautogui(script)
    print(output)

def step3_filter():
    """Step 3: 点击"筛选器\" tab"""
    print("\\n[Step 3] 点击 筛选器 tab...")
    
    script = """
import pyautogui, time

s = pyautogui.screenshot()
s.save("/Users/bangcle/.openclaw/data/ones_exports/pyauto_step3.png")
print("截图已保存")
"""
    output = run_pyautogui(script)
    print(output)

if __name__ == "__main__":
    print("=" * 60)
    print(" ONES 数据采集 — pyautogui 版")
    print("=" * 60)
    
    step1_login()
    step2_workspace()
    step3_filter()
    
    print("\\n[DONE]")
