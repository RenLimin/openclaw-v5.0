"""Lane B — 资产健康（适配器）。

设计（DETAIL §3.2）：只读聚合 full_audit §3/§4 + guardian 状态。
服务拉起由 service_guardian 常驻自动完成，governor 只记录回执；
配置/key 失效 → needs-human（建议 doctor --fix），永不自动改。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..models import Finding

FULL_AUDIT = "/Users/bangcle/.openclaw/workspace/L2-infra/scripts/system_full_audit.py"
GUARDIAN_STATE = Path(
    "/Users/bangcle/.openclaw/workspace/L2-infra/components/model-scheduling/logs/service_guardian_state.json"
)

# full_audit.py --json 的章节标题（实测）
SECTION_ASSETS = "3. 自研资产状态检测"
SECTION_PROVIDER = "4. 模型与 Provider 健康检测"
# v1.1：资产一致性探针（DETAIL §2.2）
SECTION_CONSISTENCY = "12. 资产一致性检测"


def _run_audit_json() -> dict:
    try:
        out = subprocess.run(
            ["python3", FULL_AUDIT, "--json"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode != 0:
            return {}
        return json.loads(out.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return {}


def _load_guardian() -> dict:
    if not GUARDIAN_STATE.exists():
        return {}
    try:
        return json.loads(GUARDIAN_STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _audit_findings(audit: dict) -> list[Finding]:
    findings: list[Finding] = []
    sections = audit.get("sections") or {}
    # (标题, ⚠️ 项的处置动作)
    section_specs = [
        (SECTION_ASSETS, "查看 full_audit --json 对应条目"),
        (SECTION_PROVIDER, "若为 Provider 配置/key 问题：openclaw doctor --fix；服务问题由 guardian 自愈"),
        (SECTION_CONSISTENCY, "运行 governor.py audit 进入资产审计工作流"),
    ]
    for title, warn_action in section_specs:
        for item in sections.get(title) or []:
            status = item.get("status", "")
            name = item.get("name", "")
            detail = item.get("detail", "")
            if status == "✅":
                findings.append(Finding(
                    lane="B", item=name, severity="info", status="ok",
                    evidence=f"{title}: {detail[:150]}",
                ))
            elif status == "⚠️":
                findings.append(Finding(
                    lane="B", item=name, severity="warning", status="open",
                    evidence=f"{title}: {detail[:150]}",
                    action=warn_action,
                ))
            elif status == "❌":
                findings.append(Finding(
                    lane="B", item=name, severity="critical", status="needs-human",
                    evidence=f"{title}: {detail[:150]}",
                    action=(
                        "若为 Provider 配置/key 问题：openclaw doctor --fix；服务问题由 guardian 自愈"
                        if title != SECTION_CONSISTENCY
                        else "运行 governor.py audit 进入资产审计工作流"
                    ),
                ))
    return findings


def _guardian_findings(state: dict) -> list[Finding]:
    findings: list[Finding] = []
    if not state:
        return [Finding(
            lane="B", item="guardian_state_missing", severity="warning", status="open",
            evidence="service_guardian_state.json 缺失（guardian 未运行？）",
            action="检查 launchctl list ai.openclaw.service-guardian-daemon",
        )]
    if state.get("gateway") is False:
        findings.append(Finding(
            lane="B", item="gateway_down", severity="critical", status="needs-human",
            evidence=f"guardian 报告 gateway 不在线（{state.get('timestamp', '')}）",
            action="guardian 应已尝试拉起；仍未恢复则人工介入",
        ))
    for svc in state.get("services") or []:
        if not svc.get("port_ok", True):
            findings.append(Finding(
                lane="B", item=f"service_{svc.get('label', '?')}",
                severity="critical", status="open",
                evidence=f"service {svc.get('label')} port not ok: {svc.get('action', '')}",
                action="guardian 常驻自动拉起；持续失败需人工",
            ))
    return findings


def run(apply: bool = False) -> list[Finding]:
    """Lane B 只读聚合。服务拉起由 guardian 常驻自动完成，apply 不改变行为。"""
    audit = _run_audit_json()
    if not audit:
        return [Finding(
            lane="B", item="full_audit_unavailable", severity="warning", status="open",
            evidence="system_full_audit.py --json 无输出/超时",
            action="单独运行 system_full_audit.py --json 排查",
        )]
    findings = _audit_findings(audit)
    findings.extend(_guardian_findings(_load_guardian()))
    return findings
