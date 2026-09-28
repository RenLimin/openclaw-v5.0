#!/usr/bin/env python3
"""会话上下文水位预警脚本。

扫描所有 active 会话的 token 用量，按 ctx 占比分级告警：
- WARN  (>=70%): 提醒尽早 /compact
- CRIT  (>=85%): 强烈建议立即 /compact，否则有触发 /compact 失败 → /reset 死局的风险
- DEAD  (>=100%): 已超限，任何模型都装不下，只剩 /reset

设计依据（2026-09-28 /compact 失败复盘）：
- 会话膨胀到 1.05M tokens 超过 LongCat-2.0 的 1M ctx 后，/compact 压缩请求本身
  也装不下，唯一出路是 /reset。预警必须在 70-85% 区间提前介入。

数据源: `openclaw sessions list --json`（totalTokens / model ctx）
输出: stdout JSON 报告 + memory/session-ctx-watch-latest.json
退出码: 0=正常, 1=有 WARN, 2=有 CRIT/DEAD
"""
import json
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[3]
OUT_FILE = WORKSPACE / "memory" / "session-ctx-watch-latest.json"

# 各模型真实 ctx（2026-09-28 实测校准：deepseek-v4-flash-ga 850k prompt 200 OK）
CTX_BY_MODEL = {
    "longcat/LongCat-2.0": 1048576,
    "LongCat-2.0": 1048576,
    "coding-plan/deepseek-v4-flash-ga-260731": 1048576,
    "deepseek-v4-flash-ga-260731": 1048576,
    "model-scheduling/auto": 262144,
    "auto": 262144,
    "coding-plan/doubao-seed-2-1-turbo": 262144,
    "doubao-seed-2-1-turbo": 262144,
    "coding-plan/doubao-seed-2-0-lite-260215": 262144,
    "coding-plan/doubao-seed-code-preview-251028": 262144,
    "coding-plan/doubao-seed-2-0-pro-260215": 262144,
    "coding-plan/doubao-seed-2-1-pro-260628": 262144,
}
DEFAULT_CTX = 131072  # 未知模型按保守值
WARN_THRESHOLD = 0.70
CRIT_THRESHOLD = 0.85


def classify(pct: float) -> str:
    if pct >= 1.0:
        return "DEAD"
    if pct >= CRIT_THRESHOLD:
        return "CRIT"
    if pct >= WARN_THRESHOLD:
        return "WARN"
    return "OK"


def main() -> int:
    result = subprocess.run(
        ["openclaw", "sessions", "list", "--json", "--limit", "100"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        print(json.dumps({"error": f"sessions list failed: {result.stderr[:200]}"}, ensure_ascii=False))
        return 2
    data = json.loads(result.stdout)
    sessions = data.get("sessions", [])

    findings, worst = [], "OK"
    for s in sessions:
        key = s.get("key", "?")
        model = s.get("model", "")
        total = s.get("totalTokens") or 0
        ctx = CTX_BY_MODEL.get(model, DEFAULT_CTX)
        # unknown tokens 无法判断，跳过但记录
        if not s.get("totalTokensFresh", False) and total == 0:
            continue
        pct = total / ctx if ctx else 0
        level = classify(pct)
        if level != "OK":
            findings.append({
                "session": key, "model": model, "tokens": total,
                "ctx": ctx, "pct": round(pct * 100, 1), "level": level,
            })
        if {"OK": 0, "WARN": 1, "CRIT": 2, "DEAD": 3}[level] > {"OK": 0, "WARN": 1, "CRIT": 2, "DEAD": 3}[worst]:
            worst = level

    report = {
        "timestamp": subprocess.run(["date", "-Iseconds"], capture_output=True, text=True).stdout.strip(),
        "scanned": len(sessions),
        "worst": worst,
        "findings": findings,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=1))

    print(json.dumps(report, ensure_ascii=False))
    return {"OK": 0, "WARN": 1, "CRIT": 2, "DEAD": 2}[worst]


if __name__ == "__main__":
    sys.exit(main())
