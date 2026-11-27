#!/usr/bin/env python3
"""memory-promotion-gate: L2 记忆晋升门禁 CLI。

解决 OpenClaw memory-core dreaming 的晋升死锁（详见组件 DESIGN.md）：
以 `openclaw memory search` 命中次数作为 recalls 信号，对
memory/dreaming/{light,deep}/*.md 候选做跨日累积评分，
低风险候选幂等追加进 MEMORY.md，高风险只输出待确认清单。

默认 --dry-run（不写盘）。--apply 为 fail-closed：无任何 recalls 信号时退出码 2。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---- 常量（与 DESIGN.md §4/§5 一致）----
PROMOTE_MIN_SCORE = 0.30
MIN_DAYS_SEEN = 2
WEIGHTS = {"recalls": 0.40, "days": 0.25, "confidence": 0.20, "occ": 0.15}
PROBE_LIMIT_DEFAULT = 50
PROBE_MAX_RESULTS = 5
RECALL_LOG_DENOMINATOR = 6.0
OCC_CAP = 10
DAYS_CAP = 7
MARKER_RE = re.compile(r"<!--\s*dream-promoted:\s*([0-9a-f]{12})\s*-->")
STATE_VERSION = 1

HIGH_RISK_PATTERNS = [
    r"password|passwd|token|secret|api[_\-]?key|cookie|credential|私钥|凭据",
    r"合同金额|付款|发票|税率|对公账户|银行账号|授信|结算账户|金额\s*[：:]\s*\d",
    r"身份证|护照|手机号|银行卡|身份证号",
    r"不可逆|force[\s\-]?push|删除生产|drop\s+table",
]
LOW_RISK_PATTERNS = [
    r"命名|口径|约定|术语|规范",
    r"模板|template|版式",
    r"流程|步骤|顺序|SOP",
    r"命令|CLI|脚本|入口",
]
NOISE_PATTERNS = [
    r"^(assistant|user):\s*[✅✔️]?\s*session reset",
    r"^(assistant|user):\s*/reset",
    r"^(assistant|user):\s*hi\b",
    r"^(assistant|user):\s*jerry[，,]\s*(继续|continue)",
    r"^(assistant|user):\s*删除 \d+，失败 \d+\s*$",
]

CANDIDATE_RE = re.compile(
    r"^- Candidate:\s*(?P<snippet>.*?)\s*$"
    r"\n  - confidence:\s*(?P<confidence>[\d.]+)"
    r"\n  - evidence:\s*(?P<evidence>\S+)"
    r"\n  - recalls:\s*(?P<recalls>\d+)"
    r"\n  - status:\s*(?P<status>\w+)",
    re.MULTILINE,
)


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def fingerprint(snippet: str) -> str:
    return hashlib.sha1(norm_text(snippet).encode("utf-8")).hexdigest()[:12]


def resolve_workspace(explicit: str | None) -> Path:
    """定位工作区根：显式参数 > 环境变量 > 从 cwd 向上找 memory/dreaming。"""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            raise SystemExit(f"workspace not found: {p}")
        return p
    env = os.environ.get("OPENCLAW_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    cur = Path.cwd().resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "memory" / "dreaming").is_dir():
            return cand
    raise SystemExit("cannot locate workspace (no memory/dreaming); pass --workspace")


def resolve_openclaw_bin() -> str:
    """绝对路径兜底（AGENTS.md 定时任务红线：禁止裸命令名依赖 PATH）。"""
    found = shutil.which("openclaw")
    if found:
        return found
    for candidate in ("/opt/homebrew/bin/openclaw", "/usr/local/bin/openclaw"):
        if Path(candidate).exists():
            return candidate
    raise SystemExit("openclaw binary not found")


def parse_candidates(workspace: Path) -> list[dict]:
    """解析 light/deep 报告中的 - Candidate: 块。"""
    out: list[dict] = []
    for phase in ("light", "deep"):
        d = workspace / "memory" / "dreaming" / phase
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            for m in CANDIDATE_RE.finditer(text):
                ev = m.group("evidence")
                path_part, _, rng = ev.rpartition(":")
                start = end = ""
                if "-" in rng:
                    start, _, end = rng.partition("-")
                out.append(
                    {
                        "snippet": m.group("snippet").strip(),
                        "confidence": float(m.group("confidence")),
                        "evidence_path": path_part,
                        "evidence_start": start,
                        "evidence_end": end,
                        "report_recalls": int(m.group("recalls")),
                        "status": m.group("status"),
                        "day": f.stem,
                        "phase": phase,
                    }
                )
    return out


def accumulate(raw: list[dict]) -> dict[str, dict]:
    """按指纹跨日累积：days_seen / occurrences / evidence / 平均置信度。"""
    acc: dict[str, dict] = {}
    for c in raw:
        fp = fingerprint(c["snippet"])
        e = acc.setdefault(
            fp,
            {
                "fingerprint": fp,
                "snippet": c["snippet"],
                "conf_sum": 0.0,
                "conf_n": 0,
                "days": [],
                "occurrences": 0,
                "evidence": [],
                "report_recalls": 0,
                "phases": [],
            },
        )
        if c["day"] not in e["days"]:
            e["days"].append(c["day"])
        e["occurrences"] += 1
        e["conf_sum"] += c["confidence"]
        e["conf_n"] += 1
        ev = f"{c['evidence_path']}:{c['evidence_start']}-{c['evidence_end']}"
        if ev not in e["evidence"]:
            e["evidence"].append(ev)
        e["report_recalls"] = max(e["report_recalls"], c["report_recalls"])
        if c["phase"] not in e["phases"]:
            e["phases"].append(c["phase"])
    for e in acc.values():
        e["avg_confidence"] = round(e["conf_sum"] / max(1, e["conf_n"]), 4)
        e["days_seen"] = len(e["days"])
    return acc


def is_noise(snippet: str) -> bool:
    """临时会话噪音（reset/寒暄/进度回执）不得自动晋升——否则 MEMORY.md 被污染。"""
    text = norm_text(snippet)
    return any(re.search(pat, text, re.IGNORECASE | re.MULTILINE) for pat in NOISE_PATTERNS)


def classify_risk(snippet: str) -> str:
    text = norm_text(snippet)
    for pat in HIGH_RISK_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "high"
    for pat in LOW_RISK_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "low"
    return "medium"


def score_candidate(entry: dict, recalls: int) -> dict:
    recalls_norm = _log_norm(recalls, RECALL_LOG_DENOMINATOR)
    days_norm = min(entry["days_seen"], DAYS_CAP) / DAYS_CAP
    occ_norm = min(entry["occurrences"], OCC_CAP) / OCC_CAP
    conf = max(0.0, min(1.0, entry["avg_confidence"]))
    score = (
        WEIGHTS["recalls"] * recalls_norm
        + WEIGHTS["days"] * days_norm
        + WEIGHTS["confidence"] * conf
        + WEIGHTS["occ"] * occ_norm
    )
    return {
        **{k: v for k, v in entry.items() if k not in ("conf_sum", "conf_n")},
        "noise": is_noise(entry["snippet"]),
        "recalls": int(recalls),
        "score": round(score, 4),
        "risk": classify_risk(entry["snippet"]),
    }


def _log_norm(value: float, denom: float) -> float:
    import math

    return math.log1p(max(0.0, value)) / math.log1p(denom)


def _parse_search_json(stdout: str) -> list[dict]:
    """openclaw memory search --json 的 stdout 前面可能有日志行，取最外层 JSON。"""
    start = stdout.find("{")
    if start < 0:
        return []
    try:
        data = json.loads(stdout[start:])
    except json.JSONDecodeError:
        # 退化：截到最后一个 }
        end = stdout.rfind("}")
        if end <= start:
            return []
        try:
            data = json.loads(stdout[start : end + 1])
        except json.JSONDecodeError:
            return []
    return list(data.get("results") or [])


def _token_overlap(candidate_snippet: str, other_snippet: str) -> float:
    a = set(re.findall(r"[a-z0-9一-鿿]+", norm_text(candidate_snippet)))
    b = set(re.findall(r"[a-z0-9一-鿿]+", norm_text(other_snippet)))
    if not a:
        return 0.0
    return len(a & b) / len(a)


def probe_recalls(
    entries: list[dict],
    bin_path: str,
    workspace: Path,
    max_results: int = PROBE_MAX_RESULTS,
    limit: int = PROBE_LIMIT_DEFAULT,
    query_fn=None,
) -> dict[str, int]:
    """对候选做 memory_search 召回探测，返回 {fingerprint: recalls}。

    query_fn 可注入用于测试；生产用 openclaw memory search --json。
    命中判定：result.source == "memory" 且（与候选 snippet token 覆盖率>=0.5 或 同 evidence 路径）。
    """
    ranked = sorted(entries, key=lambda e: (e["days_seen"], e["occurrences"]), reverse=True)
    targets = ranked[: max(0, limit)]
    out: dict[str, int] = {}
    for e in targets:
        query = e["snippet"][:120]
        if query_fn is not None:
            results = query_fn(query, max_results)
        else:
            results = _run_search(bin_path, query, max_results)
        hits = 0
        for r in results:
            if r.get("source") != "memory":
                continue
            path = str(r.get("path") or "")
            evidence_path = next(
                (ev.rpartition(":")[0] for ev in e.get("evidence", []) if ":" in ev), ""
            )
            if evidence_path and path.endswith(evidence_path):
                hits += 1
                continue
            if _token_overlap(e["snippet"], str(r.get("snippet") or "")) >= 0.5:
                hits += 1
        out[e["fingerprint"]] = hits
    return out


def _run_search(bin_path: str, query: str, max_results: int) -> list[dict]:
    try:
        proc = subprocess.run(
            [bin_path, "memory", "search", "--query", query,
             "--max-results", str(max_results), "--json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0:
        return []
    return _parse_search_json(proc.stdout)


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "candidates" in data:
                return data
        except json.JSONDecodeError:
            pass
    return {"version": STATE_VERSION, "updatedAt": None, "candidates": {}, "probe_cache": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updatedAt"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def build_plan(
    workspace: Path,
    scored: list[dict],
    min_score: float,
    min_days: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    promotable, blocked, pending_review = [], [], []
    for e in scored:
        if e["risk"] == "high":
            pending_review.append(e)
            continue
        if e.get("noise"):
            blocked.append(e)
            continue
        if e["score"] >= min_score and e["days_seen"] >= min_days:
            promotable.append(e)
        elif e["recalls"] > 0:
            blocked.append(e)
    promotable.sort(key=lambda e: (-e["score"], -e["recalls"]))
    return promotable, blocked, pending_review


def read_existing_markers(memory_path: Path) -> set[str]:
    if not memory_path.exists():
        return set()
    return set(MARKER_RE.findall(memory_path.read_text(encoding="utf-8", errors="replace")))


def render_entry(e: dict) -> str:
    ev = e["evidence"][0] if e["evidence"] else ""
    return (
        f"<!-- dream-promoted: {e['fingerprint']} -->\n"
        f"- {e['snippet']}  (evidence: {ev}; recalls={e['recalls']}; score={e['score']})\n"
    )


def apply_plan(workspace: Path, promotable: list[dict], state_path: Path, state: dict) -> int:
    memory_path = workspace / "MEMORY.md"
    if not memory_path.exists():
        raise SystemExit(f"MEMORY.md not found: {memory_path}")
    existing = read_existing_markers(memory_path)
    body = memory_path.read_text(encoding="utf-8", errors="replace")
    new_entries = [e for e in promotable if e["fingerprint"] not in existing]
    if not new_entries:
        return 0
    section = "\n## Dreaming 晋升（自动 · memory-promotion-gate）\n\n"
    block = section + "".join(render_entry(e) for e in new_entries)
    if not body.endswith("\n"):
        block = "\n" + block
    memory_path.write_text(body.rstrip("\n") + "\n" + block, encoding="utf-8")
    for e in new_entries:
        state["candidates"][e["fingerprint"]] = {
            "snippet": e["snippet"],
            "score": e["score"],
            "recalls": e["recalls"],
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }
    save_state(state_path, state)
    return len(new_entries)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="memory-promotion-gate CLI")
    ap.add_argument("--workspace")
    ap.add_argument("--dry-run", action="store_true", help="默认；不写盘")
    ap.add_argument("--apply", action="store_true", help="实际写入 MEMORY.md")
    ap.add_argument("--stats", action="store_true", help="仅统计")
    ap.add_argument("--min-score", type=float, default=PROMOTE_MIN_SCORE)
    ap.add_argument("--min-days", type=int, default=MIN_DAYS_SEEN)
    ap.add_argument("--probe-limit", type=int, default=PROBE_LIMIT_DEFAULT)
    ap.add_argument("--max-results", type=int, default=PROBE_MAX_RESULTS)
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not (args.dry_run or args.apply or args.stats):
        args.dry_run = True
    if args.apply and args.dry_run:
        ap.error("--apply 与 --dry-run 互斥")

    ws = resolve_workspace(args.workspace)
    state_path = Path(__file__).resolve().parents[1] / "state" / "scores.json"
    state = load_state(state_path)

    raw = parse_candidates(ws)
    acc = accumulate(raw)
    entries = list(acc.values())

    degraded = False
    if args.no_probe or args.stats:
        recalls_map = {e["fingerprint"]: int(state.get("probe_cache", {}).get(e["fingerprint"], {}).
                       get("recalls", e["report_recalls"])) for e in entries}
    else:
        bin_path = resolve_openclaw_bin()
        cache = state.setdefault("probe_cache", {})
        recalls_map = {}
        for e in entries:
            fp = e["fingerprint"]
            cached = cache.get(fp)
            if cached and cached.get("recalls") is not None and not args.apply:
                recalls_map[fp] = int(cached["recalls"])
                continue
            recalls_map[fp] = 0  # 先占位；下方批量探测覆盖
        probed = {} if args.no_probe else probe_recalls(
            entries, bin_path, ws, max_results=args.max_results, limit=args.probe_limit
        )
        for fp, n in probed.items():
            recalls_map[fp] = n
            cache[fp] = {"recalls": n, "checked_at": datetime.now(timezone.utc).isoformat()}
        degraded = not probed and bool(entries)

    scored = [score_candidate(e, recalls_map.get(e["fingerprint"], 0)) for e in entries]
    with_recalls = [e for e in scored if e["recalls"] > 0]

    if args.stats:
        summary = {
            "candidates_raw": len(raw),
            "candidates_unique": len(entries),
            "with_recalls": len(with_recalls),
            "degraded": degraded,
            "state_path": str(state_path),
        }
        print(json.dumps(summary, ensure_ascii=False) if args.json else
              "[memory-promotion-gate] " + " ".join(f"{k}={v}" for k, v in summary.items()))
        return 0

    promotable, blocked, pending = build_plan(ws, scored, args.min_score, args.min_days)
    report = {
        "candidates_raw": len(raw),
        "candidates_unique": len(entries),
        "with_recalls": len(with_recalls),
        "would_promote": len(promotable),
        "blocked_no_threshold": len(blocked),
        "pending_review_high_risk": len(pending),
    }

    if args.json:
        print(json.dumps({**report,
                          "promote": [{"fp": e["fingerprint"], "score": e["score"],
                                       "recalls": e["recalls"], "risk": e["risk"],
                                       "snippet": e["snippet"][:120]} for e in promotable[:50]],
                          "pending_review": [{"fp": e["fingerprint"], "snippet": e["snippet"][:120]}
                                             for e in pending[:50]]},
                         ensure_ascii=False, indent=1))
    else:
        print("[memory-promotion-gate] " + " ".join(f"{k}={v}" for k, v in report.items()))
        for e in promotable[:20]:
            print(f"  would promote ({e['risk']}, score={e['score']}, recalls={e['recalls']}): "
                  f"{e['snippet'][:90]}")
        for e in pending[:10]:
            print(f"  pending-review (high-risk): {e['snippet'][:90]}")

    if args.dry_run:
        return 0

    # --apply：fail-closed（无 recalls 信号绝不写盘）
    if not with_recalls:
        print("[memory-promotion-gate] FAIL-CLOSED: 无任何 recalls 信号，拒绝写入 MEMORY.md",
              file=sys.stderr)
        return 2
    n = apply_plan(ws, promotable, state_path, state)
    if args.json:
        print(json.dumps({**report, "applied": n}, ensure_ascii=False))
    elif n == 0:
        print("[memory-promotion-gate] 无新增：目标条目均已带 dream-promoted 标记（幂等跳过）")
    else:
        print(f"[memory-promotion-gate] promoted {n} entr(ies) into MEMORY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
