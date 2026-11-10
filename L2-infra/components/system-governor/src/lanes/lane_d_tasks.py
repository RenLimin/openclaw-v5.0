"""Lane D — 建设任务盘点（适配器，P3 结构化版）。

设计（DETAIL §3.4）：纯只读多源聚合，输出逐任务 Finding：
1. task_tracker current-task（active / stalled）
2. memory/task-history/*.md（归档中未完成/失败）
3. 各文档未勾选项：按「最近 ##/### 标题」归组为任务，一条标题组一条 Finding
4. doc_gap：docs/architecture 中同一 topic 有 OUTLINE 但缺 DETAIL
不改任何文件。
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from ..models import Finding

WORKSPACE = Path("/Users/bangcle/.openclaw/workspace")
CURRENT_TASK = WORKSPACE / "memory" / "current-task.md"
HISTORY_DIR = WORKSPACE / "memory" / "task-history"
ARCH_DIR = WORKSPACE / "docs" / "architecture"

SCAN_ROOTS = [
    WORKSPACE / "L2-infra",
    WORKSPACE / "L3-business",
    WORKSPACE / "L4-proprietary",
]
SKIP_PARTS = (".git", "node_modules", "__pycache__", ".trash")

HEADING_RE = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
CHECK_RE = re.compile(r"^\s*- \[ \]\s*(.*)$")


def _iter_docs() -> list[Path]:
    docs: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            docs.append(path)
    return docs


def _current_task_findings() -> list[Finding]:
    if not CURRENT_TASK.exists():
        return []
    text = CURRENT_TASK.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"task_id:\s*(\S+)", text)
    n = re.search(r"name:\s*(.+)", text)
    p = re.search(r"phase:\s*(.+)", text)
    f = re.search(r"failure_count:\s*(\d+)", text)
    out = [Finding(
        lane="D", item="current_task", severity="info", status="open",
        evidence=f"current-task.md: {m.group(1) if m else '?'} | "
                 f"{n.group(1).strip() if n else '?'} | phase={p.group(1).strip() if p else '?'}",
        action="继续推进该任务或 complete 归档",
    )]
    if f and int(f.group(1)) >= 2:
        out.append(Finding(
            lane="D", item="current_task_stalled", severity="warning", status="open",
            evidence=f"current-task failure_count={f.group(1)} ≥2",
            action="停止重试，等待 Rex 拍板",
        ))
    return out


def _history_findings() -> list[Finding]:
    if not HISTORY_DIR.exists():
        return []
    out: list[Finding] = []
    for f in sorted(HISTORY_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"archive_reason:\s*(\S+)", text)
        reason = m.group(1) if m else ""
        if reason and reason != "completed":
            out.append(Finding(
                lane="D", item="archived_unfinished", severity="warning", status="open",
                evidence=f"{f.name}: archive_reason={reason}",
                action="确认该任务是否需重启或正式关闭",
            ))
    return out


def _unchecked_group_findings() -> list[Finding]:
    """按「最近 ##/### 标题」归组未勾选项，每个标题组一条 Finding。"""
    out: list[Finding] = []
    for doc in _iter_docs():
        text = doc.read_text(encoding="utf-8", errors="ignore")
        rel = doc.relative_to(WORKSPACE)
        topic = doc.stem
        current_heading = "(无标题)"
        groups: dict[str, list[str]] = defaultdict(list)
        order: list[str] = []
        added: set[str] = set()

        def _queue(heading: str) -> None:
            if heading not in added:
                added.add(heading)
                order.append(heading)

        for line in text.splitlines():
            hm = HEADING_RE.match(line)
            if hm:
                current_heading = hm.group(2).strip()
                _queue(current_heading)
                continue
            cm = CHECK_RE.match(line)
            if cm:
                _queue(current_heading)
                groups[current_heading].append(cm.group(1).strip())

        for heading in order:
            items = groups.get(heading)
            if not items:
                continue
            n = len(items)
            # 验收/标准类未勾选视作 warning（门未过），其余 info
            is_gate = bool(re.search(r"验收|标准|出口|Acceptance|Checklist", heading + topic))
            out.append(Finding(
                lane="D", item=f"task::{topic}::{heading}"[:120],
                severity="warning" if is_gate else "info", status="open",
                evidence=f"{rel} §「{heading}」: {n} 项未完成 — 如 {items[0][:70]}",
                action=f"完成「{heading}」下 {n} 项并勾选",
            ))
    return out


def _topic_from_arch_name(name: str) -> str:
    """从 architecture 文件名提取 topic，如 DESIGN-OUTLINE-foo-v1.0 → foo。"""
    for prefix in ("DESIGN-OUTLINE-", "DESIGN-DETAIL-", "PRD-", "VERIFICATION-"):
        if name.startswith(prefix):
            rest = name[len(prefix):]
            rest = re.sub(r"-v?\d+(\.\d+)*\.md$", "", rest)
            return rest
    return ""


def _doc_gap_findings() -> list[Finding]:
    """architecture：同 topic 有 OUTLINE 但缺 DETAIL → 设计链缺口。"""
    if not ARCH_DIR.exists():
        return []
    has_outline: set[str] = set()
    has_detail: set[str] = set()
    for f in ARCH_DIR.glob("*.md"):
        topic = _topic_from_arch_name(f.name)
        if not topic:
            continue
        if f.name.startswith("DESIGN-OUTLINE-"):
            has_outline.add(topic)
        elif f.name.startswith("DESIGN-DETAIL-"):
            has_detail.add(topic)
    out: list[Finding] = []
    for topic in sorted(has_outline - has_detail):
        out.append(Finding(
            lane="D", item="doc_gap_outline_no_detail", severity="warning",
            status="open",
            evidence=f"docs/architecture: topic「{topic}」有 OUTLINE 无 DETAIL",
            action="补 DESIGN-DETAIL 或确认仅大纲即可",
        ))
    return out


def run(apply: bool = False) -> list[Finding]:
    """Lane D 纯只读盘点，apply 不改变行为。"""
    findings: list[Finding] = []
    findings.extend(_current_task_findings())
    findings.extend(_history_findings())
    findings.extend(_unchecked_group_findings())
    findings.extend(_doc_gap_findings())
    return findings
