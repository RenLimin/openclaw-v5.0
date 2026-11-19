"""757 合同审批流程异常备注提取（仅 916；复用 approval_log，不重写自动化）。

数据源：916 单「合同审批流程→」(field13682) → 757 requestid
      → ApprovalLogReader.read_approval_chain → 提取 AI小助手/人工异常意见。

降级口径（DESIGN-DETAIL §6）：
  - ApprovalLogUnavailable / 无权限 → degraded=原因，**不阻断**整体输出
  - 风险等级取正文中【…】标记；无权限单（实测 885637）不伪造
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

try:                       # 正常包结构：services.oa.enhance.pm
    from ..approval_log import ApprovalLogReader, ApprovalLogUnavailable
except ImportError:        # 直接以 pm 为顶层包加载
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from services.oa.approval_log import ApprovalLogReader, ApprovalLogUnavailable

# AI 小助手（信息管理部）写入的「销售合同审核意见」
_AI_MARKERS = ("AI小助手", "AI 小助手", "信息管理部")
# 视为「无异常」的意见
_NEUTRAL = ("无异议", "同意", "无", "—", "-", "")


@dataclass
class ApprovalNotes:
    request_id: str
    workflow_id: str = ""
    ai_summary: str = ""              # AI 小助手「销售合同审核意见」正文（纯文本）
    risk_levels: List[str] = field(default_factory=list)   # 【重点复核】/【需补充】…
    abnormal_opinions: List[str] = field(default_factory=list)  # 人工异常意见（退回/批注）
    verdict_hint: str = ""            # 总体建议（如「建议谨慎签署」）
    degraded: Optional[str] = None    # 无权限/不可得原因（不伪造）

    @property
    def ok(self) -> bool:
        return self.degraded is None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _levels(text: str) -> List[str]:
    """提取正文中的【…】风险标记（去重保序）。"""
    out: List[str] = []
    for m in re.findall(r"【([^】]{1,20})】", text or ""):
        if m not in out:
            out.append(m)
    return out


def _is_ai(entry: Any) -> bool:
    who = " ".join(str(getattr(entry, f, "") or "") for f in ("operator", "dept", "node"))
    return any(k in who for k in _AI_MARKERS)


def collect(
    approval_rid: str,
    reader: Optional[ApprovalLogReader] = None,
) -> ApprovalNotes:
    """读取 757 审批链并提取异常备注。

    Args:
        approval_rid: 916「合同审批流程→」的 requestid（757 单）。
        reader: 可注入（测试用假 reader）；None 则用默认 ApprovalLogReader()。

    Returns:
        ApprovalNotes；不可得时 degraded 填原因（不抛错、不伪造）。
    """
    n = ApprovalNotes(request_id=str(approval_rid))
    if not str(approval_rid).strip():
        n.degraded = "916 单无合同审批流程链接"
        return n

    rd = reader or ApprovalLogReader()
    try:
        chain = rd.read_approval_chain(approval_rid)
    except ApprovalLogUnavailable as exc:
        n.degraded = "无权限/不可得：%s" % exc
        return n
    except Exception as exc:  # noqa: BLE001 - 任何失败都降级，不阻断主流程
        n.degraded = "读取失败：%s" % exc
        return n

    n.workflow_id = chain.workflowid or ""
    for e in chain.entries:
        opinion = (getattr(e, "opinion", "") or "").strip()
        action = getattr(e, "action", "") or ""
        if _is_ai(e) and opinion:
            n.ai_summary = (n.ai_summary + "\n" + opinion).strip() if n.ai_summary else opinion
            continue
        # 人工异常：退回/批注 且意见非中性
        if action in ("退回", "批注") and opinion and opinion not in _NEUTRAL:
            n.abnormal_opinions.append("%s（%s）：%s" % (getattr(e, "operator", ""), action, opinion))

    n.risk_levels = _levels(n.ai_summary)
    n.verdict_hint = _verdict_hint(n.ai_summary)
    # 口径：审批链**可读即 ok**（可能该单未被 AI 复核，不视为降级）；
    # 仅「读不到」才算 degraded，避免把「无异常」误报为故障。
    if not chain.entries:
        n.degraded = "审批链为空（无流转记录）"
    return n


def _verdict_hint(text: str) -> str:
    """从 AI 意见中提取总体建议（首个含「建议」「谨慎」「签署」的短句）。"""
    if not text:
        return ""
    for sent in re.split(r"[。；\n]", text):
        s = sent.strip()
        if any(k in s for k in ("建议", "谨慎", "签署")) and len(s) <= 60:
            return s
    return ""


def quick_notes(approval_rid: str) -> ApprovalNotes:
    """便捷入口（真实浏览器读取）。"""
    return collect(approval_rid)
