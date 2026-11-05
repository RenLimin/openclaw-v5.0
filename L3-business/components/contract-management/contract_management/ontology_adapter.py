"""L2 运营本体 Function 化适配器 — L3 纯逻辑 → deterministic handler。

依据 DESIGN-DETAIL-contract-management-v1.0 §7（ADR-009 输出侧接地）：
- 将 L3 审批状态机/风险引擎暴露为 L2 OutputGuard 可绑定的函数；
- handler 契约：handler(snapshot: dict, params: dict) -> dict
    {"ok": bool, "violations": [str|{"rule","message"}], "data": <optional>}
- 规则单一来源：状态校验只在 L3 一处；法条引用来自受控规则库；
- 非法状态必须返回 violations（ok=False），绝不抛异常（fail-closed 由
  OutputGuard 兜底，但 handler 自身保持可测、不炸）。
"""
from typing import Any, Dict, List, Optional

from .models import Contract
from .state_machine import get_approval_config, next_approval_status
from .risk_engine import scan_text
from .contract_parser import parse_contract
from .contract_auditor import audit_contract


# 状态校验器：action → 合法前置状态集合（与 state_machine 流转图一致）
_PRECONDITION_STATES = {
    "submit": {"draft"},
    "approve": {"review1", "review2", "review3"},
    "reject": {"review1", "review2", "review3"},
    "sign": {"approved"},
    "archive": {"signed"},
}


def _identities(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 snapshot 提取目标身份列表（容忍缺失/非 dict）。"""
    return snapshot.get("identities", []) if isinstance(snapshot, dict) else []


def _metadata(ident: Dict[str, Any]) -> Dict[str, Any]:
    md = ident.get("metadata") if isinstance(ident, dict) else None
    return md if isinstance(md, dict) else {}


def _violation(rule: str, message: str) -> Dict[str, str]:
    return {"rule": rule, "message": message}


def _state_ok(state: str, action: str) -> bool:
    """状态是否允许执行该动作。"""
    return state in _PRECONDITION_STATES.get(action, set())


def _check_state_handlers(
    snapshot: Dict[str, Any], params: Dict[str, Any], action: str
) -> Dict[str, Any]:
    """通用状态前置校验：目标对象必须存在且状态合法。"""
    violations: List[Dict[str, str]] = []
    target_state = params.get("target_state")
    if target_state is not None and target_state not in (
        "draft", "review1", "review2", "review3", "approved", "signed",
        "archived", "rejected",
    ):
        violations.append(_violation(
            "invalid_target_state",
            f"cannot transition to {target_state!r}",
        ))
    idents = _identities(snapshot)
    if not idents:
        violations.append(_violation(
            "no_target_identity",
            "proposal targets no operational object (closed world)",
        ))
    for ident in idents:
        md = _metadata(ident)
        state = md.get("status", md.get("state"))
        if state is None:
            violations.append(_violation(
                "missing_status",
                f"object {ident.get('canonical_key')} has no status in metadata",
            ))
            continue
        if not _state_ok(str(state), action):
            violations.append(_violation(
                "illegal_transition",
                f"object {ident.get('canonical_key')} in state {state!r} "
                f"cannot execute {action}",
            ))
    return {"ok": not violations, "violations": violations}


def validate_submit_state(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """submit 前置：状态必须 draft。"""
    result = _check_state_handlers(snapshot, params, "submit")
    if result["ok"]:
        # 附审批层级信息（compute 语义，供决策参考）
        amount = float(_metadata(_identities(snapshot)[0]).get("amount", 0) or 0)
        cfg = get_approval_config(amount)
        result["data"] = {
            "approval_level": cfg.level,
            "first_approver": cfg.roles[0] if cfg.roles else None,
        }
    return result


def validate_approve_state(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """approve 前置：状态必须 reviewN。"""
    return _check_state_handlers(snapshot, params, "approve")


def validate_reject_state(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """reject 前置：状态必须 reviewN。"""
    return _check_state_handlers(snapshot, params, "reject")


def validate_sign_state(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """sign 前置：状态必须 approved。"""
    return _check_state_handlers(snapshot, params, "sign")


def validate_archive_state(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """archive 前置：状态必须 signed。"""
    return _check_state_handlers(snapshot, params, "archive")


def risk_scan(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """compute_ 风险扫描：只产出建议，不阻塞审批。

    法条依据全部来自受控规则库 CHECK_RULES（LLM 不自由生成）。
    """
    text = params.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {
            "ok": False,
            "violations": [_violation("empty_text", "text is required for risk scan")],
        }
    report = scan_text(text)
    data = report.to_dict()
    return {"ok": True, "violations": [], "data": data}


def parse_contract_text(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """compute_ 条款解析：只产出建议（28 类核心条款），不触发写。"""
    text = params.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {
            "ok": False,
            "violations": [_violation("empty_text", "text is required for parsing")],
        }
    parsed = parse_contract(text)
    data = {
        "title": parsed.title,
        "contract_no": parsed.contract_no,
        "party_a": parsed.party_a,
        "party_b": parsed.party_b,
        "clauses": [
            {
                "category": c.category,
                "law_article": c.law_article,
                "summary": c.summary,
                "key_terms": c.key_terms,
                "issues": c.issues,
                "suggestions": c.suggestions,
            }
            for c in parsed.clauses
        ],
    }
    return {"ok": True, "violations": [], "data": data}


def audit_contract_text(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """compute_ 逐条审核（43 项标准/17 类别）：只产出建议，不触发写。

    法条依据全部来自受控审核标准库 AUDIT_CRITERIA。
    """
    text = params.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return {
            "ok": False,
            "violations": [_violation("empty_text", "text is required for audit")],
        }
    parsed = parse_contract(text)
    report = audit_contract(text, parsed.clauses)
    data = {
        "overall_risk": report.overall_risk,
        "recommendation": report.recommendation,
        "summary": report.summary,
        "results": [r.to_dict() for r in report.results],
    }
    return {"ok": True, "violations": [], "data": data}


def approval_level(snapshot: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """compute_ 审批分级：金额 → 层级与角色序列。"""
    try:
        amount = float(params.get("amount", 0) or 0)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "violations": [_violation("invalid_amount", f"amount must be numeric, got {params.get('amount')!r}")],
        }
    cfg = get_approval_config(amount)
    return {
        "ok": True,
        "violations": [],
        "data": {"level": cfg.level, "roles": cfg.roles},
    }


# 注册表：装配脚本 / 测试按名取 handler
HANDLERS: Dict[str, Any] = {
    "validate_submit_state": validate_submit_state,
    "validate_approve_state": validate_approve_state,
    "validate_reject_state": validate_reject_state,
    "validate_sign_state": validate_sign_state,
    "validate_archive_state": validate_archive_state,
    "risk_scan": risk_scan,
    "approval_level": approval_level,
    "parse_contract_text": parse_contract_text,
    "audit_contract_text": audit_contract_text,
}
