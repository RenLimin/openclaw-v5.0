"""P5.1 MCP dynamic tool enumeration tests (DESIGN-DETAIL §3, PLAN §2).

Covers:
- dynamic ont_propose_<action> / ont_compute_<function> descriptors and
  schemas (including wrapper fields);
- non-deterministic functions are not exposed;
- tool-name conflict -> list_tools() raises ValueError (fail-fast);
- no execute_*/write_*/commit_* leak across the full tool set;
- static ontology descriptors stay byte-for-byte compatible.

Real temporary SQLite; sample structure is registered via ActionRegistry
with AssemblyGate open, then closed before the runtime handler starts.
"""
import os
import re
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import (
    ActionRegistry,
    AssemblyGate,
    IdentityService,
)
from ai_kb.ontology.identity_token import IdentityAuthority
from mcp.server import KBMCPHandler

DOMAIN_CODE = "test-domain"

# Fixed secret injected into the handler so tests can mint real tokens
# without touching ~/.openclaw/state/ontology-identity.secret.
_SECRET = b"test-secret-0123456789abcdef-test"


def _mint(kind, subject, verb, action, run_id="test-run"):
    auth = IdentityAuthority(secret=_SECRET)
    return auth.issue(
        run_id=run_id, subject=subject, kind=kind,
        scopes=[f"{verb}:{action}:{DOMAIN_CODE}"],
    )

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string"},
        "amount": {"type": "number"},
    },
    "required": ["contract_no"],
}

COMPUTE_IO_SCHEMA = {
    "type": "object",
    "properties": {
        "snapshot": {"type": "object"},
        "params": {"type": "object"},
    },
    "required": ["params"],
}


@pytest.fixture()
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    db = AIKB(path)
    db.init_db()
    db.init_ontology_identity_tables()
    db.init_ontology_kinetic_tables()
    db.init_ontology_proposal_tables()
    db.get_or_create_domain("Test Domain", DOMAIN_CODE, "Test")

    gate = AssemblyGate()
    gate.open()
    registry = ActionRegistry(db, gate=gate)
    registry.register_action_type(
        DOMAIN_CODE, "demo_action", "contract",
        ACTION_SCHEMA, required_approval="human",
        writeback_target="oa_writeback",
    )
    registry.register_function(
        DOMAIN_CODE, "demo_compute", "compute",
        "tests.ont_handlers:risk_score",
        io_schema=COMPUTE_IO_SCHEMA, deterministic=True,
    )
    # non-deterministic function must never be exposed as a compute tool
    registry.register_function(
        DOMAIN_CODE, "guess_risk", "risk",
        "tests.ont_handlers:risk_score",
        io_schema=COMPUTE_IO_SCHEMA, deterministic=False,
    )
    IdentityService(db).register_identity(
        DOMAIN_CODE, "contract", "HT-001", "oa", "Contract 1"
    )
    gate.close()
    db.close()
    yield path
    os.unlink(path)


@pytest.fixture()
def handler(db_path):
    h = KBMCPHandler(
        db_path, instance_code=DOMAIN_CODE, identity_secret=_SECRET,
    )
    yield h
    h.close()


def _by_name(tools):
    return {t["name"]: t for t in tools}


# --- dynamic enumeration ---

def test_dynamic_propose_tool_descriptor(handler):
    tools = _by_name(handler.list_tools())
    assert "ont_propose_demo_action" in tools
    descriptor = tools["ont_propose_demo_action"]
    assert descriptor["category"] == "propose_"
    props = descriptor["inputSchema"]["properties"]
    # params_schema properties surface directly on the tool
    assert props["contract_no"] == {"type": "string"}
    assert props["amount"] == {"type": "number"}
    # wrapper fields added by enumeration
    for field in ("object_refs", "caller_id", "caller_kind",
                  "rationale", "idempotency_key"):
        assert field in props
    required = descriptor["inputSchema"]["required"]
    assert "contract_no" in required
    assert "object_refs" in required
    # description auto-generated from object_type / writeback_target
    desc = descriptor["description"]
    assert "contract" in desc
    assert "oa_writeback" in desc


def test_dynamic_compute_tool_descriptor(handler):
    tools = _by_name(handler.list_tools())
    assert "ont_compute_demo_compute" in tools
    descriptor = tools["ont_compute_demo_compute"]
    assert descriptor["category"] == "compute_"
    props = descriptor["inputSchema"]["properties"]
    assert set(props) == {"snapshot", "params"}
    assert descriptor["inputSchema"]["required"] == ["params"]


def test_non_deterministic_function_not_exposed(handler):
    names = set(_by_name(handler.list_tools()))
    assert "ont_compute_guess_risk" not in names


# --- dynamic dispatch ---

def test_dispatch_propose_creates_pending_proposal(handler):
    result = handler.call_tool("ont_propose_demo_action", {
        "object_refs": ["HT-001"],
        "contract_no": "HT-001",
        "amount": 500,
        "caller_id": "rex",
        "caller_kind": "human",
        "rationale": "p51 test",
        "token": _mint("human", "rex", "propose", "demo_action"),
    })
    assert result["status"] == "pending"
    from ai_kb.ontology.actions import ActionRegistry as _AR
    _ont = handler._get_ontology_services()
    _action = dict(_ont["kb"].execute(
        "SELECT name FROM ont_action_type WHERE id = ?",
        (result["action_type_id"],),
    ).fetchone())
    assert _action["name"] == "demo_action"
    # flattened top-level action params land in the proposal params
    assert result["params"]["contract_no"] == "HT-001"
    assert result["params"]["amount"] == 500


def test_dispatch_compute_advice_only(handler):
    result = handler.call_tool("ont_compute_demo_compute", {
        "snapshot": {},
        "params": {"amount": 2_000_000},
    })
    assert result["function"] == "demo_compute"
    assert result["result"]["risk_level"] == "high"


# --- name conflict fail-fast ---

def test_name_conflict_raises_valueerror(db_path):
    # Register a second active version of demo_action: list_actions returns
    # both versions -> duplicate ont_propose_demo_action tool name.
    db = AIKB(db_path)
    registry = ActionRegistry(db, gate=AssemblyGate(open_by_default=True))
    registry.register_action_type(
        DOMAIN_CODE, "demo_action", "contract",
        ACTION_SCHEMA, version=2, required_approval="human",
    )
    db.close()

    handler = KBMCPHandler(db_path, instance_code=DOMAIN_CODE)
    with pytest.raises(ValueError, match="ont_propose_demo_action"):
        handler.list_tools()
    handler.close()


# --- no execute / write / commit leak ---

def test_no_execute_tools_leak(handler):
    forbidden = re.compile(r"(^|_)(execute|write|commit)_")
    names = [t["name"] for t in handler.list_tools()]
    leaks = [n for n in names if forbidden.search(n)]
    assert leaks == []


# --- backward compatibility: static six ontology descriptors ---

def test_static_six_ontology_descriptors_unchanged(handler):
    expected = [
        ("ont_query_object", "query_"),
        ("ont_compute_risk", "compute_"),
        ("ont_propose_action", "propose_"),
        ("ont_list_actions", "query_"),
        ("ont_get_proposal", "query_"),
        ("ont_review_proposal", "propose_"),
    ]
    descriptors = handler.ontology_tool_descriptors()
    assert len(descriptors) == 6
    assert [(d["name"], d["category"]) for d in descriptors] == expected
    # every descriptor keeps the MCP shape
    for d in descriptors:
        assert d["inputSchema"]["type"] == "object"
        assert isinstance(d["inputSchema"]["properties"], dict)
        assert isinstance(d["description"], str) and d["description"]

    # static tools remain present in the full enumerated set
    names = set(_by_name(handler.list_tools()))
    for name, _ in expected:
        assert name in names
