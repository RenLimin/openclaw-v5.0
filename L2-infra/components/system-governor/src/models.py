"""system-governor 数据模型。

数据结构契约见 DESIGN-DETAIL-system-governor-v1.0.md §2.2。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Finding:
    """单条检测发现。"""

    lane: str                 # "A"|"B"|"C"|"D"
    item: str                 # 检查项名，如 "scan_cron_errors"
    severity: str             # "critical"|"warning"|"info"
    status: str               # "open"|"auto-fixed"|"needs-human"|"planned"|"ok"
    evidence: str             # 证据/来源，可含 file:line、命令输出摘要
    action: Optional[str] = None   # 已执行或建议动作；None=无动作
    idempotency_key: str = ""      # 规范化 evidence hash，跨 lane 去重


@dataclass
class LaneResult:
    """单个 lane 的执行结果。"""

    lane: str
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)   # scanned/errors/warnings/elapsed_s

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)


@dataclass
class GovernanceReport:
    """一次 run 的统一账本。"""

    timestamp: str            # ISO
    invoked: str              # cli|automation
    apply: bool               # 是否 --apply
    lanes: dict[str, LaneResult] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    ledger_path: str = ""     # 账本落盘路径


# 严重度/状态常量
SEVERITIES = ("critical", "warning", "info")
STATUSES = ("open", "auto-fixed", "needs-human", "planned", "ok")
LANES = ("A", "B", "C", "D")
