#!/usr/bin/env python3
"""隔离 Chrome 实例（OA/ONES 专用）——幂等启动 / 状态 / 关闭。

背景（缺口 2026-11-23）：
  registry 记 `browser-isolated-chrome` 的入口是 profile + CDP 端口，但**全仓没有
  启动器资产**：专用实例未运行时 `ones_available()` 恒为 False，每轮都要重新摸索
  启动命令（memory/2026-11-20.md:40 已自记「下轮仍会重复探索」）。
  本脚本把「确保实例可用」收敛成**一个幂等调用**，供 OA/ONES 采集与测试前置复用。

契约（对齐 DESIGN.md §4 与 USER.md 红线）：
  - 专用 profile：~/.openclaw/data/chrome-profiles/oa-live（**不碰用户现有 Chrome**）
  - 专用端口：9333（registry 权威值；bdms 侧 9222 是另一套，见 DESIGN.md 端口说明）
  - 幂等：已在运行 → 直接复用（一次 CDP 探测，毫秒级），不重复起进程
  - 单实例：文件锁串行化并发调用
  - 用后即关：stop 只杀「命令行含本 profile + 本端口」的进程，绝不误伤用户 Chrome
  - 绝对路径兜底：Chrome 二进制不依赖 PATH（AGENTS.md 定时任务红线）

用法：
  python3 ensure_chrome.py            # ensure（已在跑则复用）
  python3 ensure_chrome.py status     # 只读：是否可用 + 端口/进程
  python3 ensure_chrome.py stop       # 关闭本专用实例
  python3 ensure_chrome.py --json     # 机器可读输出

退出码：ensure/status 0=可用；stop 0=已关闭/本就没起；1=失败
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------- 常量（可被测试 monkeypatch）----------
DATA_DIR = Path.home() / ".openclaw" / "data" / "chrome-profiles"
PROFILE_DIR = DATA_DIR / "oa-live"
LOCK_FILE = DATA_DIR / "oa-live.lock"
CDP_URL = os.environ.get("ONES_CDP_URL", "http://127.0.0.1:9333")
CDP_PORT = int(os.environ.get("ONES_CDP_PORT", "9333"))
STARTUP_TIMEOUT = float(os.environ.get("ENSURE_CHROME_TIMEOUT", "25"))
POLL_INTERVAL = 0.5

# Chrome 二进制绝对路径兜底（禁止裸命令名依赖 PATH）
_CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/opt/homebrew/bin/chromium"),
    Path("/usr/bin/chromium"),
)


def resolve_chrome() -> str | None:
    """解析 Chrome/Chromium 可执行绝对路径。"""
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if found:
        return found
    for cand in _CHROME_CANDIDATES:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def cdp_probe(timeout: float = 2.0) -> dict | None:
    """探测 CDP /json/version。可用返回 dict，不可用返回 None（不抛）。"""
    url = f"{CDP_URL}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        return json.loads(body) if body.strip() else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def is_available() -> bool:
    """专用实例是否可用（CDP 有响应即视为可用）。"""
    return cdp_probe() is not None


def _dedicated_pids() -> list[int]:
    """找出本专用实例的 PID：命令行同时含本 profile 与本端口。

    绝不匹配用户现有 Chrome（其命令行不含我们的 profile 目录）。
    """
    pids: list[int] = []
    try:
        out = subprocess.run(
            ["pgrep", "-f", f"remote-debugging-port={CDP_PORT}"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return pids
    for tok in out.stdout.split():
        try:
            pid = int(tok)
        except ValueError:
            continue
        try:
            cmd = subprocess.run(
                ["ps", "-o", "command=", "-p", str(pid)],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if str(PROFILE_DIR) in cmd:
            pids.append(pid)
    return pids


def _launch(chrome: str) -> subprocess.Popen:
    """启动专用实例（独立进程组，便于整组回收）。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        chrome,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-background-networking",
    ]
    return subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _wait_ready(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_available():
            return True
        time.sleep(POLL_INTERVAL)
    return is_available()


def _kill(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 5
    while time.time() < deadline and _dedicated_pids():
        time.sleep(0.3)
    for pid in _dedicated_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def ensure() -> tuple[bool, str]:
    """确保专用实例可用。返回 (ok, message)。"""
    if is_available():
        return True, f"复用已运行实例（CDP {CDP_URL}）"

    chrome = resolve_chrome()
    if not chrome:
        return False, "未找到 Chrome/Chromium 可执行文件"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
        except OSError as exc:
            return False, f"获取启动锁失败: {exc}"
        # 锁内二次确认（可能在等锁期间已被别人起来）
        if is_available():
            return True, f"复用已运行实例（CDP {CDP_URL}）"
        proc = _launch(chrome)
        if _wait_ready(STARTUP_TIMEOUT):
            return True, f"已启动专用实例（pid={proc.pid}, CDP {CDP_URL}, profile={PROFILE_DIR}）"
        _kill([proc.pid])
        return False, f"启动后 {STARTUP_TIMEOUT:.0f}s 内 CDP 未就绪（pid={proc.pid} 已回收）"


def status() -> tuple[bool, dict]:
    """只读状态。返回 (available, info)。"""
    info = {
        "cdp_url": CDP_URL,
        "profile": str(PROFILE_DIR),
        "profile_exists": PROFILE_DIR.is_dir(),
        "chrome": resolve_chrome(),
        "pids": _dedicated_pids(),
    }
    probe = cdp_probe()
    info["cdp_probe"] = probe is not None
    return probe is not None, info


def stop() -> tuple[bool, str]:
    """关闭本专用实例（只杀匹配本 profile+端口的进程）。"""
    pids = _dedicated_pids()
    if not pids:
        return True, "无运行中的专用实例"
    _kill(pids)
    remaining = _dedicated_pids()
    if remaining:
        return False, f"仍有残留进程: {remaining}"
    return True, f"已关闭专用实例（pid={pids}）"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="隔离 Chrome 实例（OA/ONES 专用）幂等管理")
    ap.add_argument("action", nargs="?", default="ensure",
                    choices=["ensure", "status", "stop"])
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args(argv)

    if args.action == "status":
        ok, info = status()
        if args.json:
            print(json.dumps({"available": ok, **info}, ensure_ascii=False))
        else:
            print(f"{'✅' if ok else '⚠️ '} CDP 可用={ok} 端口={CDP_PORT} "
                  f"profile={PROFILE_DIR} pids={info['pids']}")
        return 0 if ok else 1

    if args.action == "stop":
        ok, msg = stop()
        print(("✅ " if ok else "❌ ") + msg)
        return 0 if ok else 1

    ok, msg = ensure()
    print(("✅ " if ok else "❌ ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
