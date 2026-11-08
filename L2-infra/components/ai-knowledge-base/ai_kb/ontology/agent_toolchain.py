"""P6.2 OntologyToolchain — 高层 agent 的运营本体消费助手。

设计契约：DESIGN-DETAIL-operational-ontology-p6-v1.0 §3.5。

把"发现工具 → 签发 run 令牌 → propose → validate →（human 令牌）
review+commit"封装为一条可复用链路，供进程内 agent 直调（MCP 工具
并存供外部 agent，两者共用同一 ProposalService，身份校验逻辑唯一）。

红线：
- auto_review=False（默认）时 agent 只到 **validated**；
- **commit 永远由 human reviewer/operator 令牌触发**，agent 令牌无法
  自行提交；本模块不提供任何绕过 Gate 的写路径。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .actions import ActionRegistry
from .identity_token import IdentityAuthority, IdentityError
from .proposal import ProposalService


class OntologyToolchain:
    """进程内运营本体消费助手。"""

    def __init__(
        self,
        proposals: ProposalService,
        registry: ActionRegistry,
        authority: IdentityAuthority,
    ) -> None:
        self.proposals = proposals
        self.registry = registry
        self.authority = authority

    # ------------------------------------------------------------
    # 工具发现
    # ------------------------------------------------------------
    def discover(self, domain: Union[int, str]) -> List[Dict[str, Any]]:
        """列可用 ont_propose_* / ont_compute_* 工具（仅 active）。

        与 MCP 动态枚举同口径：同名多版本只取 status=active；
        绝不出现 execute_*/write_*/commit_*。
        """
        tools: List[Dict[str, Any]] = []

        for action in self.registry.list_actions(domain):
            if action.get("status") != "active":
                continue
            tools.append({
                "tool": f"ont_propose_{action['name']}",
                "category": "propose_",
                "action": action["name"],
                "version": action.get("version"),
                "object_type": action.get("object_type"),
                "required_approval": action.get("required_approval"),
                "writeback_target": action.get("writeback_target"),
            })

        for fn in self.registry.list_functions(domain):
            tools.append({
                "tool": f"ont_compute_{fn['name']}",
                "category": "compute_",
                "function": fn["name"],
                "version": fn.get("version"),
                "kind": fn.get("kind"),
            })

        return tools

    # ------------------------------------------------------------
    # 端到端动作链路
    # ------------------------------------------------------------
    def run_action(
        self,
        *,
        run_id: str,
        domain: str,
        action: str,
        object_refs: List[str],
        params: Dict[str, Any],
        scopes: List[str],
        subject: str,
        kind: str,
        markings: Optional[List[str]] = None,
        clearance: Optional[str] = None,
        auto_review: bool = False,
        reviewer_token: Optional[str] = None,
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """issue run 令牌 → propose → validate →（可选 review+commit）。

        参数：
        - scopes：run 令牌 scope（通常含 propose:<action>:<domain>）；
        - subject/kind：run 主体（agent 或 human 自提案）；
        - markings/clearance（P7.4）：对象级权限属性，签发时写入令牌
          claims（由签发方/装配目录决定，agent 不可自报提权）；
        - auto_review：True 时必须同时给 reviewer_token（human），否则
          报错——agent 无法凭自身令牌 commit；
        - reviewer_token：human reviewer/operator 令牌，存在即触发
          approve→内部 commit。

        返回 {proposal_id, status, run_token_fingerprint,
              reviewer_token_fingerprint?, decision_record?}。
        """
        if auto_review and reviewer_token is None:
            raise IdentityError(
                "auto_review requires a human reviewer_token; agent may not "
                "self-commit"
            )

        # 1) 签发 run-scoped 令牌（含对象级属性）
        run_token = self.authority.issue(
            run_id=run_id, subject=subject, kind=kind, scopes=scopes,
            markings=markings, clearance=clearance,
        )

        # 2) propose（Gate 校验 run 令牌 + scope）
        proposed = self.proposals.propose_action(
            domain, action, object_refs, params,
            caller_id=subject, caller_kind=kind,
            rationale=rationale, idempotency_key=idempotency_key,
            token=run_token,
        )
        proposal_id = proposed["id"]

        # 幂等重放：既有提案已被处理，直接回现状（不重跑 validate/review）
        if proposed.get("idempotent_replay"):
            current = self.proposals.get(proposal_id)
            return {
                "proposal_id": proposal_id,
                "status": current["status"],
                "run_token_fingerprint": self.authority.fingerprint(run_token),
                "idempotent_replay": True,
            }

        # 3) validate（纯校验，零副作用）
        validation = self.proposals.validate(proposal_id)
        if not validation.get("ok"):
            return {
                "proposal_id": proposal_id,
                "status": self.proposals.get(proposal_id)["status"],
                "run_token_fingerprint": self.authority.fingerprint(run_token),
                "validation": validation,
            }

        out: Dict[str, Any] = {
            "proposal_id": proposal_id,
            "status": "validated",
            "run_token_fingerprint": self.authority.fingerprint(run_token),
        }

        # 4) 可选 human review → 内部 commit
        if reviewer_token is not None:
            review_claims = self.authority.verify(reviewer_token)
            if review_claims["kind"] != "human":
                raise IdentityError(
                    "reviewer token must be kind=human to commit"
                )
            reviewed = self.proposals.review(
                proposal_id, "approve", review_claims["sub"],
                reviewer_kind="human", token=reviewer_token,
            )
            out["status"] = reviewed["status"]
            out["reviewer_token_fingerprint"] = (
                self.authority.fingerprint(reviewer_token)
            )
            if "decision_record" in reviewed:
                out["decision_record"] = reviewed["decision_record"]
            if "decision_record_id" in reviewed:
                out["decision_record_id"] = reviewed["decision_record_id"]

        return out
