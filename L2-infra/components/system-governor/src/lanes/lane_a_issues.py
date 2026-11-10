"""Lane A — 已知问题自愈（适配器）。

设计（DETAIL §3.1）：写动作全部委托既有模块（scan_errors.py 的 auto_fix /
reliability P1-a/b/c/d），governor 只读结果账本并聚合回执，不重复执行。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Finding

# scan_errors.py 的固定输出账本（LOG_FILE）
SCAN_LATEST = Path("/Users/bangcle/.openclaw/workspace/memory/error-scan-latest.json")


def _load_scan_result() -> dict:
    if not SCAN_LATEST.exists():
        return {}
    try:
        return json.loads(SCAN_LATEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _severity_of(err: dict) -> str:
    etype = err.get("type") or "error"
    if etype in ("llm_timeout", "compaction_failed", "gateway_restart_required",
                 "context_overflow"):
        return "critical"
    return "warning"


def _fix_status(fix: dict) -> str:
    """fix 落账状态：executed → auto-fixed；建议型 → needs-human。"""
    if fix.get("executed"):
        return "auto-fixed"
    return "needs-human"


def run(apply: bool = False) -> list[Finding]:
    """读取 scan_errors 账本，映射为 Finding 列表。只读，无写动作。

    Lane A 的写动作全部委托既有模块（scan_errors auto_fix / reliability），
    apply 参数不改变 governor 侧行为（仅保持 runner 签名统一）。
    """
    result = _load_scan_result()
    if not result:
        return [Finding(
            lane="A", item="scan_latest_missing", severity="warning",
            status="open",
            evidence="memory/error-scan-latest.json 不存在（error-scan 未跑或首次）",
            action="run scan_errors.py 一次",
        )]

    findings: list[Finding] = []
    fixes = result.get("fixes") or []
    errors = result.get("errors") or []

    # 先看 fixes：已执行的自愈 → auto-fixed；建议型 → needs-human
    fix_by_evidence: set[str] = set()
    for fix in fixes:
        status = _fix_status(fix)
        findings.append(Finding(
            lane="A", item=fix.get("action", "auto_fix"), severity="info",
            status=status,
            evidence=f"fix: {fix.get('reason', '')} result={fix.get('result', '')}",
            action=fix.get("action"),
        ))
        # 该 fix 对应的 error 不再重复列为 open
        for err in errors:
            if err.get("type") in str(fix.get("reason", "")):
                fix_by_evidence.add(err.get("type", "") + err.get("name", ""))

    # 未被 fix 覆盖的 errors → open + 建议动作
    seen: set[str] = set()
    for err in errors:
        etype = err.get("type") or "error"
        ename = err.get("name", "")
        key = etype + ename
        if key in seen or key in fix_by_evidence:
            continue
        seen.add(key)
        detail = err.get("detail") or err.get("error") or ""
        findings.append(Finding(
            lane="A", item=ename or etype, severity=_severity_of(err),
            status="open", evidence=f"{etype}: {detail[:200]}",
            action="见 error-scan-latest.json fixes 或手工处置",
        ))

    if not findings and result.get("healthy"):
        findings.append(Finding(
            lane="A", item="scan_healthy", severity="info", status="ok",
            evidence=result.get("timestamp", ""),
        ))
    return findings
