"""N5 汇总与成文：从 OA 台账（权威原始文件）构建六类产物 + 自校验。"""
from __future__ import annotations
from ..ledger_source import load_customer_rows
from ..build_artifacts import build


def run(state: dict) -> dict:
    customer = state["input_norm"]["customer"]
    rows = load_customer_rows(customer)
    if not rows:
        state["errors"].append(f"no ledger rows for {customer}")
        state["_event"] = "fail"
        return state
    art, warns = build(rows, customer)

    # 评估器自校验：数字一致性
    for c in art.contractRegister:
        node_sum = round(sum(n.amount for n in c.payment.schedule), 2)
        # 终止协议净额为负时，节点金额非负 → 不强等；仅对非负合同校验
        if c.amount >= 0 and abs(node_sum - round(c.amount, 2)) > 0.01:
            state["audit"]["checks"].append(
                f"{c.contractNo}: payment nodes {node_sum} != amount {c.amount}")

    state["artifacts"] = art.model_dump()
    state["contracts"] = [c.model_dump() for c in art.contractRegister]
    state["audit"]["warnings"].extend(warns)
    state["audit"]["status"] = "PASS" if not state["audit"]["checks"] else "BLOCK"
    state["_event"] = "pass" if state["audit"]["status"] == "PASS" else "fail"
    return state
