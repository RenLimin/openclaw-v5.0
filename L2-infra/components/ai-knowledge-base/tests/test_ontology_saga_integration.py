"""P4 multi-step writeback integration: ProposalService.commit with
SagaOrchestrator (详设 §3.5). Real temporary SQLite + real memory connectors.
"""
import json
import os
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import ActionRegistry, AssemblyGate, IdentityService, ProposalService
from tests.ont_handlers import MemoryConnector

PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string", "minLength": 1},
        "target_state": {"type": "string", "enum": ["submitted"]},
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
    db.init_ontology_saga_tables()
    db.get_or_create_domain("Test Domain", "test-domain", "Test")
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture()
def reg(kb):
    gate = AssemblyGate()
    gate.open()
    r = ActionRegistry(kb, gate=gate)
    r.register_function(
        "test-domain", "validate_submit_state", "rule",
        "tests.ont_handlers:validate_submit_state", deterministic=True,
    )
    aid = r.register_action_type(
        "test-domain", "submit_contract", "contract",
        PARAMS_SCHEMA,
        precondition={"fn": "validate_submit_state"},
        required_approval="none", writeback_target="oa",
    )
    return r, aid


@pytest.fixture()
def ident(kb):
    ids = IdentityService(kb)
    a = ids.register_identity("test-domain", "contract", "HT-001", "oa", "C1")
    kb.execute("UPDATE ont_identity SET metadata = ? WHERE id = ?",
               (json.dumps({"state": "draft"}), a))
    kb.commit()
    return ids


def _svc(kb, reg, connectors, default=None):
    return ProposalService(
        kb, reg[0], connectors=connectors, default_connector=default,
    )


def _propose(ps, key=None):
    return ps.propose_action(
        "test-domain", "submit_contract", ["HT-001"],
        {"contract_no": "HT-001", "target_state": "submitted"},
        caller_id="agent-1", caller_kind="agent",
        rationale="multi-step saga test", idempotency_key=key,
    )


# --- 多步全成功：committed + evidence 含 saga_report ---

def test_multi_step_all_success(kb, reg, ident):
    oa, wecom = MemoryConnector("oa"), MemoryConnector("wecom")
    reg[0].register_writeback_steps(reg[1], [
        {"seq": 1, "connector_key": "oa"},
        {"seq": 2, "connector_key": "wecom"},
    ])
    ps = _svc(kb, reg, {"oa": oa, "wecom": wecom})

    p = _propose(ps)
    assert ps.validate(p["id"])["ok"] is True
    out = ps.commit(p["id"])

    assert out["result"] == "allowed"
    assert oa.applied == 1 and wecom.applied == 1
    # evidence 带 saga_report
    rec = dict(ps.db.execute(
        "SELECT * FROM ont_decision_record WHERE proposal_id = ?", (p["id"],)
    ).fetchone())
    ev = json.loads(rec["evidence"])
    assert ev["saga_report"]["ok"] is True
    assert ev["saga_report"]["executed_steps"] == ["oa", "wecom"]
    assert ev["connector"] == "oa+wecom"


# --- 中间步失败：ROLLBACK + 逆序补偿 + failed + compensated ---

def test_multi_step_mid_failure_compensates_reversed(kb, reg, ident):
    oa, wecom = MemoryConnector("oa"), MemoryConnector("wecom", fail_on_apply=True)
    reg[0].register_writeback_steps(reg[1], [
        {"seq": 1, "connector_key": "oa"},
        {"seq": 2, "connector_key": "wecom"},
    ])
    ps = _svc(kb, reg, {"oa": oa, "wecom": wecom})

    p = _propose(ps)
    ps.validate(p["id"])
    with pytest.raises(Exception):
        ps.commit(p["id"])

    assert oa.compensated == 1  # 逆序补偿已成功步骤
    row = dict(ps.db.execute(
        "SELECT * FROM ont_proposal WHERE id = ?", (p["id"],)
    ).fetchone())
    assert row["status"] == "failed"
    rec = dict(ps.db.execute(
        "SELECT * FROM ont_decision_record WHERE proposal_id = ?", (p["id"],)
    ).fetchone())
    assert rec["result"] == "compensated"
    ev = json.loads(rec["evidence"])
    assert ev["saga_report"]["failed_step"] == "wecom"
    assert ev["saga_report"]["compensated"] == ["oa"]


# --- 含不可补偿连接器：人工对账记录 ---

def test_multi_step_uncompensable_reconciliation(kb, reg, ident):
    # 三步：oa 成功可补偿；wecom 成功但不可补偿；erp apply 失败。
    # 失败后逆序补偿：先 wecom → CompensationUnavailable → 标记对账；
    # 继续补偿 oa（成功，尽量多回滚）。
    oa = MemoryConnector("oa")
    wecom = MemoryConnector("wecom", not_compensable=True)
    erp = MemoryConnector("erp", fail_on_apply=True)
    reg[0].register_writeback_steps(reg[1], [
        {"seq": 1, "connector_key": "oa"},
        {"seq": 2, "connector_key": "wecom"},
        {"seq": 3, "connector_key": "erp"},
    ])
    ps = _svc(kb, reg, {"oa": oa, "wecom": wecom, "erp": erp})

    p = _propose(ps)
    ps.validate(p["id"])
    with pytest.raises(Exception):
        ps.commit(p["id"])

    row = dict(ps.db.execute(
        "SELECT * FROM ont_proposal WHERE id = ?", (p["id"],)
    ).fetchone())
    assert row["status"] == "failed"
    rec = dict(ps.db.execute(
        "SELECT * FROM ont_decision_record WHERE proposal_id = ?", (p["id"],)
    ).fetchone())
    assert rec["result"] == "compensated"
    ev = json.loads(rec["evidence"])
    assert ev["reconciliation"] == "manual"
    assert ev["saga_report"]["failed_step"] == "erp"
    assert "wecom" in ev["saga_report"]["compensation_unavailable"]
    assert ev["saga_report"]["reconciliation_required"] is True
    # 更早成功步骤仍被补偿（尽量多回滚）
    assert oa.compensated == 1
    # wecom 自身 apply 成功但补偿被标记对账
    assert wecom.applied == 1


# --- 单步路径不破坏（向后兼容）---

def test_single_step_path_unchanged(kb, reg, ident):
    oa = MemoryConnector("oa")
    ps = _svc(kb, reg, {"oa": oa}, default=MemoryConnector("null"))
    p = _propose(ps)
    ps.validate(p["id"])
    out = ps.commit(p["id"])
    assert out["result"] == "allowed"
    rec = dict(ps.db.execute(
        "SELECT * FROM ont_decision_record WHERE proposal_id = ?", (p["id"],)
    ).fetchone())
    ev = json.loads(rec["evidence"])
    assert ev["saga_report"] is None  # 单步不走 saga_report


# --- 幂等仍不重放（多步下）---

def test_multi_step_idempotent_replay(kb, reg, ident):
    oa, wecom = MemoryConnector("oa"), MemoryConnector("wecom")
    reg[0].register_writeback_steps(reg[1], [
        {"seq": 1, "connector_key": "oa"},
        {"seq": 2, "connector_key": "wecom"},
    ])
    ps = _svc(kb, reg, {"oa": oa, "wecom": wecom})

    p1 = _propose(ps, key="K1")
    ps.validate(p1["id"])
    ps.commit(p1["id"])
    # 同幂等键重复：返回既有，不重放
    p2 = _propose(ps, key="K1")
    assert p2["idempotent_replay"] is True
    assert oa.applied == 1 and wecom.applied == 1  # 未再次写回
