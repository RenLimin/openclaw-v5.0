"""ContractWritebackConnector — 合同状态真写回 + 补偿（P2）。

依据 DESIGN-OUTLINE-contract-ontology-bridge-v1.0 §3/D2：
- commit 事务内把 status/审批字段写回 L4 contract 表（本地表，可逆）；
- compensate 写回 before 状态（本地表可逆 → Saga 可完整演示）；
- 接口按 L2 WritebackConnector 契约：apply(ctx) / compensate(ctx)；
- next_status 由 L3 ApprovalStateMachine 计算（状态机裁决单一来源，
  OutputGuard 校验与写回落地用同一台状态机，保证一致）。

写回目标解析（两路径兼容）：
- 单连接器路径（ProposalService.commit 直接调 apply）：构造注入 target；
- 多步 Saga 路径：ctx.payloads[step_name]（SagaOrchestrator apply 前写入）。

设计边界：
- connector 只写 L4 contract 表（status/审批实例/审计），不写 L2 表；
- 失败抛异常 → ProposalService 事务 ROLLBACK + 逆序补偿。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

# ---------------------------------------------------------------
# sys.path 注入：L4 组件根 + L2 ai-kb + L3 contract-management
# （顶层执行，保证 ai_kb.ontology / repository / L3 均可导入）
# ---------------------------------------------------------------

def _ensure_paths() -> None:
    here = os.path.dirname(os.path.abspath(__file__))          # .../ontology_bridge
    comp = os.path.dirname(os.path.dirname(here))              # .../bangcle-contract
    l4_components = os.path.dirname(comp)                      # .../components
    root = os.path.abspath(os.path.join(l4_components, "..", ".."))  # workspace root
    paths = [
        comp,
        os.path.join(root, "L2-infra", "components", "ai-knowledge-base"),
        os.path.join(root, "L3-business", "components", "contract-management"),
    ]
    for p in paths:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


_ensure_paths()

from ai_kb.ontology import (  # noqa: E402
    CompensationUnavailable,
    SagaContext,
    WritebackConnector,
)


def _now() -> str:
    return datetime.now().isoformat()


class ContractWritebackConnector(WritebackConnector):
    """把提案动作写回 L4 contract 表（status + 审批实例 + 审计）。

    apply(ctx)：
      - target = {contract_id, action, approver_role?, approver_name?,
        comment?, level?}
      - 读 L4 row → L3 ApprovalStateMachine 计算 next_status/next_role/level
        （submit/approve/reject；sign/archive 暂不在 Bridge 范围）
      - 更新 contracts.status / current_approver
      - approve/reject 落 approval_instances
      - 追加 audit_logs（action=ontology_<action>）
    compensate(ctx)：
      - 用构造参数 before={contract_id, status, current_approver} 写回原状态；
        无 before 抛 CompensationUnavailable（不可逆 → 人工对账）。
    """

    name = "contract_writeback"

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        target: Optional[Dict[str, Any]] = None,
        before: Optional[Dict[str, Any]] = None,
        step_name: str = "contract_writeback",
    ) -> None:
        from repository.db import default_db_path
        self.db_path = db_path or default_db_path()
        self.target = target or {}
        self.before = before or {}
        self.step_name = step_name

    # --- 参数解析 ---
    def _resolve_target(self, ctx: SagaContext) -> Dict[str, Any]:
        payload = ctx.payloads.get(self.step_name)
        if isinstance(payload, dict) and payload:
            return payload
        if self.target:
            return self.target
        raise ValueError(
            "ContractWritebackConnector: no target payload "
            "(multi-step saga needs payloads[%s]; single path needs target=)"
            % self.step_name
        )

    # --- L3 状态机计算（next_status 单一来源）---
    @staticmethod
    def _compute_next(
        row: Dict[str, Any],
        action: str,
        approver_role: str,
        comment: str,
    ) -> Dict[str, Any]:
        from contract_management.models import Contract
        from contract_management.state_machine import ApprovalStateMachine

        contract = Contract(
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
        )
        machine = ApprovalStateMachine(contract)
        if action == "submit":
            result = machine.submit("ontology")
        elif action == "approve":
            result = machine.approve(approver_role or "", approver_role, comment)
        elif action == "reject":
            result = machine.reject(approver_role or "", approver_role, comment)
        else:
            raise ValueError(f"unsupported writeback action: {action}")
        return result

    # --- 写回 ---
    def apply(self, ctx: SagaContext) -> None:
        target = self._resolve_target(ctx)
        from repository.db import Repository

        contract_id = int(target.get("contract_id") or 0)
        if contract_id <= 0:
            raise ValueError("ContractWritebackConnector.apply: missing contract_id")
        action = target.get("action") or ""
        approver_role = target.get("approver_role") or ""
        approver_name = target.get("approver_name") or ""
        comment = target.get("comment") or ""

        with Repository(self.db_path) as repo:
            row = repo.get_contract_row(contract_id)
            if row is None:
                raise ValueError(
                    f"ContractWritebackConnector.apply: contract not found: {contract_id}"
                )
            result = self._compute_next(row, action, approver_role, comment)
            next_status = result["next_status"]
            next_role = result["next_approver_role"]
            from_status = row["status"]

            repo.update_contract_status(
                contract_id, next_status, current_approver=next_role,
            )
            if action in ("approve", "reject"):
                record = result.get("approval_record")
                repo.add_approval_instance(
                    contract_id, action, level=record.approval_level if record else None,
                    status=next_status, approver_role=approver_role,
                    approver_name=approver_name, comment=comment,
                )
            repo.append_audit_log(
                action=f"ontology_{action}", operator=approver_name or "ontology",
                review_id=None,
                detail=json.dumps({
                    "contract_id": contract_id,
                    "from_status": from_status,
                    "to_status": next_status,
                    "connector": self.name,
                }, ensure_ascii=False),
            )
        ctx.mark_success(self.name, {
            "contract_id": contract_id,
            "from_status": from_status,
            "to_status": next_status,
            "written_back": True,
        })

    # --- 补偿 ---
    def compensate(self, ctx: SagaContext) -> None:
        if not self.before:
            raise CompensationUnavailable(
                "ContractWritebackConnector has no 'before' snapshot; "
                "compensation unavailable, manual reconciliation required"
            )
        from repository.db import Repository

        contract_id = int(self.before.get("contract_id") or 0)
        before_status = self.before.get("status") or "draft"
        if contract_id <= 0:
            raise CompensationUnavailable(
                "ContractWritebackConnector.before missing contract_id"
            )
        with Repository(self.db_path) as repo:
            row = repo.get_contract_row(contract_id)
            if row is None:
                raise CompensationUnavailable(
                    f"contract not found for compensation: {contract_id}"
                )
            repo.update_contract_status(
                contract_id, before_status,
                current_approver=self.before.get("current_approver"),
            )
            repo.append_audit_log(
                action="ontology_compensate", operator="saga",
                review_id=None,
                detail=json.dumps({
                    "contract_id": contract_id,
                    "restored_status": before_status,
                    "connector": self.name,
                }, ensure_ascii=False),
            )
        ctx.mark_success(f"{self.name}.compensate", {
            "contract_id": contract_id,
            "restored_status": before_status,
            "compensated": True,
        })


class NotifyConnector(WritebackConnector):
    """演示用第二写回目标：审批通过后"通知"（本地审计留痕，无外部副作用）。

    用于 Saga 多步写回黄金基准：contract 写回 → 通知。注入失败即演示
    补偿路径（contract 写回被逆序回滚）。
    """

    name = "notify"

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        fail_next: bool = False,
        step_name: str = "notify",
    ) -> None:
        from repository.db import default_db_path
        self.db_path = db_path or default_db_path()
        self.fail_next = fail_next
        self.step_name = step_name

    def apply(self, ctx: SagaContext) -> None:
        if self.fail_next:
            raise RuntimeError("NotifyConnector simulated failure (saga demo)")
        payload = ctx.payloads.get(self.step_name) or {}
        contract_id = int(payload.get("contract_id") or 0)
        to_status = payload.get("next_status") or ""
        from repository.db import Repository
        with Repository(self.db_path) as repo:
            repo.append_audit_log(
                action="ontology_notify", operator="saga",
                review_id=None,
                detail=json.dumps({
                    "contract_id": contract_id,
                    "event": "approved",
                    "to_status": to_status,
                    "connector": self.name,
                }, ensure_ascii=False),
            )
        ctx.mark_success(self.name, {"notified": True, "contract_id": contract_id})

    def compensate(self, ctx: SagaContext) -> None:
        # 通知无真实外部副作用：补偿为空操作（幂等）
        ctx.mark_success(f"{self.name}.compensate", {"compensated": True})
