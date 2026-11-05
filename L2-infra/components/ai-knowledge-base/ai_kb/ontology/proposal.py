"""ProposalService — P3 Proposal Gate 核心（详设 §2.3 / §3.3）.

两阶段提交 + 输出侧接地 + 决策对象化：
- propose_action：只建 pending + 目标快照，零写业务数据；
- validate：OutputGuard 内执行 ABAC→Schema→前置条件→状态机；
- review：human approve/reject（auto 审由策略决定，required_approval=auto
  且 validate 通过时可自动批准）；
- commit：单事务（幂等校验→状态校验→应用 change_set→写回连接器
  →写 ont_decision_record + kb_audit_log）；失败 ROLLBACK + Saga 补偿。

关键不变量：**validated ≠ committed**。validate 永不产生副作用。
幂等：idempotency_key UNIQUE 兜底；重复提交返回既有结果，不重放。
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional, Union

from ..audit import AuditLogger
from ..db import AIKB
from .actions import ActionRegistry
from .connectors.base import (
    CompensationUnavailable,
    NullConnector,
    SagaContext,
    WritebackConnector,
)
from .connectors.saga import (
    SagaExecutionError,
    SagaOrchestrator,
    SagaReport,
    SagaStep,
)
from .decision import DecisionService
from ..guardrails.output_guard import OutputGuard

# 五态状态机
_STATUSES = {"pending", "validated", "rejected", "committed", "failed"}
_CALLER_KINDS = {"human", "agent"}
_REVIEW_DECISIONS = {"approve", "reject"}


class ProposalService:
    """写治理提案服务，依赖注入 AIKB 与注册中心。"""

    def __init__(
        self,
        db: AIKB,
        registry: ActionRegistry,
        guard: Optional[OutputGuard] = None,
        decisions: Optional[DecisionService] = None,
        connectors: Optional[Dict[str, WritebackConnector]] = None,
        default_connector: Optional[WritebackConnector] = None,
    ) -> None:
        self.db = db
        self.registry = registry
        self.guard = guard or OutputGuard(registry)
        self.decisions = decisions or DecisionService(db)
        self.audit = AuditLogger(db)
        # 连接器表：writeback_target（connector key）→ connector
        self.connectors: Dict[str, WritebackConnector] = connectors or {}
        self.default_connector = default_connector or NullConnector()

    # --- 内部辅助 ---
    def _resolve_domain_id(self, domain: Union[int, str]) -> int:
        if isinstance(domain, int):
            return domain
        row = self.db.execute(
            "SELECT id FROM domain WHERE code = ?", (domain,)
        ).fetchone()
        if row is None:
            raise ValueError(f"domain not found: {domain}")
        return row[0]

    @staticmethod
    def _dump_json(value: Any, field_name: str) -> str:
        if isinstance(value, str):
            json.loads(value)
            return value
        if value is None:
            raise ValueError(f"{field_name} must not be None")
        return json.dumps(value, ensure_ascii=False)

    def _find_by_idempotency_key(self, key: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        row = self.db.execute(
            "SELECT * FROM ont_proposal WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return self._hydrate(row) if row else None

    def _hydrate(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        for f in ("params", "target_snapshot", "validation_result"):
            val = item.get(f)
            if isinstance(val, str):
                try:
                    item[f] = json.loads(val)
                except json.JSONDecodeError:
                    pass
        return item

    def _load_row(self, proposal_id: int) -> Dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM ont_proposal WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"proposal not found: {proposal_id}")
        return dict(row)

    def _build_snapshot(
        self,
        domain_id: int,
        object_type: str,
        object_refs: List[str],
    ) -> Dict[str, Any]:
        """从 ont_identity 读取目标对象变更前快照（CWA：必须已登记）。

        target_snapshot 结构：
        {"domain_id", "object_type", "identities": [{id, canonical_key,
         system_of_record, status, metadata, display_name}]}
        对象不存在直接拒绝（封闭世界），不允许对"不存在对象"提写提案。
        """
        if not object_refs:
            raise ValueError("object_refs must not be empty")
        identities: List[Dict[str, Any]] = []
        for key in object_refs:
            row = self.db.execute("""
            SELECT * FROM ont_identity
            WHERE domain_id = ? AND object_type = ? AND canonical_key = ?
            """, (domain_id, object_type, key)).fetchone()
            if row is None:
                raise ValueError(
                    f"operational object not found in closed world: "
                    f"{object_type}:{key}"
                )
            item = dict(row)
            if isinstance(item.get("metadata"), str):
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except json.JSONDecodeError:
                    pass
            identities.append(item)
        return {
            "domain_id": domain_id,
            "object_type": object_type,
            "identities": identities,
        }


    def _writeback_steps(self, action: Any) -> Optional[List[Dict[str, Any]]]:
        """多写回目标的有序步骤；无则返回 None（单连接器路径）。

        向后兼容：v11 表未初始化（未迁移的旧库）时按无多步处理，
        单连接器路径不受影响。
        """
        try:
            rows = self.db.execute(
                "SELECT * FROM ont_writeback_step WHERE action_type_id = ? "
                "ORDER BY seq", (action["id"],),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        return [dict(r) for r in rows] if rows else None

    # --- 公开 API（详设 §3.3）---
    def propose_action(
        self,
        domain: Union[int, str],
        action_name: str,
        object_refs: List[str],
        params: Union[str, Dict[str, Any]],
        *,
        caller_id: str,
        caller_kind: str,
        rationale: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """只建 pending + 目标快照，零业务写。

        幂等：同 idempotency_key 重复提交直接返回既有提案（不重放），
        由 UNIQUE 约束兜底（并发下 IntegrityError 也转为读既有记录）。
        """
        if caller_kind not in _CALLER_KINDS:
            raise ValueError(
                f"caller_kind must be one of {sorted(_CALLER_KINDS)}"
            )
        if not caller_id:
            raise ValueError("caller_id must not be empty")

        if idempotency_key:
            existing = self._find_by_idempotency_key(idempotency_key)
            if existing is not None:
                existing["idempotent_replay"] = True
                return existing

        domain_id = self._resolve_domain_id(domain)
        action = self.registry.get_action(domain_id, action_name)
        if action is None:
            raise ValueError(f"action_type not found: {action_name}")

        params_text = self._dump_json(params, "params")
        snapshot = self._build_snapshot(
            domain_id, action["object_type"], list(object_refs)
        )
        snapshot_text = json.dumps(snapshot, ensure_ascii=False)
        now = self.db.get_now()

        try:
            cursor = self.db.execute("""
            INSERT INTO ont_proposal
                (domain_id, action_type_id, caller_id, caller_kind, params,
                 target_snapshot, status, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (domain_id, action["id"], caller_id, caller_kind, params_text,
                  snapshot_text, idempotency_key, now))
            self.db.commit()
            proposal_id = cursor.lastrowid
        except Exception:
            # UNIQUE(idempotency_key) 并发兜底
            self.db.conn.rollback()
            if idempotency_key:
                existing = self._find_by_idempotency_key(idempotency_key)
                if existing is not None:
                    existing["idempotent_replay"] = True
                    return existing
            raise

        self.audit.log(
            operation_type="ont_propose", user_id=caller_id,
            object_type=action["object_type"],
            object_id=proposal_id, risk_level="low",
            action_taken="propose",
            details=json.dumps({
                "proposal_id": proposal_id,
                "action": action_name,
                "object_refs": list(object_refs),
                "rationale": rationale,
                "idempotency_key": idempotency_key,
            }, ensure_ascii=False),
        )
        return self.get(proposal_id)

    def validate(
        self,
        proposal_id: int,
        caller_attrs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """调绑定 deterministic function（在 OutputGuard 内执行）。

        只做校验并写 validation_result / 状态（pending→validated 或
        保持 pending 并留违规痕），**绝不应用任何变更**（validated≠committed）。
        """
        row = self._load_row(proposal_id)
        if row["status"] not in ("pending",):
            # 已 validated 可重复读结果；rejected/committed/failed 不允许重验
            if row["status"] == "validated":
                return {
                    "ok": True,
                    "violations": [],
                    "proposal_id": proposal_id,
                    "status": "validated",
                }
            raise ValueError(
                f"proposal {proposal_id} is {row['status']}, cannot validate"
            )

        proposal = self._hydrate(row)
        attrs = caller_attrs or {
            "user_id": row["caller_id"],
            "role": row["caller_id"],
            "clearance": "internal",
        }
        result = self.guard.validate_proposal(proposal, attrs)
        violations = result["violations"]
        now = self.db.get_now()

        if result["ok"]:
            self.db.execute("""
            UPDATE ont_proposal
            SET status = 'validated', validation_result = ?
            WHERE id = ?
            """, (json.dumps({"ok": True, "violations": []}, ensure_ascii=False),
                  proposal_id))
        else:
            # 校验失败不迁移终态（仍 pending，等待修正/驳回），但留痕
            self.db.execute("""
            UPDATE ont_proposal SET validation_result = ? WHERE id = ?
            """, (json.dumps(
                {"ok": False, "violations": violations}, ensure_ascii=False),
                proposal_id))
        self.db.commit()

        self.audit.log(
            operation_type="ont_validate", user_id=row["caller_id"],
            object_type="ont_proposal", object_id=proposal_id,
            risk_level="medium" if violations else "low",
            action_taken="pass" if result["ok"] else "violations",
            details=json.dumps({
                "proposal_id": proposal_id,
                "ok": result["ok"],
                "violations": violations,
            }, ensure_ascii=False),
        )
        result["proposal_id"] = proposal_id
        result["status"] = self.get(proposal_id)["status"]
        return result

    def review(
        self,
        proposal_id: int,
        decision: str,
        reviewer: str,
        *,
        reviewer_kind: str = "human",
        auto_commit: bool = True,
    ) -> Dict[str, Any]:
        """human 审：approve/reject；approve 后按策略触发内部 commit。

        - reject：终态 rejected，写 rejected 决策记录 + 审计（拒绝留痕）；
        - approve：仅 human 可审 human 级提案；required_approval=auto 的
          提案由 auto 策略（reviewer_kind 可为 system/agent 语义，统一记
          agent）批准。approve 且 auto_commit=True 时内部调用 commit。
        commit 不存在任何对外的直接工具/端点。
        """
        if decision not in _REVIEW_DECISIONS:
            raise ValueError(
                f"decision must be one of {sorted(_REVIEW_DECISIONS)}"
            )
        if reviewer_kind not in ("human", "agent"):
            raise ValueError("reviewer_kind must be 'human' or 'agent'")

        row = self._load_row(proposal_id)
        action = self.db.execute(
            "SELECT * FROM ont_action_type WHERE id = ?",
            (row["action_type_id"],),
        ).fetchone()

        if row["status"] != "validated":
            raise ValueError(
                f"proposal {proposal_id} is {row['status']}; only validated "
                f"proposals can be reviewed"
            )
        if action["required_approval"] == "human" and reviewer_kind != "human":
            raise PermissionError(
                "this action requires human approval; agent may not review"
            )

        now = self.db.get_now()

        if decision == "reject":
            self.db.execute("""
            UPDATE ont_proposal
            SET status = 'rejected', review_by = ?, review_at = ?
            WHERE id = ?
            """, (reviewer, now, proposal_id))
            self.db.commit()
            proposal = self._hydrate(self._load_row(proposal_id))
            refs = [i["canonical_key"] for i in
                    proposal["target_snapshot"]["identities"]]
            record_id = self.decisions.record(
                row["domain_id"], action["name"], refs, reviewer, reviewer_kind,
                change_set={"applied": False, "before": proposal["target_snapshot"]},
                proposal_id=proposal_id,
                rationale=f"rejected: {proposal.get('validation_result')}",
                evidence={
                    "validation_result": proposal.get("validation_result"),
                    "reviewer": reviewer,
                },
                result="rejected",
            )
            self.audit.log(
                operation_type="ont_review", user_id=reviewer,
                object_type="ont_proposal", object_id=proposal_id,
                risk_level="medium", rule_triggered="human_reject",
                action_taken="reject",
                details=json.dumps({
                    "proposal_id": proposal_id,
                    "decision_record_id": record_id,
                }, ensure_ascii=False),
            )
            out = self.get(proposal_id)
            out["decision_record_id"] = record_id
            return out

        # approve
        self.db.execute("""
        UPDATE ont_proposal
        SET review_by = ?, review_at = ?
        WHERE id = ?
        """, (reviewer, now, proposal_id))
        self.db.commit()
        self.audit.log(
            operation_type="ont_review", user_id=reviewer,
            object_type="ont_proposal", object_id=proposal_id,
            risk_level="low", action_taken="approve",
            details=json.dumps({"proposal_id": proposal_id}, ensure_ascii=False),
        )
        if auto_commit:
            record = self.commit(proposal_id)
            out = self.get(proposal_id)
            out["decision_record"] = record
            return out
        return self.get(proposal_id)

    def commit(self, proposal_id: int) -> Dict[str, Any]:
        """单事务提交（详设 §3.3 事务时序）。

        BEGIN
          1) 幂等校验：已 committed → 直接返回既有 decision_record，不重放
          2) 状态校验：status='validated' 且审批要求已满足（review_by 已写）
          3) 应用 change_set（本地对象 metadata 变更）
          4) 写回连接器（失败抛异常 → ROLLBACK + Saga 补偿）
          5) 写 ont_decision_record + kb_audit_log
        COMMIT；失败 ROLLBACK，连接器补偿失败 → failed + 人工对账记录。
        """
        row = self._load_row(proposal_id)

        # 1) 幂等：已提交不重放
        if row["status"] == "committed":
            rec = self.db.execute(
                "SELECT * FROM ont_decision_record WHERE proposal_id = ? "
                "ORDER BY id DESC LIMIT 1", (proposal_id,)
            ).fetchone()
            return self.decisions.get(rec["id"]) if rec else self.get(proposal_id)

        # 2) 状态 + 审批校验
        if row["status"] != "validated":
            raise ValueError(
                f"proposal {proposal_id} is {row['status']}; commit requires "
                f"'validated' (validated != committed invariant)"
            )
        action = self.db.execute(
            "SELECT * FROM ont_action_type WHERE id = ?",
            (row["action_type_id"],),
        ).fetchone()
        if action["required_approval"] in ("human", "auto") and not row["review_by"]:
            raise PermissionError(
                f"action requires {action['required_approval']} approval "
                f"before commit"
            )

        proposal = self._hydrate(row)
        params = proposal["params"]
        snapshot = proposal["target_snapshot"]
        refs = [i["canonical_key"] for i in snapshot["identities"]]
        writeback_steps = self._writeback_steps(action)
        connector = self.connectors.get(
            action["writeback_target"], self.default_connector
        )
        saga = SagaContext()
        saga_report: Optional[SagaReport] = None

        try:
            # 3) 应用 change_set（库内：把参数声明的对象字段变更写入
            #    ont_identity.metadata.applied_changes，纯增量、可追溯）
            change_set = self._apply_change_set(proposal, action, params, snapshot)

            # 4) 写回源系统（多步走 SagaOrchestrator；单步保持原路径）
            if writeback_steps:
                steps = []
                for sr in writeback_steps:
                    ckey = sr["connector_key"]
                    if ckey not in self.connectors:
                        raise ValueError(
                            f"connector not registered for step: {ckey}"
                        )
                    steps.append(SagaStep(
                        name=ckey, connector=self.connectors[ckey],
                    ))
                orchestrator = SagaOrchestrator(steps)
                saga_report = orchestrator.run()
                if not saga_report.ok:
                    raise SagaExecutionError(saga_report)
                connector_name = "+".join(saga_report.executed_steps)
            else:
                saga.add_step("apply_change_set")
                saga.mark_success("apply_change_set", {"identities": refs})
                connector.apply(saga)
                connector_name = connector.name

            # 5) 决策记录 + 审计（同事务，不单独 commit）
            record_id = self.decisions.record_no_commit(
                row["domain_id"], action["name"], refs,
                row["caller_id"], row["caller_kind"],
                change_set=change_set,
                proposal_id=proposal_id,
                rationale=proposal.get("rationale"),
                evidence={
                    "validation_result": proposal.get("validation_result"),
                    "review_by": row["review_by"],
                    "connector": connector_name,
                    "saga_steps": saga.steps,
                    "saga_report": (
                        saga_report.as_dict() if saga_report else None
                    ),
                },
                result="allowed",
            )
            now = self.db.get_now()
            self.db.execute("""
            UPDATE ont_proposal
            SET status = 'committed', committed_at = ?
            WHERE id = ?
            """, (now, proposal_id))
            self.db.execute(
                "INSERT INTO kb_audit_log "
                "(timestamp, user_id, operation_type, object_type, object_id, "
                " request_id, risk_level, rule_triggered, action_taken, details, created_at) "
                "VALUES (?, ?, 'ont_commit', 'ont_proposal', ?, ?, 'low', "
                "        'proposal_gate', 'commit', ?, ?)",
                (now, row["caller_id"], proposal_id,
                 f"commit-{proposal_id}-{record_id}",
                 json.dumps({
                     "proposal_id": proposal_id,
                     "decision_record_id": record_id,
                     "action": action["name"],
                 }, ensure_ascii=False), now),
            )
            self.db.commit()
            return self.decisions.get(record_id)

        except Exception as exc:
            # ROLLBACK 本地事务
            self.db.conn.rollback()
            if saga_report is not None:
                # 多步 Saga：补偿已在编排器内完成；按报告决定降级
                if saga_report.reconciliation_required:
                    self._mark_failed_with_recon(
                        proposal_id, row, action, refs, exc,
                        saga_report=saga_report,
                    )
                else:
                    self._mark_failed(proposal_id, row, action, refs, exc,
                                      compensated=True,
                                      saga_report=saga_report)
                raise
            # 单连接器路径：原补偿语义
            try:
                connector.compensate(saga)
            except CompensationUnavailable:
                self._mark_failed_with_recon(proposal_id, row, action, refs, exc)
                raise
            except Exception:
                self._mark_failed_with_recon(proposal_id, row, action, refs, exc)
                raise
            self._mark_failed(proposal_id, row, action, refs, exc,
                              compensated=True)
            raise

    def _apply_change_set(
        self,
        proposal: Dict[str, Any],
        action: Any,
        params: Dict[str, Any],
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """在本地库内应用对象变更（纯增量 metadata 记录）。

        P3 不内置具体业务表写入（业务字段在 L3/L4）；统一把动作参数
        作为变更集追加到目标身份 metadata.applied_changes，形成
        before/after 可回放的 change_set。
        """
        before = []
        after = []
        now = self.db.get_now()
        for ident in snapshot["identities"]:
            iid = ident["id"]
            row = self.db.execute(
                "SELECT metadata FROM ont_identity WHERE id = ?", (iid,)
            ).fetchone()
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            before.append({"id": iid, "metadata": metadata})
            applied = metadata.setdefault("applied_changes", [])
            applied.append({
                "action": action["name"],
                "proposal_id": proposal["id"],
                "params": params,
                "ts": now,
            })
            self.db.execute(
                "UPDATE ont_identity SET metadata = ?, updated_at = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False), now, iid),
            )
            after.append({"id": iid, "metadata": metadata})
        return {
            "applied": True,
            "before": before,
            "after": after,
            "params": params,
        }

    def _mark_failed(self, proposal_id, row, action, refs, exc, *,
                     compensated, saga_report: Optional[SagaReport] = None):
        now = self.db.get_now()
        self.db.execute("""
        UPDATE ont_proposal SET status = 'failed' WHERE id = ?
        """, (proposal_id,))
        try:
            self.decisions.record_no_commit(
                row["domain_id"], action["name"], refs,
                row["caller_id"], row["caller_kind"],
                change_set={"applied": False},
                proposal_id=proposal_id,
                rationale=f"commit failed then compensated: {exc}",
                evidence={
                    "error": str(exc),
                    "compensated": compensated,
                    "saga_report": (
                        saga_report.as_dict() if saga_report else None
                    ),
                },
                result="compensated",
            )
            self.db.commit()
        except Exception:
            self.db.conn.rollback()

    def _mark_failed_with_recon(
        self, proposal_id, row, action, refs, exc,
        saga_report: Optional[SagaReport] = None,
    ):
        """补偿不可用：failed + 人工对账工单记录（result='compensated'）。"""
        now = self.db.get_now()
        self.db.execute(
            "UPDATE ont_proposal SET status = 'failed' WHERE id = ?",
            (proposal_id,),
        )
        try:
            self.decisions.record_no_commit(
                row["domain_id"], action["name"], refs,
                row["caller_id"], row["caller_kind"],
                change_set={"applied": False, "reconciliation_required": True},
                proposal_id=proposal_id,
                rationale=(
                    "commit failed; reverse compensation unavailable, "
                    "manual reconciliation ticket required"
                ),
                evidence={
                    "error": str(exc),
                    "reconciliation": "manual",
                    "saga_report": (
                        saga_report.as_dict() if saga_report else None
                    ),
                },
                result="compensated",
            )
            self.db.execute(
                "INSERT INTO kb_audit_log "
                "(timestamp, user_id, operation_type, object_type, object_id, "
                " request_id, risk_level, rule_triggered, action_taken, details, created_at) "
                "VALUES (?, ?, 'ont_reconcile', 'ont_proposal', ?, ?, 'high', "
                "        'compensation_unavailable', 'manual_ticket', ?, ?)",
                (now, row["caller_id"], proposal_id,
                 f"reconcile-{proposal_id}",
                 json.dumps({
                     "proposal_id": proposal_id,
                     "error": str(exc),
                     "manual_reconciliation_required": True,
                 }, ensure_ascii=False), now),
            )
            self.db.commit()
        except Exception:
            self.db.conn.rollback()

    def get(self, proposal_id: int) -> Dict[str, Any]:
        """状态查询（含反序列化 JSON 字段）。"""
        return self._hydrate(self._load_row(proposal_id))

    def list_proposals(
        self,
        domain: Union[int, str],
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """管理/查询用：按 domain（可选 status）列提案。"""
        if status is not None and status not in _STATUSES:
            raise ValueError(f"status must be one of {sorted(_STATUSES)}")
        domain_id = self._resolve_domain_id(domain)
        sql = "SELECT * FROM ont_proposal WHERE domain_id = ?"
        params: List[Any] = [domain_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self.db.execute(sql, tuple(params)).fetchall()
        return [self._hydrate(r) for r in rows]
