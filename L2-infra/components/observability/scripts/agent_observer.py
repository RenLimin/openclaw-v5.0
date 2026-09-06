#!/usr/bin/env python3
"""L2 可观测性适配 — 最小埋点实现 (阶段 1)

基于 OpenClaw CLI 已有能力:
  - `openclaw sessions list --json`  → 会话元数据 (token 用量/状态/时序)
  - `openclaw cron list --json`      → 调度任务状态
  - `openclaw status --json`         → 系统健康 (可选)

不写 TypeScript plugin，用 Python 脚本 + OpenClaw cron 实现。

用法:
    python3 scripts/observability/agent_observer.py              # 当前会话快照
    python3 scripts/observability/agent_observer.py --daily      # 每日摘要
    python3 scripts/observability/agent_observer.py --jsonl      # 写入 JSONL 日志
    python3 scripts/observability/agent_observer.py --all        # 所有活跃会话
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = REPO_ROOT / "logs" / "observability"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CST = timezone(timedelta(hours=8))

# 敏感字段 (绝不记录到日志)
SENSITIVE_PATTERNS = [
    r"(?:api[_-]?key|token|secret|password|credential)\s*[:=]\s*\S+",
    r"ghp_[a-zA-Z0-9]{36}",
    r"tvly-[a-zA-Z0-9_-]{40,}",
    r"Bearer\s+\S+",
]


def redact(text: str) -> str:
    if not text:
        return text
    for pattern in SENSITIVE_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
    return text


def safe_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def run_cli(args: list[str], *, timeout: int = 30) -> dict | list | None:
    """执行 openclaw CLI 并解析 JSON。"""
    try:
        result = subprocess.run(
            ["openclaw"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=REPO_ROOT,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# 数据采集
# --------------------------------------------------------------------------


def get_sessions(active_minutes: int = 1440) -> list[dict]:
    """获取活跃会话列表。"""
    out = run_cli(
        ["sessions", "list", "--json", "--active", str(active_minutes), "--limit", "100"]
    )
    if not out or not isinstance(out, dict):
        return []
    sessions = out.get("sessions", [])
    now_ms = datetime.now(CST).timestamp() * 1000
    return [
        {
            "key": s.get("key", "?"),
            "sessionId": s.get("sessionId", "?"),
            "kind": s.get("kind", "?"),
            "status": s.get("status", "?"),
            "model": s.get("model", "?"),
            "modelProvider": s.get("modelProvider", "?"),
            "inputTokens": s.get("inputTokens") or 0,
            "outputTokens": s.get("outputTokens") or 0,
            "totalTokens": s.get("totalTokens") or 0,
            "contextTokens": s.get("contextTokens"),
            "abortedLastRun": s.get("abortedLastRun", False),
            "ageMs": s.get("ageMs", 0),
            "updatedAt": s.get("updatedAt"),
            "sessionStartedAt": s.get("sessionStartedAt"),
            "lastInteractionAt": s.get("lastInteractionAt"),
        }
        for s in sessions
    ]


def get_cron_jobs() -> list[dict]:
    """获取 cron 任务列表。"""
    out = run_cli(["cron", "list", "--json"])
    if not out:
        return []
    if isinstance(out, dict):
        jobs = out.get("jobs", [])
    elif isinstance(out, list):
        jobs = out
    else:
        return []
    return [
        {
            "name": j.get("displayName") or j.get("name", "?"),
            "enabled": j.get("enabled", False),
            "schedule_kind": (j.get("schedule") or {}).get("kind", "?"),
            "schedule_expr": (j.get("schedule") or {}).get("expr", ""),
            "lastRunStatus": (j.get("state") or {}).get("lastRunStatus", "unknown"),
            "sessionTarget": j.get("sessionTarget", "?"),
        }
        for j in jobs
    ]


# --------------------------------------------------------------------------
# 事件生成
# --------------------------------------------------------------------------


def generate_session_snapshot(session: dict) -> dict:
    """为单个会话生成观测快照。"""
    return {
        "timestamp": datetime.now(CST).isoformat(),
        "level": "info",
        "component": "agent",
        "event": "session_snapshot",
        "trace_id": safe_hash(session["key"]),
        "session_key": session["key"],
        "session_kind": session["kind"],
        "status": session["status"],
        "model": session["model"],
        "model_provider": session["modelProvider"],
        "attributes": {
            "gen_ai.agent.input_tokens": session["inputTokens"],
            "gen_ai.agent.output_tokens": session["outputTokens"],
            "gen_ai.agent.total_tokens": session["totalTokens"],
            "gen_ai.agent.context_tokens": session["contextTokens"],
            "gen_ai.agent.aborted_last_run": session["abortedLastRun"],
            "gen_ai.agent.age_ms": session["ageMs"],
        },
    }


def generate_daily_summary() -> dict:
    """生成每日观测摘要。"""
    now = datetime.now(CST)
    sessions = get_sessions(active_minutes=1440)
    cron_jobs = get_cron_jobs()

    total_input = sum(s["inputTokens"] for s in sessions)
    total_output = sum(s["outputTokens"] for s in sessions)
    total_tokens = sum(s["totalTokens"] for s in sessions)
    aborted = sum(1 for s in sessions if s["abortedLastRun"])

    return {
        "timestamp": now.isoformat(),
        "level": "info",
        "component": "observability",
        "event": "daily_summary",
        "period": "24h",
        "date": now.strftime("%Y-%m-%d"),
        "summary": {
            "active_sessions": len(sessions),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_tokens,
            "aborted_sessions": aborted,
            "cron_jobs": len(cron_jobs),
            "cron_enabled": sum(1 for j in cron_jobs if j["enabled"]),
        },
        "sessions": [
            {
                "key": s["key"],
                "model": s["model"],
                "totalTokens": s["totalTokens"],
                "status": s["status"],
            }
            for s in sessions
        ],
        "cron": cron_jobs,
    }


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------


def write_jsonl(event: dict) -> Path:
    """写入 JSONL 日志文件。"""
    date_str = datetime.now(CST).strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{date_str}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return log_file


def format_human(event: dict) -> str:
    """人类可读格式。"""
    lines = []
    if event["event"] == "daily_summary":
        s = event["summary"]
        lines += [
            f"📊 每日观测摘要 ({event['date']})",
            f"  活跃会话: {s['active_sessions']}",
            f"  总 token: {s['total_tokens']:,} (in: {s['total_input_tokens']:,} / out: {s['total_output_tokens']:,})",
            f"  异常中断: {s['aborted_sessions']}",
            f"  Cron 任务: {s['cron_enabled']}/{s['cron_enabled']} 启用",
        ]
        if event.get("sessions"):
            lines.append("  会话明细:")
            for sess in event["sessions"]:
                lines.append(
                    f"    - {sess['key'][:30]} | {sess['model']} | "
                    f"{sess['totalTokens']:,} tokens | {sess['status']}"
                )
    elif event["event"] == "session_snapshot":
        a = event["attributes"]
        lines += [
            f"🔍 会话快照 ({event['session_key'][:40]})",
            f"  状态: {event['status']} | 模型: {event['model']}",
            f"  Token: {a['gen_ai.agent.total_tokens']:,} (in: {a['gen_ai.agent.input_tokens']:,} / out: {a['gen_ai.agent.output_tokens']:,})",
            f"  异常中断: {a['gen_ai.agent.aborted_last_run']}",
        ]
    else:
        lines.append(json.dumps(event, ensure_ascii=False, indent=2))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="L2 可观测性 — agent 观测脚本")
    parser.add_argument("--daily", action="store_true", help="生成每日摘要")
    parser.add_argument("--jsonl", action="store_true", help="写入 JSONL 日志")
    parser.add_argument("--all", action="store_true", help="所有活跃会话快照")
    args = parser.parse_args()

    if args.daily:
        event = generate_daily_summary()
    elif args.all:
        sessions = get_sessions(active_minutes=1440)
        if not sessions:
            print("⚠️ 近 24h 无活跃会话")
            return 0
        for s in sessions:
            evt = generate_session_snapshot(s)
            if args.jsonl:
                write_jsonl(evt)
            print(format_human(evt))
            print()
        return 0
    else:
        sessions = get_sessions(active_minutes=60)
        if not sessions:
            print("⚠️ 近 1 小时无活跃会话")
            return 0
        # 取最近更新的
        sessions.sort(key=lambda s: s.get("updatedAt") or 0, reverse=True)
        event = generate_session_snapshot(sessions[0])

    if args.jsonl:
        path = write_jsonl(event)
        print(f"✅ 已写入 {path.relative_to(REPO_ROOT)}")

    print(format_human(event))
    return 0


if __name__ == "__main__":
    sys.exit(main())
