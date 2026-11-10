"""统一账本：聚合、去重、落盘。

契约见 DESIGN-DETAIL-system-governor-v1.0.md §2.2 / §4。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import Finding, GovernanceReport, LaneResult
from . import policy

DEFAULT_LEDGER = Path("/Users/bangcle/.openclaw/workspace/memory/governor-latest.json")


def normalize_evidence(evidence: str) -> str:
    """规范化 evidence：压缩空白、统一换行，用于生成 idempotency_key。"""
    return " ".join(evidence.split())


def make_key(finding: Finding) -> str:
    """幂等键 = lane + item + 规范化 evidence 的 sha1 前 16 位。"""
    raw = f"{finding.lane}|{finding.item}|{normalize_evidence(finding.evidence)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """跨 lane 去重：同一幂等键只保留 severity 最高的一条。"""
    rank = {"critical": 0, "warning": 1, "info": 2}
    best: dict[str, Finding] = {}
    for f in findings:
        key = f.idempotency_key or make_key(f)
        if key not in best or rank[f.severity] < rank[best[key].severity]:
            best[key] = f
    return list(best.values())


def build_report(
    lane_results: dict[str, LaneResult],
    *,
    timestamp: str | None = None,
    invoked: str = "cli",
    apply: bool = False,
) -> GovernanceReport:
    """汇总各 lane 结果 → GovernanceReport（含去重后的 summary）。"""
    report = GovernanceReport(
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        invoked=invoked,
        apply=apply,
        lanes=lane_results,
    )
    all_findings = [f for r in lane_results.values() for f in r.findings]
    deduped = dedupe(all_findings)

    # 去重后的 findings 按自身 lane 重新归组（保留各 lane 原始 stats），
    # 保证账本序列化内容与 summary 口径一致。
    by_lane: dict[str, list[Finding]] = {}
    for f in deduped:
        by_lane.setdefault(f.lane, []).append(f)
    report.lanes = {
        lane: LaneResult(
            lane=lane,
            findings=by_lane.get(lane, []),
            stats=dict(r.stats),
        )
        for lane, r in lane_results.items()
    }

    summary = {
        "auto_fixed": sum(1 for f in deduped if f.status == "auto-fixed"),
        "needs_human": sum(1 for f in deduped if f.status == "needs-human"),
        "planned": sum(1 for f in deduped if f.status == "planned"),
        "open": sum(1 for f in deduped if f.status == "open"),
        "ok": sum(1 for f in deduped if f.status == "ok"),
        "total_unique": len(deduped),
        "total_raw": len(all_findings),
    }
    report.summary = summary
    return report


def save_report(report: GovernanceReport, path: str | Path | None = None) -> str:
    """落盘 JSON 账本，返回路径。"""
    target = Path(path) if path else DEFAULT_LEDGER
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": report.timestamp,
        "invoked": report.invoked,
        "apply": report.apply,
        "summary": report.summary,
        "lanes": {
            lane: {
                "stats": r.stats,
                "findings": [
                    {
                        "lane": f.lane,
                        "item": f.item,
                        "severity": f.severity,
                        "status": f.status,
                        "evidence": f.evidence,
                        "action": f.action,
                    }
                    for f in r.findings
                ],
            }
            for lane, r in sorted(report.lanes.items())
        },
    }
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)  # 原子替换
    report.ledger_path = str(target)
    return str(target)
