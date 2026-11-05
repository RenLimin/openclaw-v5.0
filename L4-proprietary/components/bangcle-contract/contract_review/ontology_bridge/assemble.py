"""assemble — L4 bangcle-contract → L2 运营本体装配（幂等，单一来源）。

装配逻辑集中在本模块（脚本 scripts/register_contract_ontology.py 与
测试均调用它），避免 L4/L3 两个 `scripts/` 包的同名解析冲突。

职责（DESIGN-OUTLINE-contract-ontology-bridge-v1.0 §6 P1）：
- 初始化 L4 contract 库（contracts/approval_instances/audit_logs）；
- 初始化 L2 ai_kb 库（domain + ontology 全套表）；
- 复用 L3 register_ontology_functions.register_all（importlib 绝对路径加载）：
  注册 domain bangcle-contract、9 个 deterministic function、3 个 action type
  （submit=auto / approve=human / reject=human）；
- 装配闭合校验（validate_action_bindings）；
- 可选 --register 登记示例合同为运营对象。
"""
from __future__ import annotations

import os
from typing import Optional

from ._assembly import l3_register_all
from .registry import ContractRegistry


def default_ai_kb_path(db_path: str) -> str:
    """L2 ai_kb 库默认与 contract db 同目录（ai_kb.db）。"""
    return os.path.join(os.path.dirname(db_path), "ai_kb.db")


def assemble(
    db_path: Optional[str] = None,
    ai_kb_path: Optional[str] = None,
    register: Optional[str] = None,
) -> dict:
    """执行装配；返回汇总 dict（幂等：已存在项跳过）。"""
    from repository.db import default_db_path, init_db

    db = db_path or default_db_path()
    init_db(db)  # L4 contract 库（幂等）

    ai_kb = ai_kb_path or default_ai_kb_path(db)
    # L2 ai_kb 库：L3 装配（domain + functions + actions，gate 装配期开/关）
    summary = l3_register_all(ai_kb)

    out = {
        "db_path": db,
        "ai_kb_path": ai_kb,
        "domain_id": summary["domain_id"],
        "functions": summary["functions"],
        "actions": summary["actions"],
        "bindings": summary["bindings"],
        "registered_contracts": [],
    }

    # 可选：登记示例合同（P1 演示 + CLI 黄金基准前置）
    if register:
        reg = ContractRegistry(db, ai_kb)
        for item in register.split(","):
            item = item.strip()
            if not item:
                continue
            no, _, amount = item.rpartition(":")
            try:
                amt = float(amount or 0)
            except ValueError:
                raise SystemExit(f"invalid register spec (expected NO:AMOUNT): {item}")
            result = reg.register(no, title=f"示例合同 {no}", amount=amt)
            out["registered_contracts"].append(result)

    return out
