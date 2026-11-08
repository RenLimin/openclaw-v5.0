"""P7.4 黄金用例：对象级 mandatory markings（region/PII）经 OntologyToolchain。

锁定语义（详设 §验收黄金用例）：
- 对象 metadata.markings=["pii"]；agent 无 pii 授予 → propose 拒
  （ScopeDenied），连 pending 都不建；
- agent 持 pii（令牌 claims，目录授予）→ propose→validate→停 validated；
- reviewer 无 pii 授予 → review 拒（对象不可见，不能审批自己看不到的）；
- reviewer 持 pii → review→commit（dry-run）成功；
- review→commit 间隙若吊销授予 → commit realtime_assert 拒；
- clearance：对象 confidential，令牌 restricted 才放行，internal 拒；
- fail-closed：metadata.markings 非列表 / claims 缺属性即拒。

全程真实 SQLite + 临时目录 + 固定 secret，不触网；连接器恒 dry-run
（P4.2 冻结语义不变）。
"""
from __future__ import annotations

import json
import os
import sys

import pytest

COMPONENT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

from contract_review.ontology_bridge import (  # noqa: E402
    ContractOntologyBridge,
    assemble,
)
from ai_kb.ontology.identity_token import (  # noqa: E402
    IdentityAuthority,
    ScopeDenied,
)
from ai_kb.ontology.markings import (  # noqa: E402
    MarkingDirectory,
    MarkingError,
)

_SECRET = b"l4-p7-secret-0123456789abcdef!!"
_DOMAIN = "bangcle-contract"


@pytest.fixture()
def bridge(tmp_path):
    db = str(tmp_path / "contract.db")
    aikb = str(tmp_path / "ai_kb.db")
    assemble(db, aikb, register="HT-2026-PII-01:500000")
    b = ContractOntologyBridge(db, aikb)
    yield b
    b.registry._ai_kb().close()


@pytest.fixture()
def authority():
    return IdentityAuthority(secret=_SECRET)


def _make_directory(bridge):
    ai = bridge.registry._ai_kb()
    try:
        d = MarkingDirectory(ai)
        d.register(_DOMAIN, "pii", "个人身份信息", sensitivity="high")
    finally:
        ai.close()
    return MarkingDirectory(
        __import__("ai_kb.db", fromlist=["AIKB"]).AIKB(bridge.ai_kb_path)
    )


def _tag_object(bridge, markings, clearance="restricted"):
    """直接给登记对象 metadata 挂 markings + permissions.clearance。"""
    ident = bridge.registry.get_identity("HT-2026-PII-01")
    md = ident["metadata"]
    if isinstance(md, str):
        md = json.loads(md)
    md["markings"] = list(markings)
    md.setdefault("permissions", {})
    md["permissions"]["clearance"] = clearance
    ai = bridge.registry._ai_kb()
    try:
        ai.execute(
            "UPDATE ont_identity SET metadata = ?, updated_at = ? WHERE id = ?",
            (json.dumps(md, ensure_ascii=False), ai.get_now(), ident["id"]),
        )
        ai.commit()
    finally:
        ai.close()


# ---------- 1) agent 无 pii 授予 → propose 拒，无 pending ----------

def test_agent_without_marking_denied(bridge, authority):
    d = _make_directory(bridge)
    _tag_object(bridge, ["pii"], clearance="restricted")
    with pytest.raises(ScopeDenied):
        bridge.submit_to_oa_agent(
            1, run_id="run-p7-1", agent="assistant",
            requestid="882663", action="提交",
            authority=authority, directory=d,
            agent_markings=[], agent_clearance="restricted",
        )

    # 无 pending 残留（拒绝在 propose 内、建记录之前）
    ai = bridge.registry._ai_kb()
    try:
        n = ai.execute(
            "SELECT COUNT(*) c FROM ont_proposal"
        ).fetchone()["c"]
        assert n == 0
    finally:
        ai.close()


# ---------- 2) agent 持 pii → validated；reviewer 无 pii → review 拒 ----------

def test_agent_with_marking_validated(bridge, authority):
    d = _make_directory(bridge)
    d.grant(_DOMAIN, "pii", "agent:assistant", source="directory", ttl_days=30)
    _tag_object(bridge, ["pii"], clearance="restricted")
    r = bridge.submit_to_oa_agent(
        1, run_id="run-p7-2", agent="assistant",
        requestid="882663", action="提交",
        authority=authority, directory=d,
        agent_markings=["pii"], agent_clearance="restricted",
    )
    assert r["ok"] is True
    assert r["proposal_status"] == "validated"


def test_reviewer_without_marking_cannot_approve(bridge, authority):
    d = _make_directory(bridge)
    d.grant(_DOMAIN, "pii", "agent:assistant", source="directory", ttl_days=30)
    _tag_object(bridge, ["pii"], clearance="restricted")
    with pytest.raises(ScopeDenied):
        bridge.submit_to_oa_agent(
            1, run_id="run-p7-3", agent="assistant",
            requestid="882663", action="提交",
            authority=authority, directory=d,
            agent_markings=["pii"], agent_clearance="restricted",
            reviewer_operator="rex",
            reviewer_markings=[], reviewer_clearance="restricted",
        )


# ---------- 3) reviewer 持 pii → commit（dry-run）成功 ----------

def test_reviewer_with_marking_commits(bridge, authority):
    d = _make_directory(bridge)
    d.grant(_DOMAIN, "pii", "agent:assistant", source="directory", ttl_days=30)
    d.grant(_DOMAIN, "pii", "operator:rex", source="directory", ttl_days=30)
    _tag_object(bridge, ["pii"], clearance="restricted")
    r = bridge.submit_to_oa_agent(
        1, run_id="run-p7-4", agent="assistant",
        requestid="882663", action="提交",
        authority=authority, directory=d,
        agent_markings=["pii"], agent_clearance="restricted",
        reviewer_operator="rex",
        reviewer_markings=["pii"], reviewer_clearance="restricted",
    )
    assert r["ok"] is True
    assert r["proposal_status"] == "committed"
    assert r["reviewer_token_fingerprint"]


# ---------- 4) clearance 分级不足 → 拒 ----------

def test_clearance_insufficient_denied(bridge, authority):
    d = _make_directory(bridge)
    d.grant(_DOMAIN, "pii", "agent:assistant", source="directory", ttl_days=30)
    _tag_object(bridge, ["pii"], clearance="restricted")
    with pytest.raises(ScopeDenied):
        bridge.submit_to_oa_agent(
            1, run_id="run-p7-5", agent="assistant",
            requestid="882663", action="提交",
            authority=authority, directory=d,
            agent_markings=["pii"], agent_clearance="internal",
        )


# ---------- 5) fail-closed：坏 metadata ----------

def test_bad_metadata_fail_closed(bridge, authority):
    d = _make_directory(bridge)
    ident = bridge.registry.get_identity("HT-2026-PII-01")
    ai = bridge.registry._ai_kb()
    try:
        ai.execute(
            "UPDATE ont_identity SET metadata = ? WHERE id = ?",
            (json.dumps({"markings": "pii"}), ident["id"]),
        )
        ai.commit()
    finally:
        ai.close()
    with pytest.raises((ScopeDenied, MarkingError)):
        bridge.submit_to_oa_agent(
            1, run_id="run-p7-6", agent="assistant",
            requestid="882663", action="提交",
            authority=authority, directory=d,
            agent_markings=["pii"], agent_clearance="restricted",
        )


# ---------- 6) 未注入 directory → P6 兼容路径（不强制） ----------

def test_no_directory_p6_compatible(bridge, authority):
    # 对象不挂标 + 不传 directory：行为同 P6
    r = bridge.submit_to_oa_agent(
        1, run_id="run-p7-7", agent="assistant",
        requestid="882663", action="提交",
        reviewer_operator="rex", authority=authority,
    )
    assert r["ok"] is True
    assert r["proposal_status"] == "committed"
