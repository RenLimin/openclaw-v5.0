"""OutputGuard tests (详设 §3.6): ABAC / schema / precondition / state-machine."""
import json
import os
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.guardrails.output_guard import OutputGuard
from ai_kb.ontology import (
    ActionRegistry,
    AssemblyGate,
    IdentityService,
    ProposalService,
)

PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string", "minLength": 1},
        "target_state": {"type": "string", "enum": ["submitted"]},
        "amount": {"type": "number", "minimum": 0},
    },
    "required": ["contract_no", "target_state"],
    "additionalProperties": False,
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


def _setup(kb, *, precondition, functions=None, identity_metadata=None):
    gate = AssemblyGate()
    gate.open()
    registry = ActionRegistry(kb, gate=gate)
    for fn_name, fn_kind, handler in (functions or []):
        registry.register_function(
            "test-domain", fn_name, fn_kind, handler, deterministic=True
        )
    registry.register_action_type(
        "test-domain", "submit_contract", "contract",
        PARAMS_SCHEMA, precondition=precondition,
        required_approval="human",
    )
    ids = IdentityService(kb)
    iid = ids.register_identity(
        "test-domain", "contract", "HT-001", "oa"
    )
    if identity_metadata is not None:
        kb.execute(
            "UPDATE ont_identity SET metadata=? WHERE id=?",
            (json.dumps(identity_metadata), iid),
        )
        kb.commit()
    return registry, ids


def _proposal_dict(kb):
    row = kb.execute("""
    SELECT p.* FROM ont_proposal p
    JOIN ont_action_type a ON a.id = p.action_type_id
    ORDER BY p.id DESC LIMIT 1
    """).fetchone()
    p = dict(row)
    p["params"] = json.loads(p["params"])
    p["target_snapshot"] = json.loads(p["target_snapshot"])
    return p


def _make_proposal(kb, ids, params):
    props = ProposalService(
        kb, ActionRegistry(kb)  # gate closed is fine for propose
    )
    # use a registry with closed gate; propose doesn't need gate open
    props.registry = _closed_registry_with_data(kb)
    return props.propose_action(
        "test-domain", "submit_contract", ["HT-001"], params,
        caller_id="agent-1", caller_kind="agent",
    )


def _closed_registry_with_data(kb):
    return ActionRegistry(kb, gate=AssemblyGate(open_by_default=False))


GOOD_PARAMS = {
    "contract_no": "HT-001", "target_state": "submitted", "amount": 100
}


def test_pass_all_stages(kb):
    registry, ids = _setup(
        kb,
        precondition={
            "fn": "validate_submit_state",
            "state_machine": "contract_state_machine",
        },
        functions=[
            ("validate_submit_state", "rule",
             "tests.ont_handlers:validate_submit_state"),
            ("contract_state_machine", "state_machine",
             "tests.ont_handlers:contract_state_machine"),
        ],
        identity_metadata={"state": "draft"},
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    guard = OutputGuard(registry)
    result = guard.validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    assert result["ok"] is True
    assert result["violations"] == []


def test_abac_denied(kb):
    registry, ids = _setup(
        kb, precondition=None,
        identity_metadata={
            "state": "draft",
            "permissions": {"allowed_roles": ["admin"]},
        },
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    guard = OutputGuard(registry)
    result = guard.validate_proposal(
        _proposal_dict(kb),
        {"user_id": "s", "role": "sales", "clearance": "internal"},
    )
    assert result["ok"] is False
    assert result["violations"][0]["stage"] == "abac"


def test_abac_clearance_denied(kb):
    registry, ids = _setup(
        kb, precondition=None,
        identity_metadata={
            "permissions": {"confidence_level": "restricted"},
        },
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "s", "role": "admin", "clearance": "internal"},
    )
    assert any(v["stage"] == "abac" for v in result["violations"])


def test_params_schema_type_error(kb):
    registry, ids = _setup(kb, precondition=None)
    _make_proposal(kb, ids, {"contract_no": 123, "target_state": "submitted"})
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    assert result["violations"][0]["stage"] == "params_schema"


def test_params_schema_missing_required(kb):
    registry, ids = _setup(kb, precondition=None)
    _make_proposal(kb, ids, {"target_state": "submitted"})
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    messages = " ".join(v["message"] for v in result["violations"])
    assert "contract_no" in messages


def test_params_schema_enum_and_additional(kb):
    registry, ids = _setup(kb, precondition=None)
    _make_proposal(kb, ids, {
        "contract_no": "HT-001", "target_state": "nope", "bogus": 1
    })
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    stages_msgs = [v["message"] for v in result["violations"]]
    assert any("enum" in m for m in stages_msgs)
    assert any("additional property" in m for m in stages_msgs)


def test_precondition_violation(kb):
    registry, ids = _setup(
        kb, precondition={"fn": "validate_submit_state"},
        functions=[("validate_submit_state", "rule",
                    "tests.ont_handlers:validate_submit_state")],
        identity_metadata={"state": "submitted"},
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    assert any(v["stage"] == "precondition" for v in result["violations"])
    rules = [v["rule"] for v in result["violations"]]
    assert "already_submitted" in rules


def test_state_machine_violation(kb):
    registry, ids = _setup(
        kb, precondition={"state_machine": "contract_state_machine"},
        functions=[("contract_state_machine", "state_machine",
                    "tests.ont_handlers:contract_state_machine")],
        identity_metadata={"state": "archived"},
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    sm = [v for v in result["violations"] if v["stage"] == "state_machine"]
    assert sm and sm[0]["rule"] == "illegal_transition"


def test_handler_raising_is_violation(kb):
    registry, ids = _setup(
        kb, precondition={"fn": "raise_fn"},
        functions=[("raise_fn", "rule", "tests.ont_handlers:raise_handler")],
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    assert "boom from handler" in result["violations"][0]["message"]


def test_handler_false_is_violation(kb):
    registry, ids = _setup(
        kb, precondition={"fn": "false_fn"},
        functions=[("false_fn", "rule", "tests.ont_handlers:false_handler")],
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    assert result["violations"][0]["stage"] == "precondition"


def test_missing_bound_function(kb):
    registry, ids = _setup(
        kb, precondition={"fn": "ghost"},
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    assert "not found" in result["violations"][0]["message"]


def test_state_machine_kind_mismatch(kb):
    registry, ids = _setup(
        kb, precondition={"state_machine": "rule_fn"},
        functions=[("rule_fn", "rule",
                    "tests.ont_handlers:validate_submit_state")],
    )
    _make_proposal(kb, ids, GOOD_PARAMS)
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "a", "role": "admin", "clearance": "internal"},
    )
    assert any(v["stage"] == "state_machine" for v in result["violations"])


def test_chain_collects_multiple_stages(kb):
    # ABAC + schema violations both reported (not fail-fast)
    registry, ids = _setup(
        kb, precondition=None,
        identity_metadata={"permissions": {"allowed_roles": ["admin"]}},
    )
    _make_proposal(kb, ids, {"target_state": "submitted"})
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "s", "role": "sales", "clearance": "internal"},
    )
    stages = {v["stage"] for v in result["violations"]}
    assert stages == {"abac", "params_schema"}


def test_fail_fast_stops_at_first(kb):
    registry, ids = _setup(
        kb, precondition=None,
        identity_metadata={"permissions": {"allowed_roles": ["admin"]}},
    )
    _make_proposal(kb, ids, {"target_state": "submitted"})
    result = OutputGuard(registry).validate_proposal(
        _proposal_dict(kb),
        {"user_id": "s", "role": "sales", "clearance": "internal"},
        fail_fast=True,
    )
    assert len(result["violations"]) == 1
    assert result["violations"][0]["stage"] == "abac"
