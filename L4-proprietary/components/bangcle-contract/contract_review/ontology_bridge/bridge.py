"""ContractOntologyBridge — 合同运营对象 Proposal Gate 编排（P2）。

依据 DESIGN-OUTLINE-contract-ontology-bridge-v1.0 §3/§7：
- submit/approve/reject 走 L2 ProposalService 全流程：
  propose_action → validate（OutputGuard 内调 L3 deterministic handler）
  → review（submit=auto 审 / approve·reject=human 审）→ commit（真写回）
- 关键闭环：每次 commit 成功后把 L4 最新 status 同步回 L2
  ont_identity.metadata.status（ProposalService 只追加 applied_changes，
  不更新 status 字段；不同步则下次 propose 的 snapshot 仍是旧状态，
  L3 handler 会误判非法转移）。
- 语义约定：
  - validate 失败（非法转移/状态不符）→ 返回 ok=False + violations，
    不抛异常（提案保持 pending 留痕，供学习）；
  - review 越权（agent 审 human 级动作）→ 抛 PermissionError（硬拒绝）；
  - commit 失败（Saga 演示注入）→ 抛 SagaExecutionError（测试断言用）；
  - 同 idempotency_key 重复 submit → 返回既有提案（幂等重放）。
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from .connector import ContractWritebackConnector
from .registry import DOMAIN_CODE, ContractRegistry, canonical_contract_no

# ---------------------------------------------------------------
# sys.path 注入（与 connector 同模式）
# ---------------------------------------------------------------

def _ensure_paths() -> None:
    here = os.path.dirname(os.path.abspath(__file__))          # .../ontology_bridge
    comp = os.path.dirname(os.path.dirname(here))              # .../bangcle-contract
    l4_components = os.path.dirname(comp)
    root = os.path.abspath(os.path.join(l4_components, "..", ".."))
    paths = [
        comp,
        os.path.join(root, "L2-infra", "components", "ai-knowledge-base"),
        os.path.join(root, "L3-business", "components", "contract-management"),
    ]
    for p in paths:
        if os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


_ensure_paths()

# 动作 → (action_type, required_approval, 期望 target_state)
_ACTIONS = {
    "submit": ("submit_contract", "auto", "review1"),
    "approve": ("approve_contract", "human", "approved"),
    "reject": ("reject_contract", "human", "draft"),
    "submit_to_oa": ("submit_to_oa", "human", "review"),
}


class ContractOntologyBridge:
    """合同运营桥：登记 → 提案 → 校验 → 审批 → 写回 的完整编排。"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        ai_kb_path: Optional[str] = None,
    ) -> None:
        self.registry = ContractRegistry(db_path, ai_kb_path)
        self.db_path = self.registry.db_path
        self.ai_kb_path = self.registry.ai_kb_path

    # ---------------------------------------------------------------
    # 内部装配（幂等）
    # ---------------------------------------------------------------
    def _open_l2(self):
        """打开 AIKB + 确保 domain/actions/functions 已装配（运行期 gate 关闭）。"""
        from ai_kb.db import AIKB
        from ai_kb.ontology import ActionRegistry, AssemblyGate, ProposalService

        ai = AIKB(self.ai_kb_path)
        ai.init_db()
        ai.init_ontology_tables()
        # L3 装配脚本（幂等：已注册项跳过；gate 装配期开、结束关）
        from ._assembly import l3_register_all
        l3_register_all(self.ai_kb_path)
        # 运行期 gate 关闭 → 任何 register_* 被拒（结构/数据通道分离）
        gate = AssemblyGate(open_by_default=False)
        reg = ActionRegistry(ai, gate=gate)
        return ai, reg, ProposalService

    def _contract_row(self, contract_id: int) -> Dict[str, Any]:
        from repository.db import Repository
        with Repository(self.db_path) as repo:
            row = repo.get_contract_row(contract_id)
        if row is None:
            raise ValueError(f"contract not found: {contract_id}")
        return row

    def _new_service(self, target: Dict[str, Any], before: Dict[str, Any]):
        """构造带真写回连接器的 ProposalService（单连接器路径）。"""
        ai, reg, ProposalService = self._open_l2()
        connector = ContractWritebackConnector(
            self.db_path, target=target, before=before,
        )
        svc = ProposalService(ai, reg, default_connector=connector)
        return ai, svc

    def _new_service_oa(self, target: Dict[str, Any],
                        identity: Optional[Any] = None):
        """构造带 OA 写回连接器的 ProposalService（P5.2）。

        注入 connectors={'oa_writeback': OaWritebackConnector(dry_run=True)}：
        submit_to_oa 动作经 ont_writeback_step 指向该 connector_key；
        运行期 gate 关闭，连接器由装配方注入。dry_run 冻结语义不变
        （P4.2 未闭合前绝不真实外发）。

        identity（P6.2 可选）：传入 IdentityAuthority 即启用 run-scoped
        身份治理（enforce fail-closed）；不传则保持 P5 兼容路径。
        """
        ai, reg, ProposalService = self._open_l2()
        from .oa_connector import OaWritebackConnector
        svc = ProposalService(
            ai, reg,
            connectors={
                "oa_writeback": OaWritebackConnector(
                    dry_run=True, target=target,
                ),
            },
            identity=identity,
        )
        return ai, svc

    # ---------------------------------------------------------------
    # 动作编排
    # ---------------------------------------------------------------
    def _run(
        self,
        contract_id: int,
        action: str,
        *,
        operator: str,
        caller_kind: str,
        approver_role: str = "",
        comment: str = "",
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        reviewer_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        if action not in _ACTIONS:
            raise ValueError(f"unsupported ontology action: {action}")
        action_type, required_approval, target_state = _ACTIONS[action]

        row = self._contract_row(contract_id)
        contract_no = row.get("contract_no") or ""
        canonical = canonical_contract_no(contract_no)
        if not canonical:
            raise ValueError(f"contract {contract_id} has no contract_no")

        # CWA 前置：必须已登记为运营对象
        if not self.registry.is_registered(contract_no):
            raise ValueError(
                f"contract not registered as operational object: {contract_no} "
                f"(run 'contractctl ontology register' first)"
            )

        # connector 目标 + 补偿快照（L4 表当前状态）
        target = {
            "contract_id": contract_id,
            "action": action,
            "approver_role": approver_role,
            "approver_name": operator,
            "comment": comment,
        }
        before = {
            "contract_id": contract_id,
            "status": row["status"],
            "current_approver": row["current_approver"],
        }

        ai, svc = self._new_service(target, before)
        try:
            # 1) propose（只建 pending + 快照，零业务写）
            proposal = svc.propose_action(
                DOMAIN_CODE, action_type, [canonical],
                {
                    "contract_no": contract_no,
                    "target_state": target_state,
                    "amount": float(row.get("amount") or 0.0),
                },
                caller_id=operator,
                caller_kind=caller_kind,
                rationale=rationale,
                idempotency_key=idempotency_key,
            )
            proposal_id = proposal["id"]
            if proposal.get("idempotent_replay"):
                return self._out(
                    ok=True, proposal_id=proposal_id,
                    proposal_status=proposal["status"],
                    contract_id=contract_id, action=action,
                    idempotent_replay=True,
                )

            # 2) validate（OutputGuard 内 L3 handler；无副作用）
            vr = svc.validate(proposal_id, {
                "user_id": operator,
                "role": approver_role or operator,
                "clearance": "internal",
            })
            if not vr["ok"]:
                return self._out(
                    ok=False, proposal_id=proposal_id,
                    proposal_status=vr["status"], contract_id=contract_id,
                    action=action, violations=vr["violations"],
                )

            # 3) review + commit（审批者身份 = 调用者身份；
            #    human 级动作 agent 审 → L2 抛 PermissionError）
            reviewer_kind = reviewer_kind or caller_kind
            result = svc.review(
                proposal_id, "approve", operator,
                reviewer_kind=reviewer_kind, auto_commit=True,
            )

            # 4) 状态对齐：L4 最新 status → L2 metadata.status
            latest = self._contract_row(contract_id)
            self.registry.sync_metadata(contract_id, status=latest["status"])

            return self._out(
                ok=True, proposal_id=proposal_id,
                proposal_status=result["status"],
                contract_id=contract_id, action=action,
                contract_status=latest["status"],
                decision_record=result.get("decision_record"),
            )
        finally:
            ai.close()

    def _run_oa(
        self,
        contract_id: int,
        *,
        operator: str,
        requestid: str,
        action: str = "提交",
        comment: str = "",
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """submit_to_oa：把合同状态动作提交到 OA 审批流（P5.2）。

        流程：propose（params=OA payload）→ validate（无 L3 handler
        precondition，仅 OutputGuard）→ review(approve, human) → commit
        （Saga 多步：oa_writeback 连接器，dry-run 审计）。

        caller_kind 强制 human：OA 外部写为 human 级动作，agent 不可审。
        commit 后不强制本地状态机转移——OA 态以对账为准（P4.4），
        registry.sync_metadata 仅记录审计元数据。
        """
        action_type = "submit_to_oa"
        row = self._contract_row(contract_id)
        contract_no = row.get("contract_no") or ""
        canonical = canonical_contract_no(contract_no)
        if not canonical:
            raise ValueError(f"contract {contract_id} has no contract_no")
        if not self.registry.is_registered(contract_no):
            raise ValueError(
                f"contract not registered as operational object: {contract_no} "
                f"(run 'contractctl ontology register' first)"
            )
        if not requestid or not str(requestid).strip():
            raise ValueError("requestid must not be empty (OA workflow id)")

        # OA 写回 target（连接器构造注入；多步 Saga 不传 payload）
        target = {
            "requestid": str(requestid).strip(),
            "action": action,
            "comment": comment,
        }

        ai, svc = self._new_service_oa(target)
        try:
            # 1) propose（只建 pending + 快照，零业务写）
            proposal = svc.propose_action(
                DOMAIN_CODE, action_type, [canonical],
                {
                    "requestid": str(requestid).strip(),
                    "action": action,
                    "comment": comment,
                },
                caller_id=operator,
                caller_kind="human",
                rationale=rationale,
                idempotency_key=idempotency_key,
            )
            proposal_id = proposal["id"]
            if proposal.get("idempotent_replay"):
                return self._out(
                    ok=True, proposal_id=proposal_id,
                    proposal_status=proposal["status"],
                    contract_id=contract_id, action="submit_to_oa",
                    idempotent_replay=True,
                )

            # 2) validate（OutputGuard；无 precondition，仅 schema/权限）
            vr = svc.validate(proposal_id, {
                "user_id": operator,
                "role": operator,
                "clearance": "internal",
            })
            if not vr["ok"]:
                return self._out(
                    ok=False, proposal_id=proposal_id,
                    proposal_status=vr["status"], contract_id=contract_id,
                    action="submit_to_oa", violations=vr["violations"],
                )

            # 3) review + commit（human 级动作，agent 审 → L2 抛 PermissionError）
            result = svc.review(
                proposal_id, "approve", operator,
                reviewer_kind="human", auto_commit=True,
            )

            # 4) 审计元数据（不强制本地状态机转移；OA 态以对账为准）
            self.registry.sync_metadata(
                contract_id, status=row["status"],
                fields={"oa_submitted_at": ai.get_now()},
            )

            return self._out(
                ok=True, proposal_id=proposal_id,
                proposal_status=result["status"],
                contract_id=contract_id, action="submit_to_oa",
                contract_status=row["status"],
                decision_record=result.get("decision_record"),
            )
        finally:
            ai.close()

    def submit_to_oa(
        self,
        contract_id: int,
        operator: str,
        *,
        requestid: str,
        action: str = "提交",
        comment: str = "",
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交到 OA 审批流（human 级动作；P4.2 未闭合前连接器恒 dry-run）。"""
        return self._run_oa(
            contract_id, operator=operator, requestid=requestid,
            action=action, comment=comment, rationale=rationale,
            idempotency_key=idempotency_key,
        )

    def submit_to_oa_agent(
        self,
        contract_id: int,
        *,
        run_id: str,
        agent: str,
        requestid: str,
        action: str = "提交",
        comment: str = "",
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        reviewer_operator: Optional[str] = None,
        authority: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """P6.2 首实例：agent 经 OntologyToolchain 消费 submit_to_oa。

        流程：agent run 令牌 → propose → validate → 停在 **validated**
        （agent 永不 commit）；若给 reviewer_operator，则现场签发 human
        operator 令牌 review→commit（dry-run 连接器），决策链含两条
        令牌指纹，oa_submitted_at 落库。

        红线不变：commit 只由 human 令牌触发；连接器恒 dry-run（P4.2）。
        authority 不传时用默认 secret 路径（生产）；测试注入固定 secret。
        """
        action_type = "submit_to_oa"
        row = self._contract_row(contract_id)
        contract_no = row.get("contract_no") or ""
        canonical = canonical_contract_no(contract_no)
        if not canonical:
            raise ValueError(f"contract {contract_id} has no contract_no")
        if not self.registry.is_registered(contract_no):
            raise ValueError(
                f"contract not registered as operational object: {contract_no} "
                f"(run 'contractctl ontology register' first)"
            )
        if not requestid or not str(requestid).strip():
            raise ValueError("requestid must not be empty (OA workflow id)")

        from ai_kb.ontology.agent_toolchain import OntologyToolchain
        from ai_kb.ontology.identity_token import IdentityAuthority, operator_token

        authority = authority or IdentityAuthority()
        target = {
            "requestid": str(requestid).strip(),
            "action": action,
            "comment": comment,
        }

        ai, svc = self._new_service_oa(target, identity=authority)
        try:
            chain = OntologyToolchain(svc, svc.registry, authority)
            reviewer_token = None
            if reviewer_operator:
                reviewer_token = operator_token(
                    authority, reviewer_operator,
                    run_id=run_id, domain_code=DOMAIN_CODE,
                )
            result = chain.run_action(
                run_id=run_id,
                domain=DOMAIN_CODE,
                action=action_type,
                object_refs=[canonical],
                params={
                    "requestid": str(requestid).strip(),
                    "action": action,
                    "comment": comment,
                },
                scopes=[f"propose:submit_to_oa:{DOMAIN_CODE}"],
                subject=f"agent:{agent}",
                kind="agent",
                rationale=rationale,
                idempotency_key=idempotency_key,
                reviewer_token=reviewer_token,
            )
            out = self._out(
                ok=True,
                proposal_id=result["proposal_id"],
                proposal_status=result["status"],
                contract_id=contract_id,
                action=action_type,
                decision_record=result.get("decision_record"),
                idempotent_replay=result.get("idempotent_replay", False),
            )
            out["run_token_fingerprint"] = result["run_token_fingerprint"]
            if result.get("reviewer_token_fingerprint"):
                out["reviewer_token_fingerprint"] = (
                    result["reviewer_token_fingerprint"]
                )
            # commit 后审计元数据（同 _run_oa 语义；OA 态以对账为准）
            if result["status"] == "committed":
                self.registry.sync_metadata(
                    contract_id, status=row["status"],
                    fields={"oa_submitted_at": ai.get_now()},
                )
            return out
        finally:
            ai.close()

    def submit(
        self,
        contract_id: int,
        operator: str,
        *,
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """提交审批：draft → review1（auto 审，无人工介入）。"""
        return self._run(
            contract_id, "submit", operator=operator,
            caller_kind="human", rationale=rationale,
            idempotency_key=idempotency_key,
        )

    def approve(
        self,
        contract_id: int,
        reviewer: str,
        approver_role: str = "",
        comment: str = "",
        *,
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """审批通过：reviewN → review(N+1)/approved（human 审）。"""
        return self._run(
            contract_id, "approve", operator=reviewer,
            caller_kind="human", approver_role=approver_role,
            comment=comment, rationale=rationale,
            idempotency_key=idempotency_key,
        )

    def reject(
        self,
        contract_id: int,
        reviewer: str,
        approver_role: str = "",
        comment: str = "",
        *,
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """驳回：reviewN → draft（human 审）。"""
        return self._run(
            contract_id, "reject", operator=reviewer,
            caller_kind="human", approver_role=approver_role,
            comment=comment, rationale=rationale,
            idempotency_key=idempotency_key,
        )

    # ---------------------------------------------------------------
    # 查询
    # ---------------------------------------------------------------
    def status(self, contract_id: int) -> Dict[str, Any]:
        """合同双视角状态：L4 行 + L2 identity + 最近决策链。"""
        row = self._contract_row(contract_id)
        contract_no = row.get("contract_no") or ""
        ident = self.registry.get_identity(contract_no)
        chain = self.decision_chain(contract_no)
        return {
            "contract_id": contract_id,
            "contract_no": contract_no,
            "contract_status": row["status"],
            "current_approver": row["current_approver"],
            "canonical_key": canonical_contract_no(contract_no),
            "registered": ident is not None,
            "identity_id": ident["id"] if ident else None,
            "metadata_status": (ident.get("metadata") or {}).get("status")
            if ident else None,
            "decision_chain": chain,
        }

    def proposals(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """列出 domain 提案（可按五态过滤）。"""
        ai, reg, ProposalService = self._open_l2()
        try:
            svc = ProposalService(ai, reg)
            return svc.list_proposals(DOMAIN_CODE, status=status, limit=limit)
        finally:
            ai.close()

    def decision_chain(self, contract_no: str) -> List[Dict[str, Any]]:
        """按合同编号回放决策链（DecisionService.replay）。"""
        ai, reg, ProposalService = self._open_l2()
        try:
            from ai_kb.ontology import DecisionService
            decisions = DecisionService(ai)
            canonical = canonical_contract_no(contract_no)
            return decisions.replay(DOMAIN_CODE, "contract", canonical)
        finally:
            ai.close()

    # ---------------------------------------------------------------
    # 输出归一
    # ---------------------------------------------------------------
    @staticmethod
    def _out(
        *,
        ok: bool,
        proposal_id: Optional[int] = None,
        proposal_status: Optional[str] = None,
        contract_id: Optional[int] = None,
        action: Optional[str] = None,
        contract_status: Optional[str] = None,
        violations: Optional[List[Any]] = None,
        decision_record: Optional[Dict[str, Any]] = None,
        idempotent_replay: bool = False,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "ok": ok,
            "proposal_id": proposal_id,
            "proposal_status": proposal_status,
            "contract_id": contract_id,
            "action": action,
        }
        if contract_status is not None:
            out["contract_status"] = contract_status
        if violations:
            out["violations"] = violations
        if decision_record:
            out["decision_record"] = decision_record
        if idempotent_replay:
            out["idempotent_replay"] = True
        return out
