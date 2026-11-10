"""N1 入口护栏：参数校验 + 标准化。"""
from __future__ import annotations
import re
from datetime import date

KNOWN_CUSTOMERS = {
    "中国建设银行股份有限公司": "中国建设银行股份有限公司",
    "山东省城市商业银行合作联盟有限公司": "山东省城市商业银行合作联盟有限公司",
}


class GuardError(ValueError):
    pass


def validate(raw_input: dict) -> dict:
    customer = (raw_input.get("customer") or "").strip()
    if not customer:
        raise GuardError("INVALID_CUSTOMER: customer is empty")
    period = raw_input.get("period") or {}
    try:
        start = date.fromisoformat(period["start"])
        end = date.fromisoformat(period["end"])
    except Exception as exc:
        raise GuardError(f"INVALID_PERIOD: {exc}")
    if start > end:
        raise GuardError("INVALID_PERIOD: start > end")
    audience = raw_input.get("audience")
    if audience not in ("internal", "external"):
        raise GuardError(f"INVALID_AUDIENCE: {audience!r}")

    scope = raw_input.get("scope") or {}
    allowed = {"includeH5Maint", "extraContractNos", "onlyProjects"}
    unknown = set(scope) - allowed
    if unknown:
        raise GuardError(f"INVALID_SCOPE: unknown fields {sorted(unknown)}")

    norm_name = KNOWN_CUSTOMERS.get(customer)
    known = norm_name is not None
    return {
        "customer": norm_name or customer,
        "customerKnown": known,
        "period": {"start": str(start), "end": str(end)},
        "audience": audience,
        "scope": scope,
        "teamUUID": raw_input.get("teamUUID", "RZxvwUZ8"),
    }


def run(state: dict) -> dict:
    inp = state["input_norm"]
    # input_norm 在 start 前已 validate；这里标准化并记录
    if not inp.get("customerKnown", True):
        state["audit"]["warnings"].append(f"unknown customer: {inp['customer']}")
    state["_event"] = "pass"
    return state
