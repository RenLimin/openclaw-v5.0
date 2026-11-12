"""资产审计 — 六环节工作流（v1.1，DETAIL §3.1）。

取证 → 定性 → 方案 → 拍板 → 执行 → 回归。
默认零写（apply=False）；账本落 memory/governor-audit-latest.json（原子写）。
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import audit_classify, audit_exec
from .models import AuditItem

FULL_AUDIT = Path("/Users/bangcle/.openclaw/workspace/L2-infra/scripts/system_full_audit.py")
DEFAULT_AUDIT_LEDGER = Path("/Users/bangcle/.openclaw/workspace/memory/governor-audit-latest.json")


def _collect(only: set[str] | None, timeout: int) -> dict:
    """环节 1 取证：跑 full_audit --json，取 §12。"""
    cmd = ["python3", str(FULL_AUDIT), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"full_audit 失败: {proc.stderr[:300]}")
    return json.loads(proc.stdout)


def _summarize(items: list[AuditItem]) -> dict:
    def n(s: str) -> int:
        return sum(1 for i in items if i.status == s)
    return {
        "total": len(items),
        "pending": n("pending"),
        "done": n("done"),
        "needs_human": n("needs-human"),
        "skipped": n("skipped"),
        "approved": n("approved"),
    }


def _save_ledger(payload: dict, path: Path) -> str:
    """环节 6 落盘：原子写（tmp + replace）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return str(path)


def run(
    *,
    apply: bool = False,
    only: set[str] | None = None,
    timeout: int = 300,
    root: Path | None = None,
    ledger_path: Path | None = None,
) -> dict:
    """跑六环节审计，返回结构化报告 dict。

    环节:
      1 取证  _collect → audit dict
      2/3 定性+方案  audit_classify.classify → AuditItem[]（含 category/suggestion/tier）
      4 拍板  L2→needs-human / L1→pending
      5 执行  audit_exec.run（仅 apply 且 L1）
      6 回归  重跑 §12 探针 → 落账本
    """
    root = root or Path("/Users/bangcle/.openclaw/workspace")
    ledger_path = ledger_path or DEFAULT_AUDIT_LEDGER

    # 1 取证
    audit = _collect(only, timeout)

    # 2/3 定性 + 方案
    raw_items = audit_classify.classify(audit, only=only)

    # 4 拍板
    items = [audit_classify.initial_status(it) for it in raw_items]

    # 5 执行
    items, actions = audit_exec.run(items, apply=apply, root=root)

    # 6 回归：重跑 §12，记录仍告警的探针
    re_audit = _collect(only, timeout)
    sections = re_audit.get("sections") or {}
    remaining = [
        {"name": p.get("name"), "detail": p.get("detail", "")[:200]}
        for p in sections.get("12. 资产一致性检测") or []
        if p.get("status") == "⚠️"
    ]

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "invoked": "cli",
        "apply": apply,
        "items": [
            {
                "id": i.id,
                "category": i.category,
                "evidence": i.evidence,
                "suggestion": i.suggestion,
                "tier": i.tier,
                "status": i.status,
                "detail": i.detail,
            }
            for i in items
        ],
        "actions": actions,
        "regression": {"remaining_warnings": remaining, "remaining_count": len(remaining)},
        "summary": _summarize(items),
    }
    payload["ledger_path"] = _save_ledger(payload, ledger_path)
    return payload
