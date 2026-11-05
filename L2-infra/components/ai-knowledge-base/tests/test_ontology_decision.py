"""DecisionService tests (详设 §3.4): record / replay / stats."""
import json
import os
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import ActionRegistry, AssemblyGate, IdentityService
from ai_kb.ontology.decision import DecisionService


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
def decisions(kb):
    return DecisionService(kb)


def test_record_minimal(decisions):
    rid = decisions.record(
        "test-domain", "submit_contract", ["HT-001"],
        "rex", "human", change_set={"applied": True},
        result="allowed",
    )
    rec = decisions.get(rid)
    assert rec["action_type"] == "submit_contract"
    assert rec["object_refs"] == ["HT-001"]
    assert rec["change_set"] == {"applied": True}
    assert rec["result"] == "allowed"
    assert rec["evidence"] is None
    assert rec["proposal_id"] is None


def test_record_full_with_proposal(decisions):
    rid = decisions.record(
        "test-domain", "submit_contract",
        [{"object_type": "contract", "canonical_key": "HT-002"}],
        "bot-1", "agent",
        change_set={"before": {"x": 1}, "after": {"x": 2}},
        proposal_id=42, rationale="ok", evidence={"rules": ["r1"]},
        result="allowed",
    )
    rec = decisions.get(rid)
    assert rec["proposal_id"] == 42
    assert rec["actor_kind"] == "agent"
    assert rec["evidence"] == {"rules": ["r1"]}


def test_record_invalid_result(decisions):
    with pytest.raises(ValueError):
        decisions.record(
            "test-domain", "a", ["k"], "rex", "human",
            change_set={"applied": False}, result="weird",
        )


def test_record_invalid_actor_kind(decisions):
    with pytest.raises(ValueError):
        decisions.record(
            "test-domain", "a", ["k"], "rex", "alien",
            change_set={"applied": False},
        )


def test_record_missing_change_set(decisions):
    with pytest.raises(ValueError):
        decisions.record(
            "test-domain", "a", ["k"], "rex", "human", change_set=None,
        )


def test_record_bad_json_string(decisions):
    with pytest.raises(json.JSONDecodeError):
        decisions.record(
            "test-domain", "a", ["k"], "rex", "human",
            change_set="{not json",
        )


def test_replay_by_object(decisions):
    decisions.record(
        "test-domain", "submit_contract", ["HT-001"],
        "rex", "human", change_set={"applied": True},
    )
    decisions.record(
        "test-domain", "approve_payment", ["HT-001"],
        "rex", "human", change_set={"applied": True},
    )
    decisions.record(
        "test-domain", "submit_contract", ["HT-OTHER"],
        "rex", "human", change_set={"applied": True},
    )

    chain = decisions.replay("test-domain", "contract", "HT-001")
    assert len(chain) == 2
    assert [r["action_type"] for r in chain] == [
        "submit_contract", "approve_payment"
    ]


def test_replay_with_object_typed_refs(decisions):
    decisions.record(
        "test-domain", "merge",
        [{"object_type": "contract", "canonical_key": "HT-009"}],
        "rex", "human", change_set={"applied": True},
    )
    chain = decisions.replay("test-domain", "contract", "HT-009")
    assert len(chain) == 1
    assert chain[0]["object_refs"][0]["object_type"] == "contract"
    # other object_type doesn't match
    assert decisions.replay("test-domain", "product", "HT-009") == []


def test_replay_since_filter(decisions):
    decisions.record(
        "test-domain", "a", ["HT-001"], "rex", "human",
        change_set={"applied": True},
    )
    future = "2999-01-01T00:00:00"
    assert decisions.replay(
        "test-domain", "contract", "HT-001", since=future
    ) == []


def test_stats(decisions):
    decisions.record(
        "test-domain", "submit_contract", ["HT-001"], "rex", "human",
        change_set={"applied": True}, result="allowed",
    )
    decisions.record(
        "test-domain", "submit_contract", ["HT-002"], "rex", "human",
        change_set={"applied": False}, result="rejected",
    )
    decisions.record(
        "test-domain", "pay", ["HT-001"], "rex", "human",
        change_set={"applied": True}, result="allowed",
    )
    stats = decisions.stats("test-domain")
    assert stats["total"] == 3
    assert stats["by_result"] == {"allowed": 2, "rejected": 1}
    assert stats["by_action_type"]["submit_contract"] == 2

    filtered = decisions.stats(
        "test-domain", action_type="submit_contract", result="rejected"
    )
    assert filtered["total"] == 1
