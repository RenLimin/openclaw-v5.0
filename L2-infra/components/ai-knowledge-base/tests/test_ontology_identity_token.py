"""P6.1 run-scoped 身份令牌专属测试（DESIGN-DETAIL-p6 §验收 #4-#9）。

覆盖：
- 令牌签发 / 验签往返 / 篡改拒绝 / 过期拒绝；
- scope 授权与通配，越权 scope → ScopeDenied；
- Proposal Gate enforce=True：缺 token fail-closed；
- claims.sub/kind 与自报 caller 冲突 → InvalidToken；
- 审批令牌指纹落 ont_decision_record.token_fingerprint；
- enforce_identity=False 历史逃生口；identity=None 完全兼容。

真实临时 SQLite + AssemblyGate 开关注册结构；无第三方依赖。
"""
import json
import os
import tempfile
import time

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import (
    ActionRegistry,
    AssemblyGate,
    IdentityService,
    ProposalService,
)
from ai_kb.ontology.identity_token import (
    IdentityAuthority,
    IdentityError,
    InvalidToken,
    ScopeDenied,
    TokenExpired,
    operator_token,
)

DOMAIN = "test-domain"
_SECRET = b"unit-secret-0123456789abcdef!"

PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string"},
        "target_state": {"type": "string"},
    },
    "required": ["contract_no", "target_state"],
}


@pytest.fixture()
def kb():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = AIKB(path)
    db.init_db()
    db.init_ontology_identity_tables()
    db.init_ontology_kinetic_tables()
    db.init_ontology_proposal_tables()
    db.get_or_create_domain("Test Domain", DOMAIN, "Test")
    gate = AssemblyGate()
    gate.open()
    reg = ActionRegistry(db, gate=gate)
    reg.register_action_type(
        DOMAIN, "submit_contract", "contract",
        PARAMS_SCHEMA, required_approval="human", writeback_target=None,
    )
    IdentityService(db).register_identity(
        DOMAIN, "contract", "HT-001", "oa", "Contract 1"
    )
    gate.close()
    yield db
    db.close()
    os.unlink(path)


@pytest.fixture()
def authority():
    return IdentityAuthority(secret=_SECRET)


def _svc(kb, authority, enforce=True):
    reg = ActionRegistry(kb, gate=AssemblyGate(open_by_default=False))
    return ProposalService(
        kb, reg, identity=authority, enforce_identity=enforce
    )


_PARAMS = {"contract_no": "HT-001", "target_state": "submitted"}


# ---------------------------------------------------------------
# 令牌原语
# ---------------------------------------------------------------

def test_issue_verify_roundtrip(authority):
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    claims = authority.verify(tok)
    assert claims["sub"] == "agent-1"
    assert claims["kind"] == "agent"
    assert claims["run_id"] == "run-1"
    assert claims["scopes"] == [f"propose:submit_contract:{DOMAIN}"]


def test_tampered_signature_rejected(authority):
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    payload, sig = tok.split(".")
    # flip last char of signature
    flipped_sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
    with pytest.raises(InvalidToken):
        authority.verify(f"{payload}.{flipped_sig}")


def test_expired_token_rejected(authority):
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
        ttl=-1000,  # 已过期（超出 leeway）
    )
    with pytest.raises(TokenExpired):
        authority.verify(tok)


def test_wrong_secret_rejected():
    a1 = IdentityAuthority(secret=b"secret-one-0123456789abcdef!")
    a2 = IdentityAuthority(secret=b"secret-two-0123456789abcdef!")
    tok = a1.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    with pytest.raises(InvalidToken):
        a2.verify(tok)


def test_scope_wildcard_authorizes(authority):
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"*:*:{DOMAIN}"],
    )
    claims = authority.verify(tok)
    assert authority.authorize(claims, "propose", "submit_contract", DOMAIN)
    assert authority.authorize(claims, "review", "anything", DOMAIN)


def test_scope_mismatch_denied(authority):
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    claims = authority.verify(tok)
    with pytest.raises(ScopeDenied):
        authority.authorize(claims, "review", "submit_contract", DOMAIN)
    with pytest.raises(ScopeDenied):
        authority.authorize(claims, "propose", "other_action", DOMAIN)


def test_invalid_scope_rejected_at_issue(authority):
    with pytest.raises(InvalidToken):
        authority.issue(
            run_id="run-1", subject="agent-1", kind="agent",
            scopes=["bogus-scope"],
        )


def test_operator_token_is_human_wildcard(authority):
    tok = operator_token(authority, "rex", domain_code=DOMAIN)
    claims = authority.verify(tok)
    assert claims["kind"] == "human"
    assert claims["sub"] == "operator:rex"
    assert authority.authorize(claims, "review", "submit_contract", DOMAIN)


def test_fingerprint_stable_short(authority):
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    fp = authority.fingerprint(tok)
    assert len(fp) == 16
    assert fp == authority.fingerprint(tok)  # 稳定
    # 不同令牌指纹不同（jti 随机）
    tok2 = authority.issue(
        run_id="run-2", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    assert fp != authority.fingerprint(tok2)


# ---------------------------------------------------------------
# Proposal Gate fail-closed
# ---------------------------------------------------------------

def test_propose_without_token_failclosed(kb, authority):
    svc = _svc(kb, authority, enforce=True)
    with pytest.raises(IdentityError):
        svc.propose_action(
            DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
            caller_id="agent-1", caller_kind="agent",
        )


def test_propose_with_valid_token_succeeds(kb, authority):
    svc = _svc(kb, authority)
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    out = svc.propose_action(
        DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
        caller_id="agent-1", caller_kind="agent", token=tok,
    )
    assert out["status"] == "pending"


def test_propose_caller_kind_mismatch_rejected(kb, authority):
    """令牌 kind=agent，但自报 caller_kind=human → InvalidToken。"""
    svc = _svc(kb, authority)
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    with pytest.raises(InvalidToken):
        svc.propose_action(
            DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
            caller_id="agent-1", caller_kind="human", token=tok,
        )


def test_propose_caller_id_mismatch_rejected(kb, authority):
    """令牌 sub=agent-1，但自报 caller_id=impostor → InvalidToken。"""
    svc = _svc(kb, authority)
    tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    with pytest.raises(InvalidToken):
        svc.propose_action(
            DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
            caller_id="impostor", caller_kind="agent", token=tok,
        )


# ---------------------------------------------------------------
# review 指纹落决策记录
# ---------------------------------------------------------------

def test_review_requires_token_and_records_fingerprint(kb, authority):
    svc = _svc(kb, authority)
    p_tok = authority.issue(
        run_id="run-1", subject="rex", kind="human",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    proposed = svc.propose_action(
        DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
        caller_id="rex", caller_kind="human", token=p_tok,
    )
    pid = proposed["id"]
    svc.validate(pid)

    r_tok = authority.issue(
        run_id="run-1", subject="rex", kind="human",
        scopes=[f"review:submit_contract:{DOMAIN}"],
    )
    out = svc.review(pid, "approve", "rex", token=r_tok)
    assert out["status"] == "committed"

    rec = kb.execute(
        "SELECT token_fingerprint FROM ont_decision_record "
        "WHERE proposal_id = ? ORDER BY id DESC LIMIT 1",
        (pid,),
    ).fetchone()
    assert rec["token_fingerprint"] == authority.fingerprint(r_tok)


def test_reject_records_fingerprint(kb, authority):
    svc = _svc(kb, authority)
    p_tok = authority.issue(
        run_id="run-1", subject="rex", kind="human",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    proposed = svc.propose_action(
        DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
        caller_id="rex", caller_kind="human", token=p_tok,
    )
    pid = proposed["id"]
    svc.validate(pid)

    r_tok = authority.issue(
        run_id="run-1", subject="rex", kind="human",
        scopes=[f"review:submit_contract:{DOMAIN}"],
    )
    out = svc.review(pid, "reject", "rex", token=r_tok)
    assert out["status"] == "rejected"
    rec = kb.execute(
        "SELECT token_fingerprint FROM ont_decision_record "
        "WHERE proposal_id = ? ORDER BY id DESC LIMIT 1",
        (pid,),
    ).fetchone()
    assert rec["token_fingerprint"] == authority.fingerprint(r_tok)


def test_agent_cannot_review_human_action_even_with_token(kb, authority):
    svc = _svc(kb, authority)
    p_tok = authority.issue(
        run_id="run-1", subject="rex", kind="human",
        scopes=[f"propose:submit_contract:{DOMAIN}"],
    )
    proposed = svc.propose_action(
        DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
        caller_id="rex", caller_kind="human", token=p_tok,
    )
    pid = proposed["id"]
    svc.validate(pid)

    # agent 持 review scope 仍不得审 human 级动作
    a_tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"review:submit_contract:{DOMAIN}"],
    )
    with pytest.raises((InvalidToken, PermissionError)):
        svc.review(pid, "approve", "agent-1",
                   reviewer_kind="agent", token=a_tok)


# ---------------------------------------------------------------
# 兼容 / 逃生口
# ---------------------------------------------------------------

def test_enforce_false_allows_missing_token(kb, authority):
    """enforce_identity=False：缺 token 走 fail-open（仅测试/历史）。"""
    svc = _svc(kb, authority, enforce=False)
    out = svc.propose_action(
        DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
        caller_id="agent-1", caller_kind="agent",
    )
    assert out["status"] == "pending"


def test_identity_none_fully_compatible(kb):
    """未配置 identity：身份治理未启用，行为同 P5（向后兼容）。"""
    reg = ActionRegistry(kb, gate=AssemblyGate(open_by_default=False))
    svc = ProposalService(kb, reg)  # identity=None
    out = svc.propose_action(
        DOMAIN, "submit_contract", ["HT-001"], _PARAMS,
        caller_id="agent-1", caller_kind="agent",
    )
    assert out["status"] == "pending"
    pid = out["id"]
    svc.validate(pid)
    reviewed = svc.review(pid, "approve", "rex")
    assert reviewed["status"] == "committed"
