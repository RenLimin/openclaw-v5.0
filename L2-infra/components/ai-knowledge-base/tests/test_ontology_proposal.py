"""P3 ProposalService tests (详设 §3.3) + 5 golden benchmarks.

Real temporary SQLite; service internals exercised directly. HTTP/MCP
integration lives in tests/integration/.
"""
import json
import os
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import (
    ActionRegistry,
    AssemblyGate,
    IdentityService,
    ProposalService,
)
from ai_kb.ontology.decision import DecisionService
from ai_kb.guardrails.output_guard import OutputGuard

PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string", "minLength": 1},
        "target_state": {"type": "string", "enum": ["submitted"]},
        "amount": {"type": "number"},
    },
    "required": ["contract_no", "target_state"],
}


@pytest.fixture()
def kb():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = AIKB(db_path)
    db.init_db()
    db.init_ontology_identity_tables()
    db.init_ontology_kinetic_tables()
    db.init_ontology_proposal_tables()
    db.get_or_create_domain("Test Domain", "test-domain", "Test")
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture()
def registry(kb):
    gate = AssemblyGate()
    gate.open()
    reg = ActionRegistry(kb, gate=gate)
    reg.register_function(
        "test-domain", "validate_submit_state", "rule",
        "tests.ont_handlers:validate_submit_state", deterministic=True,
    )
    reg.register_function(
        "test-domain", "contract_state_machine", "state_machine",
        "tests.ont_handlers:contract_state_machine", deterministic=True,
    )
    reg.register_action_type(
        "test-domain", "submit_contract", "contract",
        PARAMS_SCHEMA,
        precondition={
            "fn": "validate_submit_state",
            "state_machine": "contract_state_machine",
        },
        required_approval="human", writeback_target=None,
    )
    return reg


@pytest.fixture()
def identities(kb):
    ids = IdentityService(kb)
    a = ids.register_identity(
        "test-domain", "contract", "HT-001", "oa", "Contract 1"
    )
    # metadata 记录对象处于 draft
    kb.execute(
        "UPDATE ont_identity SET metadata = ? WHERE id = ?",
        (json.dumps({"state": "draft"}), a),
    )
    kb.commit()
    ids.add_alias(a, "oa", "OA-001")
    return ids


@pytest.fixture()
def proposals(kb, registry):
    return ProposalService(kb, registry)


def _propose(proposals, key=None, caller="agent-1", params=None):
    return proposals.propose_action(
        "test-domain", "submit_contract", ["HT-001"],
        params or {"contract_no": "HT-001", "target_state": "submitted",
                   "amount": 100},
        caller_id=caller, caller_kind="agent",
        rationale="submit for approval", idempotency_key=key,
    )


# --- migration v10 ---

def test_migration_v10_registered(kb):
    assert kb.get_current_migration_version() == 10
    row = kb.execute(
        "SELECT name FROM kb_migration WHERE version = 10"
    ).fetchone()
    assert row[0] == "operational_ontology_proposal"


def test_proposal_tables_idempotent(kb):
    kb.init_ontology_proposal_tables()
    assert kb.get_current_migration_version() == 10


# --- propose: pending + snapshot, zero writes ---

def test_propose_creates_pending_with_snapshot(proposals, identities):
    out = _propose(proposals)
    assert out["status"] == "pending"
    snap = out["target_snapshot"]
    assert snap["object_type"] == "contract"
    assert len(snap["identities"]) == 1
    assert snap["identities"][0]["canonical_key"] == "HT-001"
    # target_snapshot NOT NULL
    assert isinstance(out["target_snapshot"], dict)


def test_propose_unknown_object_rejected(proposals, identities):
    # CWA: 未登记对象不允许提提案
    with pytest.raises(ValueError):
        proposals.propose_action(
            "test-domain", "submit_contract", ["NOPE"], {},
            caller_id="a", caller_kind="agent",
        )


# --- full state machine: validate -> review(approve) -> commit ---

def test_full_happy_path_commit(proposals, identities):
    p = _propose(proposals)
    pid = p["id"]

    v = proposals.validate(pid)
    assert v["ok"] is True
    assert v["violations"] == []
    assert proposals.get(pid)["status"] == "validated"

    # validated != committed at this point
    assert proposals.get(pid)["committed_at"] is None

    reviewed = proposals.review(pid, "approve", "rex", reviewer_kind="human")
    assert reviewed["status"] == "committed"
    assert reviewed["committed_at"] is not None

    # decision record exists, result=allowed, fields complete
    rec_row = kb = proposals.db.execute(
        "SELECT * FROM ont_decision_record WHERE proposal_id = ?", (pid,)
    ).fetchone()
    rec = dict(rec_row)
    assert rec["result"] == "allowed"
    assert json.loads(rec["object_refs"]) == ["HT-001"]
    cs = json.loads(rec["change_set"])
    assert cs["applied"] is True
    assert "before" in cs and "after" in cs
    ev = json.loads(rec["evidence"])
    assert ev["review_by"] == "rex"

    # audit details carry proposal/decision linkage
    audit = proposals.db.execute(
        "SELECT details FROM kb_audit_log WHERE operation_type = 'ont_commit' "
        "AND object_id = ?", (pid,)
    ).fetchone()
    details = json.loads(audit[0])
    assert details["proposal_id"] == pid
    assert "decision_record_id" in details


def test_validate_does_not_commit_invariant(proposals, identities):
    p = _propose(proposals)
    proposals.validate(p["id"])
    # validate 反复执行不产生业务变更：metadata 无 applied_changes
    meta = proposals.db.execute(
        "SELECT metadata FROM ont_identity WHERE canonical_key='HT-001'"
    ).fetchone()[0]
    assert json.loads(meta).get("applied_changes") is None
    assert proposals.get(p["id"])["status"] == "validated"


def test_validate_repeated_returns_cached(proposals, identities):
    p = _propose(proposals)
    proposals.validate(p["id"])
    again = proposals.validate(p["id"])
    assert again["ok"] is True


def test_review_reject_path(proposals, identities):
    p = _propose(proposals)
    proposals.validate(p["id"])
    out = proposals.review(p["id"], "reject", "rex", reviewer_kind="human")
    assert out["status"] == "rejected"
    assert out["committed_at"] is None
    rec = proposals.db.execute(
        "SELECT * FROM ont_decision_record WHERE proposal_id = ?", (p["id"],)
    ).fetchone()
    assert dict(rec)["result"] == "rejected"
    # no applied changes
    meta = proposals.db.execute(
        "SELECT metadata FROM ont_identity WHERE canonical_key='HT-001'"
    ).fetchone()[0]
    assert json.loads(meta).get("applied_changes") is None


def test_review_requires_validated(proposals, identities):
    p = _propose(proposals)
    with pytest.raises(ValueError):
        proposals.review(p["id"], "approve", "rex")


def test_agent_cannot_review_human_action(proposals, identities):
    p = _propose(proposals)
    proposals.validate(p["id"])
    with pytest.raises(PermissionError):
        proposals.review(p["id"], "approve", "bot", reviewer_kind="agent")


def test_commit_requires_validated(proposals, identities):
    p = _propose(proposals)
    with pytest.raises(ValueError):
        proposals.commit(p["id"])


def test_validation_violations_keep_pending(proposals, identities):
    p = _propose(proposals, params={
        "contract_no": "", "target_state": "submitted"
    })
    v = proposals.validate(p["id"])
    assert v["ok"] is False
    rules = {x["rule"] for x in v["violations"]}
    assert "minLength" in " ".join(x["message"] for x in v["violations"]) or v["violations"]
    # still pending (not rejected/committed)
    assert proposals.get(p["id"])["status"] == "pending"


# --- idempotency: duplicate submission has no side effects ---

def test_idempotent_duplicate_returns_existing(proposals, identities):
    first = _propose(proposals, key="idem-1")
    second = _propose(proposals, key="idem-1")
    assert second.get("idempotent_replay") is True
    assert second["id"] == first["id"]
    count = proposals.db.execute(
        "SELECT COUNT(*) FROM ont_proposal WHERE idempotency_key = 'idem-1'"
    ).fetchone()[0]
    assert count == 1


def test_idempotent_after_commit_no_replay(proposals, identities):
    p = _propose(proposals, key="idem-2")
    proposals.validate(p["id"])
    proposals.review(p["id"], "approve", "rex", reviewer_kind="human")
    # duplicate submit after commit -> existing proposal, status committed
    again = _propose(proposals, key="idem-2")
    assert again["id"] == p["id"]
    assert again["status"] == "committed"
    # commit idempotent: no second decision record
    n = proposals.db.execute(
        "SELECT COUNT(*) FROM ont_decision_record WHERE proposal_id = ?",
        (p["id"],),
    ).fetchone()[0]
    assert n == 1


# --- denied access leaves a trace (ABAC) ---

def test_abac_denial_recorded(kb, registry, identities):
    # restrict object to admin-only via identity metadata permissions
    kb.execute("""
    UPDATE ont_identity
    SET metadata = ?
    WHERE canonical_key = 'HT-001'
    """, (json.dumps({
        "state": "draft",
        "permissions": {"allowed_roles": ["admin"], "confidence_level": "internal"},
    }),))
    kb.commit()

    proposals = ProposalService(kb, registry)
    p = _propose(proposals, caller="sales-1")
    v = proposals.validate(p["id"], caller_attrs={
        "user_id": "sales-1", "role": "sales", "clearance": "internal",
    })
    assert v["ok"] is False
    stages = {x["stage"] for x in v["violations"]}
    assert "abac" in stages
    # validation attempt itself is audited
    audit = kb.execute(
        "SELECT COUNT(*) FROM kb_audit_log WHERE operation_type='ont_validate' "
        "AND object_id = ?", (p["id"],)
    ).fetchone()[0]
    assert audit >= 1


# --- commit failure: rollback + failed status ---

def test_commit_failure_marks_failed(kb, registry, identities):
    from ai_kb.ontology.connectors.base import (
        WritebackConnector, SagaContext,
    )

    class FailingConnector(WritebackConnector):
        name = "failing"

        def apply(self, ctx: SagaContext) -> None:
            ctx.add_step("failing")
            raise RuntimeError("source system down")

        def compensate(self, ctx: SagaContext) -> None:
            ctx.mark_success("failing.compensate", {})

    proposals = ProposalService(
        kb, registry,
        connectors={"oa-connector": FailingConnector()},
    )
    # action writeback_target is NULL -> default connector; swap default
    from ai_kb.ontology.connectors.base import NullConnector
    proposals.default_connector = FailingConnector()

    p = _propose(proposals)
    proposals.validate(p["id"])
    # direct internal commit test: simulate prior human approval marker
    kb.execute(
        "UPDATE ont_proposal SET review_by='rex', review_at=? WHERE id=?",
        (kb.get_now(), p["id"]),
    )
    kb.commit()
    with pytest.raises(RuntimeError):
        proposals.commit(p["id"])
    assert proposals.get(p["id"])["status"] == "failed"
    # compensated decision record written
    rec = kb.execute(
        "SELECT result FROM ont_decision_record WHERE proposal_id = ?",
        (p["id"],),
    ).fetchall()
    assert any(r["result"] == "compensated" for r in rec)


# --- assembly-time binding validation ---

def test_binding_validation_detects_missing_function(kb):
    gate = AssemblyGate()
    gate.open()
    reg = ActionRegistry(kb, gate=gate)
    reg.register_action_type(
        "test-domain", "orphan_action", "contract",
        PARAMS_SCHEMA, precondition={"fn": "ghost"},
        required_approval="none",
    )
    with pytest.raises(ValueError):
        reg.validate_action_bindings("test-domain", name="orphan_action")


def test_binding_validation_passes(registry):
    reports = registry.validate_action_bindings(
        "test-domain", name="submit_contract"
    )
    assert reports[0]["refs"]


# --- identity.merge P3 integration: real decision record ---

def test_identity_merge_writes_decision_record(kb):
    ids = IdentityService(kb)
    a = ids.register_identity("test-domain", "contract", "M-1", "oa")
    b = ids.register_identity("test-domain", "contract", "M-2", "oa")
    out = ids.merge(a, b, actor="rex")
    assert out["kind"] == "identity_merge"
    rid = out["decision_record_id"]
    rec = DecisionService(kb).get(rid)
    assert rec["result"] == "allowed"
    assert rec["action_type"] == "identity_merge"
    assert rec["change_set"]["merge"]["from_id"] == a


# =====================================================================
# Golden benchmarks (5): 提交 / 驳回 / 越权 / 重复 / 补偿
# =====================================================================

def test_golden_commit(proposals, identities):
    """G1 提交：全字段完整性 + 状态迁移。"""
    p = _propose(proposals, key="g1")
    proposals.validate(p["id"])
    out = proposals.review(p["id"], "approve", "rex", reviewer_kind="human")
    assert out["status"] == "committed"
    rec = proposals.db.execute(
        "SELECT * FROM ont_decision_record WHERE proposal_id = ?", (p["id"],)
    ).fetchone()
    d = dict(rec)
    for f in ("domain_id", "action_type", "object_refs", "actor_id",
              "actor_kind", "change_set", "result", "ts"):
        assert d[f] is not None
    assert d["result"] == "allowed"
    assert json.loads(d["evidence"])["review_by"] == "rex"


def test_golden_reject(proposals, identities):
    """G2 驳回：rejected 终态 + rejected 决策记录。"""
    p = _propose(proposals, key="g2")
    proposals.validate(p["id"])
    out = proposals.review(p["id"], "reject", "rex", reviewer_kind="human")
    assert out["status"] == "rejected"
    rec = proposals.db.execute(
        "SELECT result FROM ont_decision_record WHERE proposal_id = ?",
        (p["id"],),
    ).fetchone()
    assert rec["result"] == "rejected"


def test_golden_abac_denied(kb, registry, identities):
    """G3 越权：ABAC 拒绝，违规留痕，对象未变更。"""
    kb.execute(
        "UPDATE ont_identity SET metadata=? WHERE canonical_key='HT-001'",
        (json.dumps({
            "state": "draft",
            "permissions": {"allowed_roles": ["admin"]},
        }),),
    )
    kb.commit()
    proposals = ProposalService(kb, registry)
    p = _propose(proposals, key="g3", caller="s-1")
    v = proposals.validate(p["id"], caller_attrs={
        "user_id": "s-1", "role": "sales", "clearance": "internal",
    })
    assert any(x["stage"] == "abac" for x in v["violations"])
    meta = json.loads(kb.execute(
        "SELECT metadata FROM ont_identity WHERE canonical_key='HT-001'"
    ).fetchone()[0])
    assert meta.get("applied_changes") is None


def test_golden_duplicate(proposals, identities):
    """G4 重复：同幂等键只落 1 提案 1 决策记录。"""
    p1 = _propose(proposals, key="g4")
    proposals.validate(p1["id"])
    proposals.review(p1["id"], "approve", "rex", reviewer_kind="human")
    p2 = _propose(proposals, key="g4")
    assert p2["id"] == p1["id"]
    assert proposals.db.execute(
        "SELECT COUNT(*) FROM ont_proposal WHERE idempotency_key='g4'"
    ).fetchone()[0] == 1
    assert proposals.db.execute(
        "SELECT COUNT(*) FROM ont_decision_record WHERE proposal_id=?",
        (p1["id"],),
    ).fetchone()[0] == 1


def test_golden_compensation(kb, registry, identities):
    """G5 补偿：连接器失败 → ROLLBACK + failed + compensated 记录。"""
    from ai_kb.ontology.connectors.base import WritebackConnector, SagaContext

    class Boom(WritebackConnector):
        name = "boom"

        def apply(self, ctx):
            raise RuntimeError("writeback rejected")

        def compensate(self, ctx):
            ctx.mark_success("boom.compensate")

    proposals = ProposalService(kb, registry)
    proposals.default_connector = Boom()
    p = _propose(proposals, key="g5")
    proposals.validate(p["id"])
    kb.execute(
        "UPDATE ont_proposal SET review_by='rex', review_at=? WHERE id=?",
        (kb.get_now(), p["id"]),
    )
    kb.commit()
    with pytest.raises(RuntimeError):
        proposals.commit(p["id"])
    assert proposals.get(p["id"])["status"] == "failed"
    recs = kb.execute(
        "SELECT result FROM ont_decision_record WHERE proposal_id=?",
        (p["id"],),
    ).fetchall()
    assert any(r["result"] == "compensated" for r in recs)
