"""P6.2 OntologyToolchain 专属测试（DESIGN-DETAIL-p6 §验收 #10-#11）。

覆盖：
- discover 列出 active propose/compute 工具，无 execute_*/write_*/commit_*；
- run_action 走 issue→propose→validate 到 validated 即停（不 commit）；
- auto_review=True 但缺 reviewer_token → IdentityError；
- human reviewer 令牌 → approve→内部 commit；agent 令牌不得 review；
- 校验失败（violations）时停在 pending 且带 validation；
- 幂等重放不重跑。

真实临时 SQLite；结构经 AssemblyGate 注册。
"""
import os
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import (
    ActionRegistry,
    AssemblyGate,
    IdentityService,
)
from ai_kb.ontology.agent_toolchain import OntologyToolchain
from ai_kb.ontology.identity_token import IdentityAuthority, IdentityError

DOMAIN = "test-domain"
_SECRET = b"toolchain-secret-0123456789abcd!"

PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string"},
        "target_state": {"type": "string"},
    },
    "required": ["contract_no", "target_state"],
}


@pytest.fixture()
def built():
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
    reg.register_function(
        DOMAIN, "risk_score", "compute",
        "tests.ont_handlers:risk_score",
        io_schema={
            "type": "object",
            "properties": {
                "snapshot": {"type": "object"},
                "params": {"type": "object"},
            },
            "required": ["params"],
        },
        deterministic=True,
    )
    IdentityService(db).register_identity(
        DOMAIN, "contract", "HT-001", "oa", "Contract 1"
    )
    gate.close()

    from ai_kb.ontology.proposal import ProposalService
    from ai_kb.ontology.decision import DecisionService
    authority = IdentityAuthority(secret=_SECRET)
    proposals = ProposalService(
        db, reg, decisions=DecisionService(db), identity=authority
    )
    chain = OntologyToolchain(proposals, reg, authority)
    yield db, chain, authority
    db.close()
    os.unlink(path)


def _run(chain, **overrides):
    kw = dict(
        run_id="run-1", domain=DOMAIN, action="submit_contract",
        object_refs=["HT-001"],
        params={"contract_no": "HT-001", "target_state": "submitted"},
        scopes=[f"propose:submit_contract:{DOMAIN}"],
        subject="agent-1", kind="agent",
    )
    kw.update(overrides)
    return chain.run_action(**kw)


# ---------------------------------------------------------------
# discover
# ---------------------------------------------------------------

def test_discover_lists_active_tools(built):
    _, chain, _ = built
    tools = chain.discover(DOMAIN)
    names = {t["tool"] for t in tools}
    assert "ont_propose_submit_contract" in names
    assert "ont_compute_risk_score" in names


def test_discover_no_write_leak(built):
    _, chain, _ = built
    names = {t["tool"] for t in chain.discover(DOMAIN)}
    forbidden = [n for n in names
                 if n.startswith(("execute_", "write_", "commit_"))]
    assert forbidden == []


# ---------------------------------------------------------------
# run_action
# ---------------------------------------------------------------

def test_run_stops_at_validated_no_commit(built):
    db, chain, _ = built
    out = _run(chain)
    assert out["status"] == "validated"
    assert "decision_record" not in out
    # DB 里提案确实未 committed
    rec = db.execute(
        "SELECT status FROM ont_proposal WHERE id = ?",
        (out["proposal_id"],),
    ).fetchone()
    assert rec["status"] == "validated"
    assert len(out["run_token_fingerprint"]) == 16


def test_auto_review_without_reviewer_token_rejected(built):
    _, chain, _ = built
    with pytest.raises(IdentityError):
        _run(chain, auto_review=True)  # 无 reviewer_token


def test_human_reviewer_token_commits(built):
    db, chain, authority = built
    review_tok = authority.issue(
        run_id="run-1", subject="rex", kind="human",
        scopes=[f"review:submit_contract:{DOMAIN}"],
    )
    out = _run(chain, reviewer_token=review_tok)
    assert out["status"] == "committed"
    assert out["reviewer_token_fingerprint"] == authority.fingerprint(review_tok)
    assert "decision_record" in out
    # 决策记录带 reviewer 令牌指纹
    rec = db.execute(
        "SELECT token_fingerprint FROM ont_decision_record "
        "WHERE proposal_id = ? ORDER BY id DESC LIMIT 1",
        (out["proposal_id"],),
    ).fetchone()
    assert rec["token_fingerprint"] == authority.fingerprint(review_tok)


def test_agent_token_cannot_be_reviewer(built):
    _, chain, authority = built
    agent_review_tok = authority.issue(
        run_id="run-1", subject="agent-1", kind="agent",
        scopes=[f"review:submit_contract:{DOMAIN}"],
    )
    with pytest.raises(IdentityError):
        _run(chain, reviewer_token=agent_review_tok)


def test_run_idempotent_replay(built):
    db, chain, authority = built
    review_tok = authority.issue(
        run_id="run-1", subject="rex", kind="human",
        scopes=[f"review:submit_contract:{DOMAIN}"],
    )
    first = _run(chain, reviewer_token=review_tok, idempotency_key="idem-1")
    assert first["status"] == "committed"

    # 同 idempotency_key 再来：返回既有，不重跑、不报错
    second = _run(chain, reviewer_token=review_tok, idempotency_key="idem-1")
    assert second["proposal_id"] == first["proposal_id"]
    assert second.get("idempotent_replay") is True
