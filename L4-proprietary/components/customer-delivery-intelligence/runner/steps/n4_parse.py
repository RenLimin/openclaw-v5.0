"""N4 解析与抽取：Phase 2 直接消费 OA 台账（原始文件），本节点透传。

真实合同全文条款的深度抽取走既有 contract-manager / bangcle-contract，
当前 v1 以 OA 台账验收条件原文为条款事实源，无需重复 OCR。
"""
from __future__ import annotations


def run(state: dict) -> dict:
    state["_event"] = "pass"
    return state
