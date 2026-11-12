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


@dataclass(frozen=True)
class AuditItem:
    """资产审计单项（v1.1，DETAIL §2.4）。"""

    id: str                # 稳定标识，如 "P3-health-engine"
    category: str          # 残留 | 重复 | 空壳 | 口径漂移 | 断链
    evidence: str          # 证据（file:line / 命令输出摘要）
    suggestion: str        # 处置建议（归位/合并/降级/删除/补实现）
    tier: str              # L1（可回滚 git 操作）| L2（需人工）
    status: str            # pending | approved | done | skipped | needs-human
    detail: dict = None    # 补充字段（路径对、计数、阈值等）


# AuditItem 状态/分类常量
AUDIT_STATUSES = ("pending", "approved", "done", "skipped", "needs-human")
AUDIT_CATEGORIES = ("残留", "重复", "空壳", "口径漂移", "断链")


# 严重度/状态常量
SEVERITIES = ("critical", "warning", "info")
STATUSES = ("open", "auto-fixed", "needs-human", "planned", "ok")
LANES = ("A", "B", "C", "D")
