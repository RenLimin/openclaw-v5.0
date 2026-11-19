"""P4 757 异常备注提取单测（离线：注入假 reader，不触网）。

真实边界（2026-11-19 实测）：
  - 885637（916 单 886453 关联）→ OA 返回「对不起，您暂时没有权限！」
  - 885641 / 885784 → 可读，含 AI小助手「销售合同审核意见」
本测试用假 reader 覆盖两种路径 + 降级口径。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(COMPONENT_ROOT / "services" / "oa" / "enhance"))
sys.path.insert(0, str(COMPONENT_ROOT))

from pm import approval_notes as an  # noqa: E402
from services.oa.approval_log import ApprovalEntry, ApprovalChain, ApprovalLogUnavailable  # noqa: E402


class _FakeReader:
    def __init__(self, chain=None, exc=None):
        self._chain = chain
        self._exc = exc

    def read_approval_chain(self, rid):
        if self._exc:
            raise self._exc
        return self._chain


def _chain(entries, rid="885641", wf="757"):
    return ApprovalChain(requestid=rid, workflowid=wf, tx_status="", creator_node_id="",
                         viewer_user_id="", entries=entries)


def _ai(opinion):
    return ApprovalEntry(node="AI复核", operator="AI小助手", operator_id="1",
                         dept="信息管理部", action="批注", opinion=opinion,
                         date="2026-11-11", time="10:00", receivers="", log_id="1")


def _human(opinion, action="退回"):
    return ApprovalEntry(node="商务", operator="曾铭", operator_id="2", dept="深圳分公司",
                         action=action, opinion=opinion, date="2026-11-11", time="09:00",
                         receivers="", log_id="2")


# ---------- 正常提取 ----------
def test_ai_summary_and_levels():
    c = _chain([_ai("总体建议【重点复核】建议谨慎签署。签约比例 28.17%，含【需补充】交付邮件证据缺失。")])
    n = an.collect("885641", reader=_FakeReader(c))
    assert n.ok and n.ai_summary
    assert n.risk_levels == ["重点复核", "需补充"]
    assert "谨慎签署" in n.verdict_hint


def test_human_abnormal_opinion():
    c = _chain([_human("合同金额与概算不一致，请补充说明")])
    n = an.collect("885641", reader=_FakeReader(c))
    assert n.ok
    assert any("合同金额与概算不一致" in o for o in n.abnormal_opinions)


def test_neutral_opinion_ignored():
    c = _chain([_human("无异议", action="批准"), _human("同意", action="批准")])
    n = an.collect("885641", reader=_FakeReader(c))
    assert n.ok and n.abnormal_opinions == []


# ---------- 降级：不伪造、不阻断 ----------
def test_no_permission_degraded():
    """实测 885637：OA 无权限 → degraded，不抛错。"""
    n = an.collect("885637", reader=_FakeReader(exc=ApprovalLogUnavailable("requestid=885637: loglist 被拦截")))
    assert not n.ok
    assert "无权限" in n.degraded
    assert n.ai_summary == ""


def test_empty_rid():
    n = an.collect("")
    assert not n.ok and "无合同审批流程链接" in n.degraded


def test_generic_exception_degraded():
    n = an.collect("885641", reader=_FakeReader(exc=RuntimeError("boom")))
    assert not n.ok and "读取失败" in n.degraded


def test_readable_but_no_ai_is_ok():
    """有链可读但无 AI 意见 → ok（不误报故障），risk_levels 为空。"""
    c = _chain([_human("已通过", action="批准")])
    n = an.collect("885641", reader=_FakeReader(c))
    assert n.ok and n.risk_levels == [] and n.ai_summary == ""


def test_empty_chain_degraded():
    c = _chain([])
    n = an.collect("885641", reader=_FakeReader(c))
    assert not n.ok and "审批链为空" in n.degraded


# ---------- 纯函数 ----------
def test_levels_dedup():
    assert an._levels("【重点复核】【需补充】【重点复核】") == ["重点复核", "需补充"]


def test_verdict_hint():
    assert "建议谨慎签署" in an._verdict_hint("总体建议【重点复核】建议谨慎签署。分项一致。")
    assert an._verdict_hint("无异常") == ""
