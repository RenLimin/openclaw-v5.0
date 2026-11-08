"""P6.2 黄金用例：agent 经 OntologyToolchain 消费 submit_to_oa（详设 §验收 #12）。

覆盖：
- agent run 令牌 → propose → validate → 停在 validated（agent 永不 commit）；
- human operator 令牌 → review → commit（dry-run 连接器），审计含
  run 令牌指纹 + reviewer 令牌指纹，oa_submitted_at 落库；
- 决策链可回放，decision_record.token_fingerprint = reviewer 令牌指纹；
- 无真实 HTTP：连接器恒 dry-run（P4.2 冻结语义不变）。

全程真实 SQLite + 临时目录 + 固定 secret，不触网。
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
from contract_review.ontology_bridge.oa_connector import (  # noqa: E402
    OaWritebackConnector,
)
from ai_kb.ontology.identity_token import (  # noqa: E402
    IdentityAuthority,
    IdentityError,
)

_SECRET = b"l4-golden-secret-0123456789abcdef!"


@pytest.fixture()
def bridge(tmp_path):
    """独立 db + ai_kb + 装配 + 登记 1 个合同。"""
    db = str(tmp_path / "contract.db")
    aikb = str(tmp_path / "ai_kb.db")
    assemble(db, aikb, register="HT-2026-008:200000")
    b = ContractOntologyBridge(db, aikb)
    yield b
    b.registry._ai_kb().close()


@pytest.fixture()
def authority():
    return IdentityAuthority(secret=_SECRET)


# ---------- 1) agent 到 validated 即停 ----------

def test_agent_stops_at_validated(bridge, authority):
    """agent run 令牌：propose→validate→validated，绝不 commit。"""
    r = bridge.submit_to_oa_agent(
        1, run_id="run-882663", agent="assistant",
        requestid="882663", action="提交", comment="P6.2 agent 送审",
        authority=authority,
    )
    assert r["ok"] is True
    assert r["proposal_status"] == "validated"
    assert r["action"] == "submit_to_oa"
    assert r["run_token_fingerprint"]
    assert "reviewer_token_fingerprint" not in r
    assert "decision_record" not in r

    # 提案未 committed
    st = bridge.status(1)
    assert len(st["decision_chain"]) == 0

    # agent 令牌确实有效（run 指纹 16 hex）
    assert len(r["run_token_fingerprint"]) == 16


# ---------- 2) human operator 令牌 commit（双指纹 + dry-run） ----------

def test_human_operator_commits_with_fingerprints(bridge, authority):
    """reviewer_operator 现场签发 human 令牌 → review→commit（dry-run）。"""
    r = bridge.submit_to_oa_agent(
        1, run_id="run-882663", agent="assistant",
        requestid="882663", action="提交", comment="P6.2 送审",
        reviewer_operator="rex", authority=authority,
    )
    assert r["ok"] is True
    assert r["proposal_status"] == "committed"
    assert r["run_token_fingerprint"]
    assert r["reviewer_token_fingerprint"]

    # 决策链可回放 + 证据完整
    st = bridge.status(1)
    chain = st["decision_chain"]
    assert len(chain) == 1
    rec = chain[0]
    assert rec["action_type"] == "submit_to_oa"
    assert rec["result"] == "allowed"
    # actor = 提案发起者（agent）；审批者身份在 evidence.review_by
    assert rec["actor_kind"] == "agent"
    assert rec["actor_id"] == "agent:assistant"
    assert rec["evidence"]["review_by"] == "operator:rex"
    assert rec["evidence"]["connector"] == "oa_writeback"
    assert rec["evidence"]["saga_report"]["ok"] is True
    assert rec["evidence"]["saga_report"]["executed_steps"] == ["oa_writeback"]
    # 指纹落库 = reviewer 令牌指纹
    assert rec["token_fingerprint"] == r["reviewer_token_fingerprint"]

    # 审计元数据落库（同 _run_oa 语义）
    ident = bridge.registry.get_identity("HT-2026-008")
    assert ident is not None
    md = ident["metadata"]
    if isinstance(md, str):
        md = json.loads(md)
    assert "oa_submitted_at" in md


# ---------- 3) agent 令牌无法自行 commit ----------

def test_agent_cannot_self_commit(bridge, authority):
    """agent 令牌当 reviewer → 拒绝（toolchain 强制 human 才可 commit）。"""
    from ai_kb.ontology.agent_toolchain import OntologyToolchain

    agent_tok = authority.issue(
        run_id="run-882663", subject="agent:assistant", kind="agent",
        scopes=[f"review:submit_to_oa:bangcle-contract"],
    )
    ai, svc = bridge._new_service_oa(
        {"requestid": "882663", "action": "提交"}, identity=authority,
    )
    try:
        chain = OntologyToolchain(svc, svc.registry, authority)
        with pytest.raises(IdentityError):
            chain.run_action(
                run_id="run-882663", domain="bangcle-contract",
                action="submit_to_oa", object_refs=["ht-2026-008"],
                params={"requestid": "882663", "action": "提交"},
                scopes=[f"propose:submit_to_oa:bangcle-contract"],
                subject="agent:assistant", kind="agent",
                reviewer_token=agent_tok,
            )
    finally:
        ai.close()


# ---------- 4) 幂等重放 ----------

def test_agent_run_idempotent_replay(bridge, authority):
    r1 = bridge.submit_to_oa_agent(
        1, run_id="run-882663", agent="assistant",
        requestid="882663", action="提交",
        reviewer_operator="rex", authority=authority,
        idempotency_key="k-agent-1",
    )
    r2 = bridge.submit_to_oa_agent(
        1, run_id="run-882663", agent="assistant",
        requestid="882663", action="提交",
        reviewer_operator="rex", authority=authority,
        idempotency_key="k-agent-1",
    )
    assert r1["ok"] is True
    assert r1["proposal_status"] == "committed"
    assert r2["idempotent_replay"] is True
    assert r2["proposal_id"] == r1["proposal_id"]
    st = bridge.status(1)
    assert len(st["decision_chain"]) == 1
