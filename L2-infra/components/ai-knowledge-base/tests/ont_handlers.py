"""Deterministic handler fixtures for ontology proposal tests.

Referenced by handler_ref as 'tests.ont_handlers:<name>'. All handlers are
pure functions (deterministic=1), zero side effects, returning only
validation results per the OutputGuard contract:
    handler(snapshot: dict, params: dict) -> bool | dict | list
"""
try:
    from ai_kb.ontology.connectors.base import CompensationUnavailable
except ImportError:  # pragma: no cover - standalone
    class CompensationUnavailable(Exception):
        pass

"""Deterministic handler fixtures for ontology proposal tests.

Referenced by handler_ref as 'tests.ont_handlers:<name>'. All handlers are
pure functions (deterministic=1), zero side effects, returning only
validation results per the OutputGuard contract:
    handler(snapshot: dict, params: dict) -> bool | dict | list
"""
from typing import Any, Dict, List


def validate_submit_state(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """Rule precondition: contract must have a non-empty contract_no and
    not already be in 'submitted' state."""
    violations: List[Dict[str, str]] = []
    if not params.get("contract_no"):
        violations.append({
            "rule": "contract_no_required",
            "message": "contract_no is required",
        })
    for ident in snapshot.get("identities", []):
        metadata = ident.get("metadata") or {}
        if metadata.get("state") == "submitted":
            violations.append({
                "rule": "already_submitted",
                "message": f"contract {ident.get('canonical_key')} already submitted",
            })
    return {"ok": not violations, "violations": violations}


def contract_state_machine(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """State machine constraint: only draft -> submitted transitions allowed."""
    violations: List[Dict[str, str]] = []
    target_state = params.get("target_state")
    if target_state != "submitted":
        violations.append({
            "rule": "invalid_target_state",
            "message": f"cannot transition to {target_state!r}",
        })
    for ident in snapshot.get("identities", []):
        state = (ident.get("metadata") or {}).get("state")
        if state != "draft":
            violations.append({
                "rule": "illegal_transition",
                "message": f"contract in state {state!r} cannot be submitted",
            })
    return {"ok": not violations, "violations": violations}


def risk_score(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """compute_ risk function: advice only."""
    amount = float(params.get("amount", 0))
    level = "high" if amount > 1_000_000 else "low"
    return {"risk_level": level, "amount": amount}


def raise_handler(snapshot: Dict[str, Any], params: Dict[str, Any]) -> bool:
    """Handler that raises (fail-closed violation path)."""
    raise RuntimeError("boom from handler")


def false_handler(snapshot: Dict[str, Any], params: Dict[str, Any]) -> bool:
    """Handler returning False (simple bool violation path)."""
    return False


# --- P4: saga test connectors (memory, no side effects) ---
class MemoryConnector:
    """内存写回连接器（测试用）：apply 可配置失败/成功，compensate 可配置不可补偿。

    not_compensable=True 时 compensate 抛 CompensationUnavailable。
    """

    def __init__(self, name, fail_on_apply=False, not_compensable=False):
        self.name = name
        self.fail_on_apply = fail_on_apply
        self.not_compensable = not_compensable
        self.applied = 0
        self.compensated = 0

    def apply(self, ctx):
        self.applied += 1
        if self.fail_on_apply:
            raise RuntimeError(f"{self.name} apply failed")
        ctx.mark_success(self.name, {"written_back": True})

    def compensate(self, ctx):
        if self.not_compensable:
            raise CompensationUnavailable(f"{self.name} cannot compensate")
        self.compensated += 1
        ctx.mark_success(f"{self.name}.compensate", {"compensated": True})
