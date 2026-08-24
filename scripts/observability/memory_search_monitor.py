#!/usr/bin/env python3
"""L2 记忆语义检索监控 — ADR-009 决策 4 落地实现

背景（2026-08-24 实测教训）：
  `openclaw memory status --index` 会**报告健康而检索实际停摆**。
  当天 status 显示 provider=local / 393 chunks / Embeddings: ready / dims=768 全部正常，
  但 memory_search 实际返回 disabled:true + "index sources changed"，一条都不返回。
  ⇒ **status 不可信，必须实查（behavioral probe）**。

检测原理：
  发一条**与目标文档无关键词重叠**的中文查询，断言返回结果中
  `textScore == 0` 且 `vectorScore > 阈值` —— 这只能由向量召回产生。
  若语义检索降级为 keyword-only，该查询会命中不了或 vectorScore 全为 0。

三态判据（对齐 ADR-008 三态模型 + ADR-009 决策 4）：
  ok        → 有结果且存在 textScore==0 而 vectorScore>阈值 的命中（纯向量召回）
  degraded  → 有结果但全部 vectorScore==0（静默降级为 keyword-only）
  down      → 无结果 / 命令失败 / JSON 解析失败 / 检索被禁用

注意：
  `openclaw memory search --json` 只返回 {"results": [...]}，
  **不含** provider/disabled/debug 字段（实测 2026-08-24）。
  所以不能靠读字段判断，只能靠上述行为断言。
  `memory status --index` 仍作为**辅助**信息采集，但不作为判据。

用法:
    python3 scripts/observability/memory_search_monitor.py            # 人读输出
    python3 scripts/observability/memory_search_monitor.py --json     # 结构化
    python3 scripts/observability/memory_search_monitor.py --jsonl    # 追加日志
    python3 scripts/observability/memory_search_monitor.py --quiet    # 仅异常时输出

退出码:
    0 = ok
    1 = degraded（静默降级）
    2 = down（完全不可用）
    3 = 脚本自身错误
"""

from __future__ import annotations

import argparse
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

# 探针查询：刻意与目标文档无关键词重叠，只能靠语义召回
# 目标：USER.md「Never 把凭据/API key 写到任何 markdown 文件」
# 查询用「密钥泄露/开源代码仓库」—— 与目标文本无共同词，textScore 应为 0
PROBE_QUERY = "如何避免把密钥泄露到开源代码仓库"
VECTOR_SCORE_MIN = 0.35  # 低于此值视为无效召回（实测正常值 ~0.69）

SENSITIVE_PATTERNS = [
    r"(?:api[_-]?key|token|secret|password|credential)\s*[:=]\s*\S+",
    r"ghp_[a-zA-Z0-9]{36}",
    r"tvly-[a-zA-Z0-9_-]{40,}",
    r"ark-[a-zA-Z0-9_-]{20,}",
    r"Bearer\s+\S+",
]


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in SENSITIVE_PATTERNS:
        out = re.sub(pat, "[REDACTED]", out, flags=re.IGNORECASE)
    return out


def run_cli(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def probe_search(agent: str = "main") -> dict:
    """行为探针：实查一条纯语义查询，断言向量召回生效。"""
    rc, out, err = run_cli(
        ["openclaw", "memory", "search", PROBE_QUERY, "--json", "--agent", agent]
    )
    result: dict = {
        "query": PROBE_QUERY,
        "exitCode": rc,
        "state": "down",
        "hits": 0,
        "pureVectorHits": 0,
        "topVectorScore": None,
        "reason": None,
    }

    if rc != 0:
        result["reason"] = f"CLI exit {rc}: {redact(err.strip())[:200]}"
        return result

    # CLI 可能在 JSON 前打印日志行，取第一个 '{' 起的内容
    idx = out.find("{")
    if idx < 0:
        result["reason"] = "no JSON in output"
        return result

    try:
        payload = json.loads(out[idx:])
    except json.JSONDecodeError as exc:
        result["reason"] = f"JSON parse failed: {exc}"
        return result

    # 工具侧会带 disabled/unavailable；CLI 侧目前不带，但兼容将来加上
    if payload.get("disabled") or payload.get("unavailable"):
        result["reason"] = redact(
            str(payload.get("error") or payload.get("warning") or "search disabled")
        )[:200]
        return result

    hits = payload.get("results") or []
    result["hits"] = len(hits)

    if not hits:
        result["reason"] = "probe query returned zero results"
        return result

    vec_scores = [h.get("vectorScore") or 0 for h in hits]
    result["topVectorScore"] = max(vec_scores) if vec_scores else 0

    # 纯向量命中：textScore 为 0（无关键词重叠）但 vectorScore 达阈值
    pure = [
        h
        for h in hits
        if (h.get("textScore") or 0) == 0
        and (h.get("vectorScore") or 0) >= VECTOR_SCORE_MIN
    ]
    result["pureVectorHits"] = len(pure)

    if pure:
        result["state"] = "ok"
        result["topHit"] = f"{pure[0].get('path')}#{pure[0].get('startLine')}"
        return result

    if result["topVectorScore"] and result["topVectorScore"] > 0:
        # 有向量分但没有纯向量命中 —— 可能只是探针查询恰好有词重叠，属弱信号
        result["state"] = "ok"
        result["reason"] = (
            "no zero-textScore hit; vector scoring active but probe overlapped keywords"
        )
        return result

    result["state"] = "degraded"
    result["reason"] = "all vectorScore == 0 (silently degraded to keyword-only)"
    return result


def collect_status(agent: str = "main") -> dict:
    """辅助信息（**不作为判据** —— 实测会报健康而检索停摆）。"""
    rc, out, _ = run_cli(["openclaw", "memory", "status", "--index", "--agent", agent])
    info: dict = {"exitCode": rc, "provider": None, "model": None,
                  "chunks": None, "dims": None, "embeddings": None}
    if rc != 0:
        return info
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Provider:"):
            info["provider"] = s.split(":", 1)[1].strip()
        elif s.startswith("Model:"):
            info["model"] = s.split(":", 1)[1].strip()
        elif s.startswith("Embeddings:"):
            info["embeddings"] = s.split(":", 1)[1].strip()
        elif s.startswith("Vector dims:"):
            info["dims"] = s.split(":", 1)[1].strip()
        elif "chunks" in s and "Indexed:" in s:
            info["chunks"] = s.split(":", 1)[1].strip()
    return info


def build_report(agent: str = "main") -> dict:
    probe = probe_search(agent)
    status = collect_status(agent)

    # 一致性检查：status 说健康但探针失败 —— 正是 2026-08-24 那次故障的特征
    inconsistent = bool(
        probe["state"] != "ok"
        and status.get("embeddings") == "ready"
        and status.get("provider")
    )

    return {
        "ts": datetime.now(CST).isoformat(),
        "agent": agent,
        "state": probe["state"],
        "probe": probe,
        "status": status,
        "statusMisreportsHealth": inconsistent,
    }


def render(report: dict) -> str:
    p = report["probe"]
    s = report["status"]
    icon = {"ok": "✅", "degraded": "⚠️", "down": "❌"}.get(report["state"], "?")
    lines = [
        f"{icon} memory_search: {report['state'].upper()}  ({report['ts']})",
        f"   探针查询   : {p['query']}",
        f"   命中       : {p['hits']} 条，其中纯向量召回 {p['pureVectorHits']} 条",
        f"   最高 vec   : {p['topVectorScore']}",
    ]
    if p.get("topHit"):
        lines.append(f"   证据       : {p['topHit']} (textScore=0)")
    if p.get("reason"):
        lines.append(f"   说明       : {p['reason']}")
    lines.append(
        f"   status辅助 : provider={s.get('provider')} / {s.get('chunks')} / "
        f"dims={s.get('dims')} / embeddings={s.get('embeddings')}"
    )
    if report["statusMisreportsHealth"]:
        lines.append(
            "   🔴 status 报告健康但实查失败 —— 与 2026-08-24 故障特征一致，"
            "先跑 `openclaw memory index --force`"
        )
    return "\n".join(lines)


def append_jsonl(report: dict) -> Path:
    day = datetime.now(CST).strftime("%Y-%m-%d")
    path = LOGS_DIR / f"memory-search-{day}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=False) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(
        description="记忆语义检索监控（ADR-009 决策 4）"
    )
    ap.add_argument("--agent", default="main", help="agent id（默认 main）")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--jsonl", action="store_true", help="追加写 JSONL 日志")
    ap.add_argument("--quiet", action="store_true", help="仅在非 ok 时输出")
    args = ap.parse_args()

    try:
        report = build_report(args.agent)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 监控脚本自身失败: {redact(str(exc))}", file=sys.stderr)
        return 3

    if args.jsonl:
        path = append_jsonl(report)
        if not args.quiet:
            print(f"📝 已写入 {path.relative_to(REPO_ROOT)}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not (args.quiet and report["state"] == "ok"):
        print(render(report))

    return {"ok": 0, "degraded": 1, "down": 2}.get(report["state"], 3)


if __name__ == "__main__":
    sys.exit(main())
