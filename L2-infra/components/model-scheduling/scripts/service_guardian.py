#!/usr/bin/env python3
"""
service_guardian.py — Gateway ↔ 自定义服务生命周期同步守护
方案 B：cron 每 5min 调用，检查 Gateway 状态，同步启停自定义服务。

设计原则：
- 幂等：多次调用结果一致
- 单向依赖：自定义服务跟随 Gateway，不反向依赖
- 可扩展：新增自定义服务只需追加 SERVICE 配置
- 不依赖 OpenClaw 内部实现：纯 launchctl + HTTP health check

Rex 拍板：2026-08-26，方案 B 确认
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ─── 配置 ───────────────────────────────────────────────
GATEWAY_LABEL = "ai.openclaw.gateway"
GATEWAY_HEALTH_URL = "http://127.0.0.1:18789/health"

# 自定义服务列表（未来新增服务在此追加）
CUSTOM_SERVICES = [
    {
        "label": "ai.openclaw.model-scheduling",
        "plist": os.path.expanduser(
            "~/.openclaw/workspace/model-scheduling/LaunchAgent/ai.openclaw.model-scheduling.plist"
        ),
        "check_port": 3000,
        "enabled": True,
    },
]

LOG_DIR = Path(os.path.expanduser("~/.openclaw/workspace/model-scheduling/logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "service_guardian.log"
STATE_FILE = LOG_DIR / "service_guardian_state.json"

MAX_LOG_SIZE = 512 * 1024  # 512KB 轮转


# ─── 工具函数 ───────────────────────────────────────────
def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        # 轮转
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_SIZE:
            LOG_FILE.rename(LOG_FILE.with_suffix(".log.1"))
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """执行命令，返回 (returncode, stdout, stderr)"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def check_gateway() -> bool:
    """检查 Gateway 是否存活"""
    rc, out, _ = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", GATEWAY_HEALTH_URL])
    return rc == 0 and out == "200"


def is_service_loaded(label: str) -> bool:
    """检查 LaunchAgent 是否已注册"""
    rc, out, _ = run(["launchctl", "list"])
    if rc != 0:
        return False
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] == label:
            return True
    return False


def is_service_running(label: str) -> bool:
    """检查服务进程是否在跑"""
    rc, out, _ = run(["launchctl", "list"])
    if rc != 0:
        return False
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[2] == label:
            pid = parts[0]
            return pid != "-" and int(pid) > 0
    return False


def is_port_listening(port: int) -> bool:
    """检查端口是否监听"""
    rc, out, _ = run(["lsof", "-i", f":{port}", "-sTCP:LISTEN"])
    return rc == 0 and len(out) > 0


def load_service(plist_path: str, label: str) -> bool:
    """加载 LaunchAgent"""
    # 确保 plist 在 LaunchAgents 目录
    la_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    src = Path(plist_path)
    if not src.exists():
        log(f"plist 不存在: {plist_path}", "ERROR")
        return False

    try:
        # 拷贝到 LaunchAgents（如果不存在或内容不同）
        need_copy = True
        if la_path.exists():
            if la_path.read_text() == src.read_text():
                need_copy = False
        if need_copy:
            la_path.write_text(src.read_text())
            la_path.chmod(0o644)
            log(f"已更新 plist: {la_path}")
    except Exception as e:
        log(f"拷贝 plist 失败: {e}", "ERROR")
        return False

    # bootstrap（幂等：已加载则跳过）
    if is_service_loaded(label):
        log(f"已加载: {label}")
        return True

    rc, out, err = run(["launchctl", "bootstrap", "gui/{}".format(os.getuid()), str(la_path)])
    if rc == 0:
        log(f"已加载服务: {label}")
        return True
    else:
        # 可能已存在，不算错
        if "already" in err.lower() or "exist" in err.lower():
            log(f"服务已存在: {label}")
            return True
        log(f"加载失败: {label} — {err}", "ERROR")
        return False


def unload_service(label: str) -> bool:
    """卸载 LaunchAgent"""
    la_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"

    if not is_service_loaded(label):
        log(f"未加载，跳过: {label}")
        return True

    rc, out, err = run(["launchctl", "bootout", "gui/{}".format(os.getuid()), str(la_path)])
    if rc == 0:
        log(f"已卸载服务: {label}")
        return True
    else:
        if "not" in err.lower() or "No" in err:
            log(f"服务已卸载: {label}")
            return True
        log(f"卸载失败: {label} — {err}", "ERROR")
        return False


def kill_service_port(port: int):
    """杀掉占用端口的进程（兜底）"""
    rc, out, _ = run(["lsof", "-ti", f":{port}"])
    if rc == 0 and out:
        for pid in out.splitlines():
            pid = pid.strip()
            if pid:
                run(["kill", "-9", pid])
                log(f"已杀掉占用端口 {port} 的进程: PID {pid}", "WARN")


# ─── 主逻辑 ─────────────────────────────────────────────
def main():
    log("=" * 50)
    log("Service Guardian 启动")

    gateway_alive = check_gateway()
    log(f"Gateway 状态: {'ALIVE' if gateway_alive else 'DEAD'}")

    results = {
        "timestamp": datetime.now().isoformat(),
        "gateway": gateway_alive,
        "services": [],
    }

    for svc in CUSTOM_SERVICES:
        if not svc.get("enabled", True):
            continue

        label = svc["label"]
        port = svc.get("check_port")
        svc_result = {"label": label, "action": "none"}

        if gateway_alive:
            # Gateway 活着 → 确保服务也活着
            if is_service_running(label):
                svc_result["action"] = "already_running"
                log(f"✅ {label}: 运行中")
            else:
                log(f"⚠️ {label}: 未运行，尝试拉起...")
                if load_service(svc["plist"], label):
                    time.sleep(2)  # 等启动
                    if is_service_running(label):
                        svc_result["action"] = "started"
                        log(f"✅ {label}: 已拉起")
                    else:
                        svc_result["action"] = "start_failed"
                        log(f"❌ {label}: 拉起失败", "ERROR")
                else:
                    svc_result["action"] = "load_failed"
                    log(f"❌ {label}: 加载失败", "ERROR")
        else:
            # Gateway 死了 → 停掉自定义服务
            if is_service_loaded(label):
                log(f"⛔ Gateway 停止，卸载 {label}...")
                if unload_service(label):
                    svc_result["action"] = "stopped"
                    log(f"✅ {label}: 已停止")
                else:
                    # 兜底：直接杀端口
                    if port:
                        kill_service_port(port)
                    svc_result["action"] = "stop_failed"
                    log(f"❌ {label}: 停止失败", "ERROR")
            else:
                svc_result["action"] = "already_stopped"
                log(f"✅ {label}: 已停止")

        # 端口二次确认
        if port and gateway_alive:
            if is_port_listening(port):
                svc_result["port_ok"] = True
            else:
                svc_result["port_ok"] = False
                log(f"⚠️ 端口 {port} 未监听", "WARN")

        results["services"].append(svc_result)

    # 写状态文件（供 cron/监控读取）
    try:
        STATE_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    except Exception:
        pass

    log("Service Guardian 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
