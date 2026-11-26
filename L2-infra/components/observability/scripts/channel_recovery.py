#!/usr/bin/env python3
"""channel_recovery.py — Channel 主动恢复兜底（observability 第 2 层）

背景：合盖睡眠 / 进程冻结后，WeCom 重连阶梯耗尽，而 gateway 内置 thaw 恢复
因 defer 语义长期不落地，health-monitor 又因自动重启阶梯重置而永不触发。
本模块独立检测 channel「断连且未自愈」并主动重启该 channel。

设计：DESIGN-DETAIL-channel-recovery-v1.0.md

用法：
    python3 channel_recovery.py --recover   # 检测并按需恢复（launchd 调用）
    python3 channel_recovery.py --check     # 只判定不动作
    python3 channel_recovery.py --status    # 打印内部状态 JSON

退出码：
    0  正常 / 已恢复 / 无需动作
    2  gateway 不可达（channel 操作无意义）
    3  恢复动作执行但失败
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

CST = timezone(timedelta(hours=8))

WORKSPACE = Path("/Users/bangcle/.openclaw/workspace")
COMP_DIR = WORKSPACE / "L2-infra" / "components" / "observability"
LOG_DIR = COMP_DIR / "logs"
STATE_FILE = LOG_DIR / "channel_recovery_state.json"
RECOVERY_LOG = LOG_DIR / "channel-recovery.log"
LOCK_FILE = LOG_DIR / "channel_recovery.lock"

GATEWAY_LOG = Path.home() / "Library" / "Logs" / "openclaw" / "gateway.log"
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"
SAFE_RESTART = (
    WORKSPACE / "L2-infra" / "components" / "gateway-safety" / "scripts" / "safe_restart.sh"
)

CHANNEL = os.environ.get("CHANNEL_RECOVERY_CHANNEL", "wecom")
ACCOUNT = os.environ.get("CHANNEL_RECOVERY_ACCOUNT", "default")

SEED_BYTES = int(os.environ.get("CHANNEL_RECOVERY_SEED_BYTES", str(8 * 1024 * 1024)))
STABLE_SECONDS = int(os.environ.get("CHANNEL_RECOVERY_STABLE_SECONDS", "600"))
COOLDOWN_SECONDS = int(os.environ.get("CHANNEL_RECOVERY_COOLDOWN_SECONDS", "600"))
STALE_SECONDS = int(os.environ.get("CHANNEL_RECOVERY_STALE_SECONDS", "1800"))
MAX_LIGHT_PER_DAY = int(os.environ.get("CHANNEL_RECOVERY_MAX_LIGHT_PER_DAY", "5"))
VERIFY_TIMEOUT = int(os.environ.get("CHANNEL_RECOVERY_VERIFY_TIMEOUT", "45"))
CLI_TIMEOUT = int(os.environ.get("CHANNEL_RECOVERY_CLI_TIMEOUT", "30"))
HTTP_PROBE_TIMEOUT = int(os.environ.get("CHANNEL_RECOVERY_HTTP_PROBE_TIMEOUT", "5"))

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
EVENT_RE = re.compile(rf"\[{re.escape(CHANNEL)}\] \[([^\]]+)\] (.*)$")

SENSITIVE_KEYS = {"secret", "token", "password", "apikey", "api_key", "credential"}


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def now_ts() -> float:
    return datetime.now(CST).timestamp()


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if any(s in k.lower() for s in SENSITIVE_KEYS) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def log(level: str, event: str, **fields: Any) -> None:
    """写 JSONL 日志，并打印一行人类可读摘要到 stdout。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(CST).isoformat(timespec="seconds"),
        "level": level,
        "event": event,
        **fields,
    }
    line = json.dumps(_redact(record), ensure_ascii=False)
    try:
        with open(RECOVERY_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(f"[{record['ts']}] {level} {event} {json.dumps(_redact(fields), ensure_ascii=False)}")


def ensure_env() -> dict:
    """launchd 环境缺 /opt/homebrew/bin，必须注入，否则 openclaw 找不到 node。"""
    env = dict(os.environ)
    parts = [p for p in env.get("PATH", "").split(":") if p]
    # homebrew 必须置于 PATH 最前（顺序：bin 在 sbin 之前）
    extras = [p for p in ("/opt/homebrew/bin", "/opt/homebrew/sbin") if p not in parts]
    env["PATH"] = ":".join(extras + parts)
    env.setdefault("HOME", str(Path.home()))
    return env


def run_cli(args: Iterable[str], timeout: int | None = None) -> tuple[int, str, str]:
    """执行 openclaw CLI，返回 (rc, stdout, stderr)。"""
    try:
        proc = subprocess.run(
            [OPENCLAW_BIN, *args],
            capture_output=True,
            text=True,
            timeout=timeout or CLI_TIMEOUT,
            env=ensure_env(),
            cwd=str(WORKSPACE),
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except OSError as exc:
        return 1, "", str(exc)


def gateway_port() -> int:
    """从 openclaw.json 读取 gateway.port，失败回退 18789。"""
    try:
        data = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
        return int(data["gateway"]["port"])
    except (OSError, KeyError, TypeError, ValueError):
        return 18789


class Lock:
    """非阻塞互斥锁，防止 launchd 与手动运行并发。"""

    def __enter__(self) -> "Lock":
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._fh = open(LOCK_FILE, "w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.close()
            raise SystemExit("channel_recovery: another instance is running")
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
        finally:
            self._fh.close()


# --------------------------------------------------------------------------
# 状态
# --------------------------------------------------------------------------

def load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1}


def save_state(state: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)


# --------------------------------------------------------------------------
# 日志解析
# --------------------------------------------------------------------------

def _classify(message: str) -> str | None:
    if "Authentication successful" in message:
        return "auth_ok"
    if "giving up after 10 restart attempts" in message:
        return "gave_up"
    if "Max reconnect attempts reached" in message:
        return "gave_up"
    if "Connection lost" in message or "WebSocket disconnected" in message:
        return "conn_lost"
    if "Connecting to WebSocket" in message:
        return "reconnect"
    return None


def parse_events(text: str) -> list[tuple[float, str]]:
    """从日志文本抽取本 channel 的事件，返回 (epoch_seconds, kind) 列表。"""
    events: list[tuple[float, str]] = []
    for line in text.splitlines():
        ts_match = TS_RE.match(line)
        if not ts_match:
            continue
        try:
            ts = datetime.strptime(ts_match.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=CST)
        except ValueError:
            continue
        ev_match = EVENT_RE.search(line)
        if not ev_match or ev_match.group(1) != ACCOUNT:
            continue
        kind = _classify(ev_match.group(2))
        if kind:
            events.append((ts.timestamp(), kind))
    return events


def _read_range(start: int) -> tuple[str, int]:
    size = GATEWAY_LOG.stat().st_size
    start = max(0, min(start, size))
    with open(GATEWAY_LOG, "r", encoding="utf-8", errors="ignore") as fh:
        fh.seek(start)
        return fh.read(), size


def seed_events() -> tuple[list[tuple[float, str]], int]:
    """首次运行：从 EOF 回扫 SEED_BYTES 播种。"""
    size = GATEWAY_LOG.stat().st_size
    start = max(0, size - SEED_BYTES)
    text, size = _read_range(start)
    return parse_events(text), size


def read_new_events(offset: int) -> tuple[list[tuple[float, str]], int]:
    """增量读取；日志 shrink/轮转时回退回扫。"""
    try:
        size = GATEWAY_LOG.stat().st_size
    except OSError:
        return [], offset
    if size < offset:
        start = max(0, size - SEED_BYTES)
        text, size = _read_range(start)
        return parse_events(text), size
    if size == offset:
        return [], offset
    text, size = _read_range(offset)
    return parse_events(text), size


EVENT_FIELD = {
    "auth_ok": "last_auth_ok",
    "conn_lost": "last_conn_lost",
    "gave_up": "last_gave_up",
    "reconnect": "last_reconnect",
}


def apply_events(state: dict, events: Iterable[tuple[float, str]]) -> None:
    """应用事件并维护断连 streak 起点（down_since）。

    语义：真正的失败（conn_lost / gave_up）开启 streak；鉴权成功清零。
    `reconnect`（Connecting to WebSocket）不算失败——它在正常建连流程里
    紧跟 auth 之后也会打印，若计入会导致健康期被误判 down。
    """
    for ts, kind in sorted(events, key=lambda item: item[0]):
        key = EVENT_FIELD[kind]
        if ts > float(state.get(key) or 0):
            state[key] = ts
        if kind == "auth_ok":
            state["down_since"] = None
        elif kind in ("conn_lost", "gave_up") and state.get("down_since") is None:
            state["down_since"] = ts


# --------------------------------------------------------------------------
# channel 状态
# --------------------------------------------------------------------------

def channel_status() -> dict | None:
    rc, out, err = run_cli(["gateway", "call", "channels.status", "--json"])
    if rc != 0:
        log("WARN", "channels.status.failed", rc=rc, stderr=err.strip()[:200])
        return None
    idx = out.find("{")
    if idx < 0:
        return None
    try:
        data = json.loads(out[idx:])
    except ValueError:
        return None
    accounts = data.get("channelAccounts", {}).get(CHANNEL) or []
    account = next((a for a in accounts if a.get("accountId") == ACCOUNT), accounts[0] if accounts else None)
    return {
        "channel": data.get("channels", {}).get(CHANNEL),
        "account": account,
        "statusIssues": data.get("statusIssues"),
    }


def gateway_http_ok() -> bool:
    """HTTP 存活探针：用于确认 gateway 进程活着。"""
    import urllib.request

    port = gateway_port()
    url = f"http://127.0.0.1:{port}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=HTTP_PROBE_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


# --------------------------------------------------------------------------
# 判定
# --------------------------------------------------------------------------

def evaluate(state: dict, status: dict | None, now: float) -> str:
    """返回 up / down-unstable / down / stale / unknown。

    - up           无失败信号（自上次鉴权后无断连）
    - down-unstable 已断连但不足稳定期（给内置重连阶梯留机会）
    - down          断连持续 >= STABLE_SECONDS
    - stale         日志静默过久，无法判定
    - unknown       无日志基线且无 status 依据
    """
    last_event = max(
        float(state.get("last_auth_ok") or 0),
        float(state.get("last_conn_lost") or 0),
        float(state.get("last_gave_up") or 0),
        float(state.get("last_reconnect") or 0),
    )
    if not last_event:
        return _evaluate_status_fallback(state, status, now)

    down_since = state.get("down_since")
    if down_since is None:
        # 自上次鉴权后无失败 → 健康。安静是正常态，不因静默时长判 stale。
        return "up"
    if now - float(down_since) < STABLE_SECONDS:
        return "down-unstable"
    if now - last_event > STALE_SECONDS:
        # streak 已持续，但日志再无动静：无法确认现状，不动作
        return "stale"
    return "down"


def _evaluate_status_fallback(state: dict, status: dict | None, now: float) -> str:
    account = (status or {}).get("account") or {}
    unhealthy = (account.get("running") is False) or bool(account.get("lastError"))
    streak = int(state.get("status_down_streak") or 0)
    streak = streak + 1 if unhealthy else 0
    state["status_down_streak"] = streak
    if streak >= 2:
        return "down"
    return "unknown"


# --------------------------------------------------------------------------
# 恢复动作
# --------------------------------------------------------------------------

def _account_last_start_epoch(status: dict | None) -> float | None:
    account = (status or {}).get("account") or {}
    value = account.get("lastStartAt")
    if isinstance(value, (int, float)) and value > 0:
        return float(value) / 1000.0
    return None


def _account_intentionally_stopped(state: dict, status: dict | None, now: float) -> bool:
    """channel 是否被人为停掉（running=false 且 stop 时间晚于上次鉴权，且无 gave-up）。

    目的：不推翻用户的 `channels.stop` 操作。
    """
    account = (status or {}).get("account") or {}
    if account.get("running") is not False:
        return False
    stopped = account.get("lastStopAt")
    if not isinstance(stopped, (int, float)) or stopped <= 0:
        return False
    last_auth = float(state.get("last_auth_ok") or 0)
    gave_up = float(state.get("last_gave_up") or 0)
    if gave_up > last_auth:
        return False  # 插件自身放弃，属可恢复故障
    return (stopped / 1000.0) > last_auth


def decide_action(state: dict, decision: str, status: dict | None, now: float) -> tuple[str, str]:
    if decision != "down":
        return "none", ""
    last_recovery = float(state.get("last_recovery_at") or 0)
    if last_recovery and now - last_recovery < COOLDOWN_SECONDS:
        return "skip", f"cooldown {now - last_recovery:.0f}s < {COOLDOWN_SECONDS}s"
    started = _account_last_start_epoch(status)
    if started and now - started < COOLDOWN_SECONDS:
        return "skip", f"lastStartAt {now - started:.0f}s < {COOLDOWN_SECONDS}s"

    # 用户手动停掉的 channel 不自动拉起（否则会推翻人为操作）
    if _account_intentionally_stopped(state, status, now):
        return "skip", "channel stopped after last auth (intentional)"

    # 注入 now（与本函数其余时间判定一致，不再用墙钟）——否则跨日计数
    # 在测试/回放中不可复现（2026-11-26 修复：既有两用例因写死 NOW 常挂）。
    day = datetime.fromtimestamp(now, CST).strftime("%Y-%m-%d")
    if state.get("light_day") != day:
        state["light_day"] = day
        state["light_count"] = 0
    if int(state.get("light_count") or 0) >= MAX_LIGHT_PER_DAY:
        return "alert", f"daily light cap {MAX_LIGHT_PER_DAY} reached"
    if int(state.get("consecutive_light_failures") or 0) >= 2:
        return "full", "light recovery failed twice"
    return "light", ""


def light_recovery(state: dict) -> tuple[bool, str]:
    """stop → start 单 channel，等待 Authentication successful 作为成功证据。"""
    start_ts = now_ts()
    rc, out, err = run_cli(
        ["gateway", "call", "channels.stop", "--params",
         json.dumps({"channel": CHANNEL, "accountId": ACCOUNT}), "--json"]
    )
    if rc != 0:
        return False, f"stop rc={rc} {err.strip()[:160]}"
    time.sleep(1)
    rc, out, err = run_cli(
        ["gateway", "call", "channels.start", "--params",
         json.dumps({"channel": CHANNEL, "accountId": ACCOUNT}), "--json"]
    )
    if rc != 0:
        return False, f"start rc={rc} {err.strip()[:160]}"

    deadline = time.time() + VERIFY_TIMEOUT
    while time.time() < deadline:
        events, new_offset = read_new_events(int(state.get("log_offset") or 0))
        state["log_offset"] = new_offset
        apply_events(state, events)
        if float(state.get("last_auth_ok") or 0) >= start_ts - 5:
            return True, "authentication successful"
        time.sleep(3)
    return False, f"no authentication within {VERIFY_TIMEOUT}s"


def full_recovery() -> tuple[bool, str]:
    """兜底：走 safe_restart.sh（含 pre-restart guard）。"""
    try:
        proc = subprocess.run(
            ["bash", str(SAFE_RESTART)],
            capture_output=True,
            text=True,
            timeout=300,
            env=ensure_env(),
            cwd=str(WORKSPACE),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        return False, f"safe_restart rc={proc.returncode} {proc.stderr.strip()[:200]}"
    return True, "gateway restart completed"


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def _fmt_ts(value: Any) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromtimestamp(float(value), CST).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return str(value)


def run(mode: str) -> int:
    now = now_ts()
    status = channel_status()
    if status is None:
        log("ERROR", "gateway.unreachable", detail="channels.status failed")
        return 2
    if not gateway_http_ok():
        log("WARN", "gateway.http.not_ok", port=gateway_port(), detail="process may be down")

    state = load_state()
    if not state.get("log_offset"):
        events, offset = seed_events()
        state["log_offset"] = offset
        apply_events(state, events)
    else:
        events, offset = read_new_events(int(state["log_offset"]))
        state["log_offset"] = offset
        apply_events(state, events)

    decision = evaluate(state, status, now)
    summary = {
        "decision": decision,
        "last_auth_ok": _fmt_ts(state.get("last_auth_ok")),
        "last_bad": _fmt_ts(
            max(
                float(state.get("last_conn_lost") or 0),
                float(state.get("last_gave_up") or 0),
                float(state.get("last_reconnect") or 0),
            ) or None
        ),
        "down_since": _fmt_ts(state.get("down_since")),
        "account_running": (status.get("account") or {}).get("running"),
        "account_last_error": (status.get("account") or {}).get("lastError"),
    }

    if mode == "check":
        print(json.dumps(summary, ensure_ascii=False))
        log("INFO", "check", **summary)
        return 0

    action, reason = decide_action(state, decision, status, now)
    summary.update({"action": action, "reason": reason})
    rc = 0

    if action == "light":
        ok, detail = light_recovery(state)
        state["last_recovery_at"] = now
        state["last_recovery_kind"] = "light"
        if ok:
            state["light_count"] = int(state.get("light_count") or 0) + 1
            state["consecutive_light_failures"] = 0
            log("INFO", "recovery.light.ok", **summary, detail=detail)
        else:
            state["consecutive_light_failures"] = int(state.get("consecutive_light_failures") or 0) + 1
            log("WARN", "recovery.light.failed", **summary, detail=detail)
            rc = 3
    elif action == "full":
        ok, detail = full_recovery()
        state["last_recovery_at"] = now
        state["last_recovery_kind"] = "full"
        if ok:
            state["consecutive_light_failures"] = 0
            log("WARN", "recovery.full.ok", **summary, detail=detail)
        else:
            log("ERROR", "recovery.full.failed", **summary, detail=detail)
            rc = 3
    elif action == "alert":
        log("ERROR", "recovery.alert", **summary, reason=reason)
    elif action == "skip":
        log("INFO", "recovery.skip", **summary, reason=reason)
    else:
        log("INFO", "idle", **summary)

    save_state(state)
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Channel 主动恢复兜底")
    parser.add_argument("--recover", action="store_true", help="检测并按需恢复")
    parser.add_argument("--check", action="store_true", help="只判定不动作")
    parser.add_argument("--status", action="store_true", help="打印内部状态")
    args = parser.parse_args()

    if args.status:
        state = load_state()
        state.pop("raw", None)
        print(json.dumps(state, ensure_ascii=False, indent=1))
        return 0

    mode = "recover" if args.recover else "check"
    with Lock():
        return run(mode)


if __name__ == "__main__":
    sys.exit(main())
