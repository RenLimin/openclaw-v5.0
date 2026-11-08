"""E2E integration for P3 Proposal Gate (real HTTP + real MCP descriptors).

Per delivery rules: permission/access paths are exercised over a real HTTP
server (uvicorn in a background thread) — no FastAPI TestClient. MCP tool
descriptor registration is asserted for the three-way classification and
the absence of execute_*/write_*/commit_* tools.
"""
import json
import os
import sys
import time

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ai_kb.db import AIKB
from ai_kb.ontology import ActionRegistry, AssemblyGate, IdentityService
from ai_kb.ontology.identity_token import IdentityAuthority
from mcp.server import KBMCPHandler

_SECRET = b"test-secret-0123456789abcdef-e2e"


def _mint(kind, subject, verb, action, domain="ont", run_id="e2e-run"):
    auth = IdentityAuthority(secret=_SECRET)
    return auth.issue(
        run_id=run_id, subject=subject, kind=kind,
        scopes=[f"{verb}:{action}:{domain}"],
    )

PARAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "contract_no": {"type": "string", "minLength": 1},
        "target_state": {"type": "string", "enum": ["submitted"]},
    },
    "required": ["contract_no", "target_state"],
}


@pytest.fixture()
def ontology_env(tmp_path):
    db_path = str(tmp_path / "ont.db")
    kb = AIKB(db_path)
    kb.init_db()
    kb.init_ontology_identity_tables()
    kb.init_ontology_kinetic_tables()
    kb.init_ontology_proposal_tables()
    kb.get_or_create_domain("Ont Domain", "ont", "ontology e2e")

    # Assembly channel: register structure (gate open)
    gate = AssemblyGate()
    gate.open()
    registry = ActionRegistry(kb, gate=gate)
    registry.register_function(
        "ont", "validate_submit_state", "rule",
        "tests.ont_handlers:validate_submit_state", deterministic=True,
    )
    registry.register_function(
        "ont", "contract_state_machine", "state_machine",
        "tests.ont_handlers:contract_state_machine", deterministic=True,
    )
    registry.register_action_type(
        "ont", "submit_contract", "contract", PARAMS_SCHEMA,
        precondition={
            "fn": "validate_submit_state",
            "state_machine": "contract_state_machine",
        },
        required_approval="human",
    )
    registry.validate_action_bindings("ont")

    ids = IdentityService(kb)
    iid = ids.register_identity("ont", "contract", "HT-100", "oa", "C100")
    kb.execute(
        "UPDATE ont_identity SET metadata=? WHERE id=?",
        (json.dumps({"state": "draft"}), iid),
    )
    kb.commit()
    ids.add_alias(iid, "oa", "OA-100")
    kb.close()
    return db_path


@pytest.fixture()
def http_server(ontology_env):
    """Start the real FastAPI server on an ephemeral port in a thread."""
    import threading

    import uvicorn

    # Configure the module-level app against the temp DB
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    import api.server as rest

    rest._service_registry.clear()
    rest._ont_registry.clear()
    rest._db_path = ontology_env
    rest._load_instances(ontology_env)
    assert "ont" in rest._service_registry

    config = uvicorn.Config(
        rest.app, host="127.0.0.1", port=0, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to come up and discover the actual port
    base_url = None
    for _ in range(50):
        if server.started and server.servers:
            sock = server.servers[0].sockets[0]
            base_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            break
        time.sleep(0.05)
    assert base_url, "server failed to start"

    # ready check
    for _ in range(50):
        try:
            r = requests.get(f"{base_url}/health", timeout=1)
            if r.status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.05)

    yield base_url
    server.should_exit = True
    thread.join(timeout=5)


# --- MCP descriptors: three-way classification ---

def test_mcp_three_way_classification(ontology_env):
    handler = KBMCPHandler(ontology_env, instance_code="ont")
    tools = handler.list_tools()
    names = {t["name"] for t in tools}

    # Six ontology tools registered
    expected = {
        "ont_query_object", "ont_compute_risk", "ont_propose_action",
        "ont_list_actions", "ont_get_proposal", "ont_review_proposal",
    }
    assert expected <= names

    ont_tools = [t for t in tools if t["name"] in expected]
    categories = {t["name"]: t["category"] for t in ont_tools}
    assert categories["ont_query_object"] == "query_"
    assert categories["ont_list_actions"] == "query_"
    assert categories["ont_get_proposal"] == "query_"
    assert categories["ont_compute_risk"] == "compute_"
    assert categories["ont_propose_action"] == "propose_"
    assert categories["ont_review_proposal"] == "propose_"

    # Hard constraint: no execute_*/write_*/commit_* leakage anywhere
    forbidden = [n for n in names
                 if n.startswith(("execute_", "write_", "commit_"))]
    assert forbidden == []

    # Existing read-only tools still present
    assert "kb_query" in names
    handler.close()


def test_mcp_propose_review_chain(ontology_env):
    """Exercise proposal flow via real MCP tool dispatch (no direct commit tool)."""
    handler = KBMCPHandler(
        ontology_env, instance_code="ont", identity_secret=_SECRET,
    )

    proposed = handler.call_tool("ont_propose_action", {
        "action": "submit_contract",
        "object_refs": ["HT-100"],
        "params": {"contract_no": "HT-100", "target_state": "submitted"},
        "caller_id": "agent-9", "caller_kind": "agent",
        "idempotency_key": "mcp-1",
        "token": _mint("agent", "agent-9", "propose", "submit_contract"),
    })
    pid = proposed["id"]
    assert proposed["status"] == "pending"

    # list_actions discovery works
    listed = handler.call_tool("ont_list_actions", {})
    assert any(a["name"] == "submit_contract"
               for a in listed["actions"])

    # get proposal
    got = handler.call_tool("ont_get_proposal", {"proposal_id": pid})
    assert got["status"] == "pending"

    # compute risk (advice only)
    risk = handler.call_tool("ont_compute_risk", {
        "function": "risk_score",
        "snapshot": proposed["target_snapshot"],
        "params": {"amount": 2_000_000},
    })
    # risk_score isn't registered in this fixture -> expect graceful error,
    # proving compute path doesn't fabricate; register & retry instead
    if "error" in risk:
        handler._get_ontology_services()["registry"].gate.open()
        reg = handler._get_ontology_services()["registry"]
        reg.register_function(
            "ont", "risk_score", "risk",
            "tests.ont_handlers:risk_score",
        )
        risk = handler.call_tool("ont_compute_risk", {
            "function": "risk_score",
            "snapshot": proposed["target_snapshot"],
            "params": {"amount": 2_000_000},
        })
    assert risk["result"]["risk_level"] == "high"

    # direct commit tool does not exist
    assert handler.call_tool("commit_proposal", {"proposal_id": pid}) \
        .get("error")

    # validate then human review (internal commit)
    svc = handler._get_ontology_services()
    from ai_kb.ontology.proposal import ProposalService
    ProposalService.validate(svc["proposals"], pid)

    reviewed = handler.call_tool("ont_review_proposal", {
        "proposal_id": pid, "decision": "approve",
        "reviewer": "rex", "reviewer_kind": "human",
        "token": _mint("human", "rex", "review", "submit_contract"),
    })
    assert reviewed["status"] == "committed"

    # query object resolves after commit
    obj = handler.call_tool("ont_query_object", {
        "source_system": "oa", "source_key": "OA-100",
        "caller_attrs": {"role": "admin", "clearance": "internal"},
    })
    assert obj["found"] is True and obj["allowed"] is True
    handler.close()


# --- REST: real HTTP propose -> review ---

def test_rest_propose_review_over_http(http_server, ontology_env):
    base = http_server

    # POST propose
    r = requests.post(f"{base}/ontology/proposals", json={
        "instance_code": "ont",
        "action": "submit_contract",
        "object_refs": ["HT-100"],
        "params": {"contract_no": "HT-100", "target_state": "submitted"},
        "caller_id": "agent-http", "caller_kind": "agent",
        "idempotency_key": "http-1",
    })
    assert r.status_code == 200, r.text
    proposal = r.json()
    pid = proposal["id"]
    assert proposal["status"] == "pending"

    # GET query
    r = requests.get(
        f"{base}/ontology/proposals",
        params={"instance_code": "ont", "status": "pending"},
    )
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json()["proposals"])

    # Validate via internal services (validate is not a REST action endpoint;
    # review requires validated state). Drive validate through the same
    # service the REST layer uses.
    import api.server as rest
    proposals_svc = rest._ont_registry["ont"]
    v = proposals_svc.validate(pid)
    assert v["ok"] is True

    # POST review (human approve) -> internal commit
    r = requests.post(f"{base}/ontology/proposals/review", json={
        "instance_code": "ont", "proposal_id": pid,
        "decision": "approve", "reviewer": "rex",
        "reviewer_kind": "human",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "committed"

    # GET shows committed
    r = requests.get(
        f"{base}/ontology/proposals",
        params={"instance_code": "ont", "status": "committed"},
    )
    assert any(p["id"] == pid for p in r.json()["proposals"])

    # No direct write/commit endpoints: route inventory check
    paths = {route.path for route in rest.app.routes}
    assert "/ontology/proposals" in paths
    assert "/ontology/proposals/review" in paths
    assert not any("commit" in p or "execute" in p or "/write" in p
                   for p in paths if p.startswith("/ontology"))


def test_rest_reject_over_http(http_server):
    base = http_server
    import api.server as rest

    r = requests.post(f"{base}/ontology/proposals", json={
        "instance_code": "ont",
        "action": "submit_contract",
        "object_refs": ["HT-100"],
        "params": {"contract_no": "HT-100", "target_state": "submitted"},
        "caller_id": "agent-r", "caller_kind": "agent",
        "idempotency_key": "http-reject-1",
    })
    pid = r.json()["id"]
    rest._ont_registry["ont"].validate(pid)

    r = requests.post(f"{base}/ontology/proposals/review", json={
        "instance_code": "ont", "proposal_id": pid,
        "decision": "reject", "reviewer": "rex",
        "reviewer_kind": "human",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_rest_unknown_instance_404(http_server):
    r = requests.get(
        f"{http_server}/ontology/proposals",
        params={"instance_code": "ghost"},
    )
    assert r.status_code == 404


def test_rest_read_only_tools_intact(http_server):
    # Existing read-only surface unaffected
    r = requests.get(f"{http_server}/api/v1/mcp/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    assert "kb_query" in names
    assert not any(n.startswith(("execute_", "write_", "commit_"))
                   for n in names)
