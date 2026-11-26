#!/usr/bin/env python3
"""net_probe.py — 通道网络定责探针（observability，只读）

背景：wecom 稳定性审计（2026-11-26）判定「整机/出口网络路径周期性瞬断」为主因，
但触发层未定案——(a) 本机代理 7897 / (b) 内网 DNS 首跳抖动 / (c) macOS 网络栈残留。
本探针在故障窗口留下定向采集样本，把推测变实证。

用法：
    python3 net_probe.py            # 采样一次；异常才落盘
    python3 net_probe.py --json     # 打印完整样本
    python3 net_probe.py --force-write   # 调试用：无论是否异常都落盘

退出码：0=全部正常；1=检出异常（已落盘 incident）；2=脚本自身错误

设计依据：L2-infra/components/observability/DESIGN.md §10（2026-11-26 增补）。
非目标：不改源码、不做恢复（归 channel_recovery.py）、不常驻高频探测。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

COMP_DIR = Path("/Users/bangcle/.openclaw/workspace/L2-infra/components/observability")
LOG_DIR = COMP_DIR / "logs"
INCIDENT_FILE = LOG_DIR / "net-probe-incidents.jsonl"

TARGET_HOST = os.environ.get("NET_PROBE_TARGET", "openws.work.weixin.qq.com")
CONTROL_HOST = os.environ.get("NET_PROBE_CONTROL", "example.com")

# 默认/内网首跳/公共 DNS；缺失的 resolver 自动跳过
RESOLVERS = [
    ("default", None),
    ("intranet-3", "172.16.6.3"),
    ("intranet-4", "172.16.6.4"),
    ("ali-5", "223.5.5.5"),
    ("tencent-29", "119.29.29.29"),
]

DIG_TIMEOUT = int(os.environ.get("NET_PROBE_DIG_TIMEOUT", "2"))
TCP_TIMEOUT = float(os.environ.get("NET_PROBE_TCP_TIMEOUT", "3"))
PROXY_PORT = int(os.environ.get("NET_PROBE_PROXY_PORT", "7897"))

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")


def now() -> datetime:
    return datetime.now(CST)


def resolve_env() -> dict:
    """launchd PATH 兜底（AGENTS.md §LaunchAgent PATH 红线）。"""
    env = dict(os.environ)
    parts = [p for p in env.get("PATH", "").split(":") if p]
    extras = [p for p in ("/opt/homebrew/bin", "/opt/homebrew/sbin") if p not in parts]
    env["PATH"] = ":".join(extras + parts)
    env.setdefault("HOME", str(Path.home()))
    return env


def run(cmd: list[str], timeout: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=resolve_env()
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, OSError):
        return 124, ""


def probe_dns(host: str, resolver: str | None) -> dict:
    """dig 单次查询，返回 ok/耗时/答案。resolver=None 表示系统默认。"""
    base = ["dig", "+time=%d" % DIG_TIMEOUT, "+tries=1", "+short"]
    cmd = base + ([f"@{resolver}"] if resolver else []) + [host]
    t0 = time.monotonic()
    rc, out = run(cmd, DIG_TIMEOUT + 2)
    ms = round((time.monotonic() - t0) * 1000, 1)
    answers = [ln.strip() for ln in out.splitlines() if re.match(r"^\d+\.\d+\.\d+\.\d+$", ln.strip())]
    return {
        "resolver": resolver or "default",
        "ok": rc == 0 and bool(answers),
        "rc": rc,
        "ms": ms,
        "answers": sorted(set(answers)),
    }


def probe_tcp(ip: str, port: int) -> dict:
    t0 = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=TCP_TIMEOUT):
            ms = round((time.monotonic() - t0) * 1000, 1)
        return {"ok": True, "ms": ms}
    except OSError:
        return {"ok": False, "ms": round((time.monotonic() - t0) * 1000, 1)}


def probe_tls(ip: str, port: int, sni: str) -> dict:
    t0 = time.monotonic()
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((ip, port), timeout=TCP_TIMEOUT) as raw:
            with ctx.wrap_socket(raw, server_hostname=sni) as sock:
                ms = round((time.monotonic() - t0) * 1000, 1)
                cert = sock.getpeercert()
                return {"ok": True, "ms": ms, "subject": str(cert.get("subject"))[:80]}
    except (OSError, ssl.SSLError):
        return {"ok": False, "ms": round((time.monotonic() - t0) * 1000, 1)}


def collect() -> dict:
    """一轮完整采样。全部只读。"""
    ts = now().isoformat(timespec="seconds")
    dns_target = [probe_dns(TARGET_HOST, r) for _, r in RESOLVERS]
    dns_control = [probe_dns(CONTROL_HOST, r) for _, r in RESOLVERS]

    # 取一个可达 IP 做 TCP/TLS 直连（优先 dig 答案，否则 getaddrinfo）
    ips = {a for d in dns_target for a in d["answers"]}
    direct_ips = sorted(ips)
    direct = [dict({"ip": ip}, **probe_tcp(ip, 443)) for ip in direct_ips]
    tls = [dict({"ip": ip}, **probe_tls(ip, 443, TARGET_HOST)) for ip in direct_ips]

    proxy = {"port": PROXY_PORT, **probe_tcp("127.0.0.1", PROXY_PORT)}

    target_ok_dns = any(d["ok"] for d in dns_target)
    control_ok_dns = any(d["ok"] for d in dns_control)
    any_direct_ok = any(d["ok"] for d in direct)
    any_tls_ok = any(t["ok"] for t in tls)

    # 异常判定：任一解析失败 / 直连全挂 / TLS 全挂 / 内网首跳失败
    failed = []
    if not target_ok_dns:
        failed.append("target-dns-all-fail")
    if not any(d["ok"] for name, d in zip((n for n, _ in RESOLVERS), dns_target) if name.startswith("intranet")):
        # 关键：插件只用系统默认解析（→ 内网首跳）。内网挂即插件 ENOTFOUND 的直接签名，
        # 即使公共 DNS 仍通也必须报——否则探针对真实故障保持沉默（回归测试锁住）。
        failed.append("intranet-dns-unreachable")
    if not any_direct_ok and direct:
        failed.append("target-tcp-all-fail")
    if not any_tls_ok and tls:
        failed.append("target-tls-all-fail")
    if not control_ok_dns:
        failed.append("control-dns-all-fail")

    names = [n for n, _ in RESOLVERS]
    per_resolver = dict(zip(names, dns_target))

    # 定责线索
    hint = None
    if failed:
        intranet_fail = not any(
            per_resolver.get(n, {}).get("ok") for n in ("intranet-3", "intranet-4")
        )
        public_ok = any(per_resolver.get(n, {}).get("ok") for n in ("ali-5", "tencent-29"))
        default_ok = per_resolver.get("default", {}).get("ok")
        if intranet_fail and (public_ok or default_ok):
            hint = "b-candidate: 内网 DNS 首跳失败而系统/公共 DNS 仍通 → 指向 (b) 内网 DNS 抖动（插件仅走系统默认解析）"
        elif proxy["ok"] and not target_ok_dns:
            hint = "a-candidate: 代理端口活但目标解析失败 → 指向 (a) 出口/代理链路"
        elif not proxy["ok"]:
            hint = "a-candidate: 代理端口不可达 → (a) 代理本身异常"
        elif intranet_fail and not public_ok:
            hint = "c-candidate: 内网首跳与公共 DNS 同挂 → 疑 (c) 整机网络栈/DNS 整体失效"
        else:
            hint = "undetermined: 共享出口整体失败，需对照历史与 Sleep/Wake 记录"

    return {
        "ts": ts,
        "target": TARGET_HOST,
        "control": CONTROL_HOST,
        "dns_target": dns_target,
        "dns_control": dns_control,
        "direct_tcp": direct,
        "tls": tls,
        "proxy": proxy,
        "failed": failed,
        "hint": hint,
        "env_proxy": {
            "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
            "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
        },
    }


def write_incident(sample: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(INCIDENT_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="通道网络定责探针（只读）")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--force-write", action="store_true")
    args = ap.parse_args(argv)

    try:
        sample = collect()
    except Exception as exc:  # noqa: BLE001 - 探针自身错误必须显式退出
        print(f"❌ 探针执行错误: {exc}", file=sys.stderr)
        return 2

    abnormal = bool(sample["failed"])
    if abnormal or args.force_write:
        write_incident(sample)

    if args.as_json:
        print(json.dumps(sample, ensure_ascii=False, indent=2))
    else:
        icon = "❌" if abnormal else "✅"
        print(
            f"{icon} net-probe @ {sample['ts']} "
            f"DNS(target)={'通' if any(d['ok'] for d in sample['dns_target']) else '全挂'} "
            f"TCP直连={len([d for d in sample['direct_tcp'] if d['ok']])}/{len(sample['direct_tcp'])} "
            f"TLS={len([t for t in sample['tls'] if t['ok']])}/{len(sample['tls'])} "
            f"代理{PROXY_PORT}={'活' if sample['proxy']['ok'] else '死'}"
        )
        if abnormal:
            print(f"   异常: {', '.join(sample['failed'])}")
            print(f"   线索: {sample['hint']}")
            print(f"   已落盘: {INCIDENT_FILE}")
    return 1 if abnormal else 0


if __name__ == "__main__":
    sys.exit(main())
