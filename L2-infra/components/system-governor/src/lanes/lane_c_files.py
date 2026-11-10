"""Lane C — 文件治理（适配器）。

设计（DETAIL §3.3）：
- dry-run（默认）：tempcleanctl list + archive dry-run → planned 清单，零写。
- --apply：先 archive（归档移动），再 tempcleanctl clean（trash 已过期项）。
受保护 / 未过期 / 无候选时一律不动作。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..models import Finding

TEMPCLEANCTL = (
    "/Users/bangcle/.openclaw/workspace/L2-infra/components/"
    "workspace-temp-cleanup/scripts/tempcleanctl.py"
)
ARCHIVE = (
    "/Users/bangcle/.openclaw/workspace/L2-infra/components/"
    "workspace-temp-cleanup/scripts/archive.py"
)
WORKSPACE = "/Users/bangcle/.openclaw/workspace"
ARCHIVE_DEST = "/Users/bangcle/.openclaw/workspace/.archive"


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.returncode, out.stdout, out.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"


def _plan_findings() -> list[Finding]:
    findings: list[Finding] = []
    rc, out, err = _run(["python3", TEMPCLEANCTL, "--root", WORKSPACE,
                         "dry-run", "--json"])
    temp_expired = 0
    if rc == 0:
        try:
            import json
            cands = json.loads(out)
            temp_expired = sum(1 for c in cands if c.get("expired"))
        except Exception:  # noqa: BLE001
            pass
    rc2, out2, _ = _run(["python3", ARCHIVE, "--root", WORKSPACE,
                         "--dest", ARCHIVE_DEST, "--json"])
    arch_planned = 0
    if rc2 == 0:
        try:
            import json
            arch_planned = json.loads(out2)["summary"]["planned"]
        except Exception:  # noqa: BLE001
            pass

    if temp_expired:
        findings.append(Finding(
            lane="C", item="temp_clean", severity="warning", status="planned",
            evidence=f"tempcleanctl: {temp_expired} 个已过期候选（将 trash）",
            action="--apply 执行 tempcleanctl clean --yes",
        ))
    if arch_planned:
        findings.append(Finding(
            lane="C", item="archive", severity="warning", status="planned",
            evidence=f"archive: {arch_planned} 个文件命中归档规则 R1-R3",
            action="--apply 移动到 .archive/（manifest 登记，可回滚）",
        ))
    if not findings:
        findings.append(Finding(
            lane="C", item="file_scan", severity="info", status="ok",
            evidence="无过期临时资产，无命中归档规则（workspace 当前干净）",
        ))
    return findings


def _apply_findings() -> list[Finding]:
    findings: list[Finding] = []
    # 1) 归档
    rc, out, err = _run(["python3", ARCHIVE, "--root", WORKSPACE,
                         "--dest", ARCHIVE_DEST, "--apply", "--json"])
    if rc == 0:
        try:
            import json
            s = json.loads(out)["summary"]
            findings.append(Finding(
                lane="C", item="archive", severity="info", status="auto-fixed",
                evidence=f"archive apply: moved {s['moved']}, "
                         f"skipped {s['skipped_identical']}, "
                         f"{s['bytes'] // 1024 // 1024}MB",
                action="见 .archive/manifest.json（可回滚）",
            ))
        except Exception:  # noqa: BLE001
            pass
    else:
        findings.append(Finding(
            lane="C", item="archive", severity="warning", status="open",
            evidence=f"archive apply rc={rc}: {err[:120]}",
        ))
    # 2) trash 已过期临时资产
    rc, out, err = _run(["python3", TEMPCLEANCTL, "--root", WORKSPACE,
                         "clean", "--yes"])
    findings.append(Finding(
        lane="C", item="temp_clean", severity="info",
        status="auto-fixed" if rc == 0 else "open",
        evidence=f"tempclean clean: {(out or err).strip()[:160]}",
    ))
    return findings


def run(apply: bool = False) -> list[Finding]:
    return _apply_findings() if apply else _plan_findings()
