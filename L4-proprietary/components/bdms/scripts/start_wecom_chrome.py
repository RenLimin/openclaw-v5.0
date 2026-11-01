#!/usr/bin/env python3
"""启动企微文档持久化 Chrome（launch_persistent_context），供 CDP 复用登录态。

- 持久化目录：~/.openclaw/data/chrome-profiles/wecom（避免 /tmp 被清理）
- 端口：9222（远程调试）
- 首次运行需扫码登录企微，之后永久复用
"""
import os
import sys
import time
import json
import signal
import socket
from pathlib import Path

PROFILE = str(Path.home() / ".openclaw" / "data" / "chrome-profiles" / "wecom")
PORT = 9222
DOC_URL = "https://doc.weixin.qq.com/sheet/e3_AewA9wbYAJkCNWXLLXtMASV6kFQG5?scode=AD8AYAehAA801jsTMu"

def wait_cdp(port, timeout=30):
    for _ in range(timeout):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except OSError:
            time.sleep(1)
    return False

def main():
    print(f"profile: {PROFILE}")
    print(f"port: {PORT}")
    Path(PROFILE).mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        # 持久化上下文：登录态存到 PROFILE 目录
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            headless=False,
            args=[f"--remote-debugging-port={PORT}",
                  "--no-first-run", "--disable-sync",
                  "--disable-background-networking"],
            accept_downloads=True,
            viewport={"width": 1600, "height": 1000},
        )
        print("✅ Chrome 已启动（持久化 profile + CDP 9222）")

        # 打开目标文档
        page = context.pages[0] if context.pages else context.new_page()
        print(f"打开企微文档: {DOC_URL[:60]}...")
        page.goto(DOC_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        print(f"页面标题: {page.title()[:60]}")

        # 打印登录状态
        body = page.evaluate("() => document.body.innerText.slice(0, 200)")
        has_grid = page.locator("[role='grid']").count()
        has_tab = page.locator(".tab-bar-item").count()
        print(f"表格grid数: {has_grid}, Sheet tab数: {has_tab}")
        print(f"页面文本: {body[:150]!r}")

        # 保持运行，等待外部 CDP 连接
        print("\n🦞 Chrome 保持运行中（Ctrl+C 退出）。扫码登录企微后即可被 BDMS 复用。")
        while True:
            time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已退出")
