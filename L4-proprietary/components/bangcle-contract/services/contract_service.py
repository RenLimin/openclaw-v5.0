"""services.contract_service — P2 持久化 + L3 状态机接线。

契约（DESIGN-DETAIL-contract-ontology-bridge-v1.0 §2.3）：
- create_contract_from_card：P1 映射 → contracts 落库（status 恒 draft）
  → audit_logs 追加 action='create' → 返回带 id 的 L3 Contract。
- apply_action：读合同 → L3 ApprovalStateMachine 裁决 → 合法则在
  **单一事务**内更新状态/落审批实例/追加审计；状态机抛 ValueError
  时整体 ROLLBACK（零落库）并重抛 ContractStateError。
- L4 只读库/落库/编排，状态规则全部由 L3 裁决，不重复实现。
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from ontology.mapper import map_card_to_contract
from repository.db import Repository


# ---------------------------------------------------------------
# L3 路径注入（与 ontology/mapper.py 同一方式）
# ---------------------------------------------------------------

def _l3_component_root() -> str:
    # services/contract_service.py -> services -> 组件根 -> ... -> 仓库根
    component_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(component_root)))
    return os.path.join(repo_root, "L3-business", "components", "contract-management")


def _load_l3():
    root = _l3_component_root()
    if not os.path.isdir(root):
        raise RuntimeError(f"L3 contract-management 组件不存在: {root}")
    if root not in sys.path:
        sys.path.insert(0, root)
    from contract_management.state_machine import ApprovalStateMachine
    from contract_management.models import Contract
    return ApprovalStateMachine, Contract


class ContractStateError(ValueError):
    """非法状态流转：apply_action 已整体回滚，数据库无任何新增行。"""


_ALLOWED_ACTIONS = ("submit", "approve", "reject", "sign", "archive")


def _row_to_contract(row: Dict[str, Any], Contract) -> Any:
    """contracts 表行 → L3 Contract（extra JSON 反序列化）。"""
    extra: Dict[str, Any] = {}
    if row.get("extra"):
        try:
            parsed = json.loads(row["extra"])
            if isinstance(parsed, dict):
                extra = parsed
        except (ValueError, TypeError):
            extra = {}
    return Contract(
        id=row["id"],
        contract_no=row.get("contract_no") or "",
        title=row.get("title") or "",
        contract_type=row.get("contract_type") or "tech_service",
        party_a=row.get("party_a") or "",
        party_b=row.get("party_b") or "",
        amount=float(row.get("amount") or 0.0),
        status=row["status"],
        current_approver=row.get("current_approver"),
        created_by=row.get("created_by") or "",
        effective_date=row.get("effective_date"),
        expiry_date=row.get("expiry_date"),
        extra=extra,
    )


def create_contract_from_card(
    card_main_fields: dict,
    *,
    db_path: Optional[str] = None,
) -> Any:
    """Cube 卡片主字段 → L3 Contract 映射 → 落库（draft）→ 审计 create。

    返回带 id 的 Contract。
    """
    _, Contract = _load_l3()
    contract = map_card_to_contract(card_main_fields)
    if not isinstance(contract, Contract):
        # mapper 在异常输入下也返回 Contract，此分支仅为类型保险
        contract = Contract()

    extra_json = json.dumps(contract.extra, ensure_ascii=False) if contract.extra else None
    with Repository(db_path) as repo:
        contract_id = repo.add_contract(
            contract_no=contract.contract_no,
            title=contract.title,
            contract_type=contract.contract_type,
            party_a=contract.party_a,
            party_b=contract.party_b,
            amount=float(contract.amount),
            status="draft",
            current_approver=contract.current_approver,
            effective_date=contract.effective_date,
            expiry_date=contract.expiry_date,
            extra=extra_json,
            created_by=contract.created_by or "",
        )
        # audit_logs.review_id 外键属 reviews 域，合同审计置 NULL，
        # contract_id 放入 detail JSON（既有表结构不动）。
        repo.append_audit_log(
            action="create",
            operator="system",
            review_id=None,
            detail=json.dumps(
                {
                    "contract_id": contract_id,
                    "contract_no": contract.contract_no,
                    "title": contract.title,
                },
                ensure_ascii=False,
            ),
        )

    contract.id = contract_id
    contract.status = "draft"
    return contract


def apply_action(
    contract_id: int,
    action: str,
    *,
    operator: str,
    approver_role: str = "",
    comment: str = "",
    db_path: Optional[str] = None,
) -> dict:
    """对本地合同推进一个生命周期动作（submit/approve/reject/sign/archive）。

    状态裁决全部交给 L3 ApprovalStateMachine；非法动作抛 ContractStateError，
    且整个事务回滚（contracts/approval_instances/audit_logs 均不落行）。
    """
    ApprovalStateMachine, Contract = _load_l3()

    with Repository(db_path) as repo:
        conn = repo._conn
        row = repo.get_contract_row(contract_id)
        if row is None:
            raise ContractStateError(f"合同不存在: id={contract_id}")

        contract = _row_to_contract(row, Contract)
        machine = ApprovalStateMachine(contract)

        if action not in _ALLOWED_ACTIONS:
            raise ContractStateError(f"未知操作: {action}")

        # 1) 先让状态机裁决（纯计算，可能抛 ValueError）
        try:
            if action == "submit":
                result = machine.submit(operator)
            elif action == "approve":
                result = machine.approve(operator, approver_role, comment)
            elif action == "reject":
                result = machine.reject(operator, approver_role, comment)
            elif action == "sign":
                result = machine.sign(operator)
            else:  # archive
                result = machine.archive(operator)
        except ValueError as exc:
            raise ContractStateError(str(exc)) from exc

        next_status = result["next_status"]
        next_role = result.get("next_approver_role")
        audit = result["audit_log"]
        from_status = audit.from_status
        to_status = audit.to_status
        now_iso = datetime.now().isoformat()

        # 2) 单一事务落库：任何一步异常 → ROLLBACK
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE contracts
                   SET status = ?, current_approver = ?, updated_at = ?
                 WHERE id = ?
                """,
                (next_status, next_role, now_iso, contract_id),
            )

            if action in ("approve", "reject"):
                record = result["approval_record"]
                conn.execute(
                    """
                    INSERT INTO approval_instances
                        (contract_id, level, status, action,
                         approver_role, approver_name, comment, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract_id,
                        record.approval_level,
                        next_status,
                        record.action,
                        record.approver_role,
                        record.approver_name,
                        record.comment,
                        record.created_at,
                    ),
                )

            detail_payload: Dict[str, Any] = {
                "contract_id": contract_id,
                "from_status": from_status,
                "to_status": to_status,
            }
            if audit.detail is not None:
                detail_payload["detail"] = audit.detail
            detail_json = json.dumps(detail_payload, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO audit_logs
                    (review_id, action, operator, detail, created_at)
                VALUES (NULL, ?, ?, ?, ?)
                """,
                (
                    audit.action,
                    audit.operator,
                    detail_json,
                    audit.created_at,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    out: Dict[str, Any] = {
        "contract_id": contract_id,
        "action": action,
        "next_status": next_status,
        "next_approver_role": next_role,
    }
    for key in ("step", "total_steps", "rejected_at_level"):
        if key in result:
            out[key] = result[key]
    return out


def list_contracts(
    status: Optional[str] = None,
    *,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """列出合同（可按状态过滤）。"""
    with Repository(db_path) as repo:
        return repo.list_contracts(status)


def get_contract(
    contract_id: int,
    *,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """取合同详情（含 approval_instances 与 audit_logs），无则 None。"""
    with Repository(db_path) as repo:
        return repo.get_contract_with_history(contract_id)
