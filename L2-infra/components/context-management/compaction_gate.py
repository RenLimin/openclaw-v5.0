#!/usr/bin/env python3
"""
压缩健康门禁（compaction-gate）— 把「压缩静默失败」变成可观测、可退出码消费的信号

问题背景（事故 2026-11-26，gateway.log 实证）：
- `agents.defaults.compaction.mode = safeguard`：压缩失败时「宁可不压也不丢」，
  失败后没有强制重试，**当轮任务即中断且不自动续跑**。
- `[compaction-diag] end outcome=failed/error` 累计 600+ 条，
  而 `auto-compaction succeeded` 历史仅个位数——失败是常态，成功是少数。
- 典型失败：`errorMessage="Session maintenance yielded to a foreground turn"`。
- 既有 `auto_recovery.py` 只看 token 使用率（实测长期 30% 无需恢复），
  无法发现这类「失败但没到阈值」的静默中断。

本脚本职责边界：
- 默认**只读**：解析 gateway.log 尾部（有字节上限，不全量读 77MB+），按 sessionKey
  统计窗口内 failed/error 次数与最后一次成功时间，输出结构化报告。
- 判定：窗口内失败 >= threshold 且期间无成功补偿 → alert（rc=1）；
  失败 >= 2×threshold → critical（rc=2）。
- `--fix`：对告警会话调用 `openclaw sessions compact <key>` 尝试恢复
  （走绝对路径，不依赖 launchd PATH）。带 `--exclude`（跳过前台会话等）、
  `--fix-cooldown-minutes`（冷却期内不重复 fix）、`--max-fix-per-run`（单轮上限）。
- `--silent-ok`：ok 且无修复动作时零输出——供 automation 消费，
  借「空输出抑制投递」只在异常时打扰。
- 状态落盘 `logs/compaction-gate-state.json`：记住各会话最后一次成功时间，
  供跨运行判定「失败后是否已恢复」。

设计依据：L2-infra/components/context-management/DESIGN.md §压缩健康门禁（2026-11-26 增补）。
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_LOG = Path.home() / "Library" / "Logs" / "openclaw" / "gateway.log"
DEFAULT_STATE_DIR = Path(__file__).resolve().parent / "logs"
STATE_FILE_NAME = "compaction-gate-state.json"
DEFAULT_FIX_COOLDOWN_MINUTES = 60
DEFAULT_MAX_FIX_PER_RUN = 2

DIAG_END_RE = re.compile(
    r"^(?P<ts>\S+) \[agent/embedded\] \[compaction-diag\] end\s+(?P<rest>.+)$"
)
SUCCESS_RE = re.compile(
    r"^(?P<ts>\S+) \[agent/embedded\] auto-compaction succeeded for (?P<model>\S+);"
)
SAFEGUARD_RE = re.compile(
    r"^(?P<ts>\S+) \[compaction-safeguard\] Compaction safeguard: "
    r"finalized artifact truncated; loss=(?P<loss>\S+)"
)
KV_RE = re.compile(r"(\w+)=(\S+)")

FAIL_OUTCOMES = {"failed", "error"}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def resolve_openclaw_bin() -> str:
    """外部 CLI 一律绝对路径（AGENTS.md §LaunchAgent PATH 红线）。"""
    return (
        shutil.which("openclaw")
        or "/opt/homebrew/bin/openclaw"
    )


def tail_text(path: Path, max_bytes: int) -> str:
    """读日志尾部。仅当真的发生截断时才丢弃可能不完整的首行；
    小文件整读，避免「首行被误删」的 off-by-one（回归测试曾抓到）。"""
    size = path.stat().st_size
    with open(path, "rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
            data = fh.read()
            nl = data.find(b"\n")
            body = data[nl + 1:] if nl != -1 else data
        else:
            body = fh.read()
    return body.decode("utf-8", errors="replace")


def load_state(state_path: Path) -> dict:
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def record_global_success(state_path: Path, events: dict) -> None:
    """把窗口内观察到的压缩成功写入 state（成功行无 sessionKey，按全局记录）。

    修复（2026-11-26）：此前 remember_success/save_state 定义但从未被调用，
    state 永不落盘，「失败后是否已恢复」的补偿判定形同虚设。
    """
    if not events.get("successes"):
        return
    state = load_state(state_path)
    state.setdefault("last_success", {})
    newest = max(parse_ts(s["ts"]) for s in events["successes"])
    prev = state["last_success"].get("*global*")
    if prev is None or parse_ts(prev) < newest:
        state["last_success"]["*global*"] = newest.isoformat()
    save_state(state_path, state)


def scan_log(log_path: Path, now: datetime, window: timedelta, max_bytes: int) -> dict:
    """解析窗口内事件：失败明细 / 成功时刻 / safeguard 截断。"""
    text = tail_text(log_path, max_bytes)
    failures, successes, truncations = [], [], []
    for line in text.splitlines():
        m = DIAG_END_RE.match(line)
        if m:
            kv = dict(KV_RE.findall(m.group("rest")))
            if kv.get("outcome") in FAIL_OUTCOMES:
                ts = parse_ts(m.group("ts"))
                if ts >= now - window:
                    failures.append(
                        {
                            "ts": ts.isoformat(),
                            "session_key": kv.get("sessionKey"),
                            "diag_id": kv.get("diagId"),
                            "reason": kv.get("reason"),
                            "detail": kv.get("detail"),
                        }
                    )
            continue
        m = SUCCESS_RE.match(line)
        if m:
            ts = parse_ts(m.group("ts"))
            if ts >= now - window:
                successes.append(
                    {"ts": ts.isoformat(), "model": m.group("model")}
                )
            continue
        m = SAFEGUARD_RE.match(line)
        if m:
            ts = parse_ts(m.group("ts"))
            if ts >= now - window:
                truncations.append(
                    {"ts": ts.isoformat(), "loss": m.group("loss")}
                )
    return {
        "failures": sorted(failures, key=lambda x: x["ts"]),
        "successes": sorted(successes, key=lambda x: x["ts"]),
        "truncations": sorted(truncations, key=lambda x: x["ts"]),
    }


def evaluate(events: dict, state: dict, threshold: int) -> dict:
    """按 sessionKey 聚合判定。成功补偿 = 任一成功时刻晚于该会话最近一次失败。

    修复（2026-11-26）：成功行不带 sessionKey，统一按全局最后成功时刻参与判定；
    此前 state 从不落盘 + 窗口成功不参与抑制，「无成功补偿」判定形同虚设。
    """
    remembered = {
        k: parse_ts(v) for k, v in state.get("last_success", {}).items()
    }
    all_success = list(remembered.values()) + [
        parse_ts(s["ts"]) for s in events["successes"]
    ]
    global_success = max(all_success) if all_success else None

    per_session: dict[str, dict] = {}
    for f in events["failures"]:
        key = f["session_key"] or "unknown"
        slot = per_session.setdefault(key, {"failures": []})
        slot["failures"].append(f)

    sessions = []
    for key, slot in per_session.items():
        failures = slot["failures"]
        status = "ok"
        if len(failures) >= threshold:
            unrecovered = (
                global_success is None
                or global_success < parse_ts(failures[-1]["ts"])
            )
            if unrecovered:
                status = "critical" if len(failures) >= threshold * 2 else "alert"
        sessions.append(
            {
                "session_key": key,
                "status": status,
                "failure_count": len(failures),
                "failures": failures[:20],
                "last_success": global_success.isoformat() if global_success else None,
            }
        )
    overall = "ok"
    if any(s["status"] == "alert" for s in sessions):
        overall = "alert"
    if any(s["status"] == "critical" for s in sessions):
        overall = "critical"
    return {
        "overall": overall,
        "sessions": sorted(sessions, key=lambda x: x["session_key"]),
        "truncation_events": events["truncations"],
    }


def try_fix(session_keys: list[str]) -> list[dict]:
    """调用 sessions compact 尝试恢复（不改 gateway 进程）。

    global key（agent:<agent>:<session>）需带 --agent，由 key 前缀推导。
    """
    bin_path = resolve_openclaw_bin()
    results = []
    for key in session_keys:
        cmd = [bin_path, "sessions", "compact", key]
        parts = key.split(":")
        if len(parts) >= 3 and parts[0] == "agent":
            cmd += ["--agent", parts[1]]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        results.append(
            {
                "session_key": key,
                "rc": proc.returncode,
                "stdout": (proc.stdout or "").strip()[-400:],
                "stderr": (proc.stderr or "").strip()[-400:],
            }
        )
    return results


def build_report(
    log_path: Path,
    *,
    now: datetime | None = None,
    window_minutes: int = 60,
    threshold: int = 2,
    max_bytes: int = 32 * 1024 * 1024,
    state_path: Path | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    state_path = state_path or DEFAULT_STATE_DIR / STATE_FILE_NAME
    state = load_state(state_path)
    events = scan_log(log_path, now, timedelta(minutes=window_minutes), max_bytes)
    report = evaluate(events, state, threshold)
    report.update(
        {
            "generated_at": now.isoformat(),
            "log": str(log_path),
            "window_minutes": window_minutes,
            "threshold": threshold,
        }
    )
    # 落盘：窗口内观察到的成功归因不到具体会话，推进全局兜底（修复死代码）。
    record_global_success(state_path, events)
    report["state_path"] = str(state_path)
    return report


def remember_success(state_path: Path, key: str, ts: datetime) -> None:
    state = load_state(state_path)
    state.setdefault("last_success", {})
    prev = state["last_success"].get(key)
    if prev is None or parse_ts(prev) < ts:
        state["last_success"][key] = ts.isoformat()
    save_state(state_path, state)


def main(argv: list[str] | None = None, *, state_dir: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="压缩健康门禁（只读检测，--fix 才动作）")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="gateway 日志路径")
    parser.add_argument(
        "--state-dir", default=str(state_dir or DEFAULT_STATE_DIR), help="状态文件目录"
    )
    parser.add_argument("--window-minutes", type=int, default=60)
    parser.add_argument("--threshold", type=int, default=2)
    parser.add_argument("--max-bytes", type=int, default=32 * 1024 * 1024)
    parser.add_argument("--fix", action="store_true", help="对告警会话执行 compact 恢复")
    parser.add_argument(
        "--exclude", default="",
        help="逗号分隔的 sessionKey 子串，跳过自动修复（如 agent:main:main）",
    )
    parser.add_argument(
        "--fix-cooldown-minutes", type=int, default=DEFAULT_FIX_COOLDOWN_MINUTES,
        help="同一会话两次自动修复的最小间隔（默认 60）",
    )
    parser.add_argument(
        "--max-fix-per-run", type=int, default=DEFAULT_MAX_FIX_PER_RUN,
        help="单轮最多自动修复的会话数（默认 2）",
    )
    parser.add_argument(
        "--silent-ok", action="store_true",
        help="ok 且无修复动作时零输出（供 automation 空输出抑制投递）",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"❌ 日志不存在: {log_path}", file=sys.stderr)
        return 2

    state_path = Path(args.state_dir) / STATE_FILE_NAME
    report = build_report(
        log_path,
        window_minutes=args.window_minutes,
        threshold=args.threshold,
        max_bytes=args.max_bytes,
        state_path=state_path,
    )

    fix_results = []
    if args.fix:
        excludes = [e for e in args.exclude.split(",") if e.strip()]
        cooldown = load_state(state_path).get("last_fix_attempt", {})
        now_dt = datetime.now(timezone.utc)
        targets = []
        for s in report["sessions"]:
            key = s["session_key"]
            if s["status"] not in ("alert", "critical") or key == "unknown":
                continue
            if any(e in key for e in excludes):
                continue
            last = cooldown.get(key)
            if last and now_dt - parse_ts(last) < timedelta(
                minutes=args.fix_cooldown_minutes
            ):
                continue
            targets.append(key)
        targets = targets[: args.max_fix_per_run]
        if targets:
            fix_results = try_fix(targets)
            # 冷却与成功记忆落盘：失败也记录尝试，避免对同一会话反复打
            state = load_state(state_path)
            state.setdefault("last_fix_attempt", {})
            state.setdefault("last_success", {})
            for key, r in zip(targets, fix_results):
                state["last_fix_attempt"][key] = now_dt.isoformat()
                if r["rc"] == 0:
                    remember_success(state_path, key, now_dt)
                    state["last_success"][key] = now_dt.isoformat()
            save_state(state_path, state)
            report = build_report(
                log_path,
                window_minutes=args.window_minutes,
                threshold=args.threshold,
                max_bytes=args.max_bytes,
                state_path=state_path,
            )
            report["fix_results"] = fix_results

    exit_code = {"ok": 0, "alert": 1, "critical": 2}[report["overall"]]
    report["exit_code"] = exit_code

    if args.silent_ok and report["overall"] == "ok" and not fix_results:
        return 0

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        icon = {"ok": "✅", "alert": "⚠️", "critical": "❌"}[report["overall"]]
        print(
            f"{icon} 压缩健康门禁: {report['overall'].upper()} "
            f"(窗口 {args.window_minutes}min, 阈值 {args.threshold}, "
            f"safeguard 截断 {len(report['truncation_events'])} 次)"
        )
        for s in report["sessions"]:
            print(
                f"  [{s['status']:<8}] {s['session_key']} "
                f"失败 {s['failure_count']} 次, 最后成功 {s['last_success'] or '无记录'}"
            )
        if fix_results:
            for r in fix_results:
                print(f"  🔧 fix {r['session_key']}: rc={r['rc']}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
