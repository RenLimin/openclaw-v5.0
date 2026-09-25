"""合同管理服务层 — ContractManagementService。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

职责：
  - create_contract / submit_approval / approve / reject / sign / archive
  - generate_docx / scan_risks / analyze_subject
  - get_contract / list_contracts / audit_log
  - 所有写操作使用审计字段
  - 所有查询自动过滤软删除
  - 敏感字段加密存储，列表接口脱敏
"""

import os
import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime

from bdms.core import db as _db
from bdms.core.paths import DATA_DIR
from ..base import BaseService, audit_insert_sql, audit_update_sql

from .engine import ContractManagementEngine
from .models import (
    Contract,
    ContractDocument,
    ContractClause,
    RiskScanResult,
    ApprovalNode,
    AuditTrailEntry,
    CONTRACT_STATUSES,
)
from ._crypto import encrypt, decrypt, mask_name, mask_amount


class ContractManagementService(BaseService):
    """合同管理服务层。"""

    module_name = "contract_management"

    def __init__(self, db_path: Optional[Path] = None):
        self.engine = ContractManagementEngine(db_path)
        self.db_path = self.engine.db_path
        # RBAC：当前操作的角色（可通过 set_current_roles 设置）
        self._current_roles: list[str] = []
        super().__init__()

    # ─── RBAC 上下文 ───

    def set_current_roles(self, roles: list[str]) -> None:
        """设置当前操作的角色列表（用于权限检查）。"""
        self._current_roles = roles if roles else []

    def has_permission(self, permission: str) -> bool:
        """检查当前角色是否拥有指定权限。"""
        from bdms.security import has_permission
        return has_permission(self._current_roles, permission)

    def _require_permission(self, permission: str) -> None:
        """权限检查，不通过抛 PermissionError。

        Raises:
            PermissionError: 无权限
        """
        from bdms.modules.base import PermissionError
        if not self.has_permission(permission):
            raise PermissionError(
                f"无权限执行此操作: {permission}，"
                f"当前角色: {self._current_roles}"
            )

    # ══════════════════════════════════════════════════════════
    # 创建合同
    # ══════════════════════════════════════════════════════════

    def create_contract(self, data: dict, operator: str = "") -> dict:
        """创建合同。

        Args:
            data: 合同字段 dict
            operator: 操作人

        Returns:
            {"id": int, "contract_no": str}

        Raises:
            PermissionError: 无 cr_create 权限（当已设置角色时）
        """
        # RBAC：如果设置了角色，检查权限
        if self._current_roles:
            self._require_permission("cr_create")
        conn = _db.get_connection(self.db_path)
        try:
            # 生成合同编号
            contract_no = data.get("contract_no") or self._generate_contract_no(conn)

            # 计算审批级别
            amount = float(data.get("amount", 0))
            approval_config = self.engine.get_approval_level(amount)

            # 加密敏感字段
            party_a_enc = encrypt(data.get("party_a", ""))
            party_b_enc = encrypt(data.get("party_b", ""))

            now = datetime.now().isoformat()
            # 实施相关字段（v2.1 扩展）
            impl_owner = data.get("impl_owner", "")
            impl_status = data.get("impl_status", "not_started")

            sql = f"""INSERT INTO cr_contracts
                      (created_at, updated_at, created_by, updated_by,
                       contract_no, title, contract_type,
                       party_a, party_b, amount, currency,
                       effective_date, expiry_date, status, approval_level,
                       impl_owner, impl_status)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            cur = conn.execute(sql, [
                now, now, operator, operator,
                contract_no,
                data.get("title", ""),
                data.get("contract_type", ""),
                party_a_enc,
                party_b_enc,
                amount,
                data.get("currency", "CNY"),
                data.get("effective_date", ""),
                data.get("expiry_date", ""),
                "draft",
                approval_config["level"],
                impl_owner,
                impl_status,
            ])
            contract_id = cur.lastrowid

            # 写入审计日志
            self._write_audit(conn, contract_id, "CREATE", "", "",
                              json.dumps({"contract_no": contract_no, "title": data.get("title", "")}),
                              operator)

            conn.commit()
            return {"id": contract_id, "contract_no": contract_no}
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 更新合同
    # ══════════════════════════════════════════════════════════

    def update_contract(self, contract_id: int, updates: dict, operator: str = "") -> dict:
        """更新合同基本信息。

        Raises:
            PermissionError: 无 cr_edit 权限（当已设置角色时）

        可更新字段：title, contract_type, amount, currency,
        effective_date, expiry_date, impl_owner, impl_status 等。
        状态变更请用 approve/reject/sign/archive。

        Args:
            contract_id: 合同 ID
            updates: 待更新字段 dict
            operator: 操作人

        Returns:
            {"id": int, "updated_fields": list}
        """
        from .models import VALID_IMPL_STATUSES

        # RBAC
        if self._current_roles:
            self._require_permission("cr_edit")

        conn = _db.get_connection(self.db_path)
        try:
            # 校验存在
            row = conn.execute(
                "SELECT * FROM cr_contracts WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')",
                (contract_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"合同 {contract_id} 不存在或已删除")

            # 允许更新的字段
            allowed = {
                "title", "contract_type", "amount", "currency",
                "effective_date", "expiry_date", "impl_owner", "impl_status",
                "party_a", "party_b",
            }
            update_fields = {k: v for k, v in updates.items() if k in allowed}
            if not update_fields:
                return {"id": contract_id, "updated_fields": []}

            # 校验 impl_status
            if "impl_status" in update_fields:
                if update_fields["impl_status"] not in VALID_IMPL_STATUSES:
                    raise ValueError(
                        f"无效的实施状态: {update_fields['impl_status']}，"
                        f"有效值: {VALID_IMPL_STATUSES}"
                    )

            # 加密敏感字段
            if "party_a" in update_fields:
                update_fields["party_a"] = encrypt(update_fields["party_a"])
            if "party_b" in update_fields:
                update_fields["party_b"] = encrypt(update_fields["party_b"])

            # 构造 UPDATE SQL
            set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
            set_clause += ", updated_at = ?, updated_by = ?"
            values = list(update_fields.values()) + [datetime.now().isoformat(), operator]
            values.append(contract_id)

            conn.execute(
                f"UPDATE cr_contracts SET {set_clause} WHERE id = ?",
                values,
            )

            # 写审计
            for field, old_val in update_fields.items():
                self._write_audit(
                    conn, contract_id, "UPDATE", field,
                    str(dict(row).get(field, "")), str(old_val), operator,
                )

            conn.commit()
            return {"id": contract_id, "updated_fields": list(update_fields.keys())}
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 提交审批
    # ══════════════════════════════════════════════════════════

    def submit_approval(self, contract_id: int, operator: str = "",
                        comment: str = "") -> dict:
        """提交审批（draft → review1）。

        Raises:
            PermissionError: 无 cr_approve 权限（当已设置角色时）
        """
        if self._current_roles:
            self._require_permission("cr_approve")
        return self._transition(contract_id, "review1", "submit",
                                  operator, comment)

    # ══════════════════════════════════════════════════════════
    # 审批通过
    # ══════════════════════════════════════════════════════════

    def approve(self, contract_id: int, operator: str = "",
                role: str = "", comment: str = "") -> dict:
        """审批通过 — 根据当前状态自动判断下一状态。

        Raises:
            PermissionError: 无 cr_approve 权限（当已设置角色时）
        """
        if self._current_roles:
            self._require_permission("cr_approve")
        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"合同 {contract_id} 不存在")

        current = contract["status"]
        amount = contract.get("amount", 0)
        approval_config = self.engine.get_approval_level(amount)
        level = approval_config["level"]

        # 根据当前级别决定下一状态
        if current == "review1":
            if level >= 2:
                next_status = "review2"
            else:
                next_status = "approved"
        elif current == "review2":
            if level >= 3:
                next_status = "review3"
            else:
                next_status = "approved"
        elif current == "review3":
            if level >= 4:
                next_status = "review4"
            else:
                next_status = "approved"
        elif current == "review4":
            next_status = "approved"
        else:
            raise ValueError(f"当前状态 {current} 不允许审批通过")

        result = self._transition(contract_id, next_status, "approve",
                                  operator, comment, role=role)
        result["approval_level"] = level
        return result

    # ══════════════════════════════════════════════════════════
    # 驳回
    # ══════════════════════════════════════════════════════════

    def reject(self, contract_id: int, operator: str = "",
               role: str = "", comment: str = "") -> dict:
        """驳回合同 → 回到 draft（设计文档：驳回回起草）。"""
        return self._transition(contract_id, "draft", "reject",
                                  operator, comment, role=role)

    # ══════════════════════════════════════════════════════════
    # 签署
    # ══════════════════════════════════════════════════════════

    def sign(self, contract_id: int, operator: str = "",
             comment: str = "") -> dict:
        """签署合同（approved → signed）。"""
        now = datetime.now().isoformat()[:10]
        conn = _db.get_connection(self.db_path)
        try:
            result = self._transition(contract_id, "signed", "sign",
                                      operator, comment)
            conn.execute(
                "UPDATE cr_contracts SET signed_date = ? WHERE id = ?",
                (now, contract_id),
            )
            conn.commit()
            return result
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 归档
    # ══════════════════════════════════════════════════════════

    def archive(self, contract_id: int, operator: str = "") -> dict:
        """归档合同（signed → archived）。"""
        now = datetime.now().isoformat()[:10]
        conn = _db.get_connection(self.db_path)
        try:
            result = self._transition(contract_id, "archived", "archive",
                                      operator, "")
            conn.execute(
                "UPDATE cr_contracts SET archive_date = ? WHERE id = ?",
                (now, contract_id),
            )
            conn.commit()
            return result
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 状态流转核心
    # ══════════════════════════════════════════════════════════

    def _transition(self, contract_id: int, to_status: str, action: str,
                    operator: str, comment: str = "", role: str = "") -> dict:
        """执行状态流转。"""
        conn = _db.get_connection(self.db_path)
        try:
            # 获取当前状态
            row = conn.execute(
                "SELECT status FROM cr_contracts WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')",
                (contract_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"合同 {contract_id} 不存在或已删除")

            from_status = row["status"]

            # 校验流转合法性
            validation = self.engine.validate_state_transition(from_status, to_status)
            if not validation["valid"]:
                raise ValueError(validation["message"])

            now = datetime.now().isoformat()

            # 更新状态
            conn.execute(
                "UPDATE cr_contracts SET status = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                (to_status, now, operator, contract_id),
            )

            # 写审批日志
            conn.execute(
                """INSERT INTO cr_approval_log
                   (contract_id, from_status, to_status, action,
                    approver_name, approver_role, comment, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (contract_id, from_status, to_status, action,
                 operator, role, comment, now),
            )

            # 写审计追踪
            self._write_audit(conn, contract_id, "STATUS_CHANGE",
                              "status", from_status, to_status, operator)

            conn.commit()
            return {
                "id": contract_id,
                "from_status": from_status,
                "to_status": to_status,
                "action": action,
            }
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 查询
    # ══════════════════════════════════════════════════════════

    def get_contract(self, contract_id: int) -> Optional[dict]:
        """获取单个合同详情（解密敏感字段）。

        Raises:
            PermissionError: 无 cr_view 权限（当已设置角色时）
        """
        if self._current_roles:
            self._require_permission("cr_view")
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM cr_contracts WHERE id = ? AND (deleted_at IS NULL OR deleted_at = '')",
                (contract_id,),
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            # 解密敏感字段
            d["party_a"] = decrypt(d.get("party_a", ""))
            d["party_b"] = decrypt(d.get("party_b", ""))
            return d
        finally:
            conn.close()

    def list_contracts(self, filters: dict = None, page: int = 1,
                       page_size: int = 20, mask: bool = True) -> dict:
        """列表查询（自动过滤软删除，金额脱敏）。

        Raises:
            PermissionError: 无 cr_view 权限（当已设置角色时）

        Args:
            filters: 过滤条件 {"status": "draft", "contract_type": "..."}
            page: 页码（从 1 开始）
            page_size: 每页条数
            mask: 是否脱敏

        Returns:
            {"items": list[dict], "total": int, "page": int, "page_size": int}
        """
        # RBAC
        if self._current_roles:
            self._require_permission("cr_view")

        filters = filters or {}
        conn = _db.get_connection(self.db_path)
        try:
            where = ["(c.deleted_at IS NULL OR c.deleted_at = '')"]
            params: list = []

            if filters.get("status"):
                where.append("c.status = ?")
                params.append(filters["status"])
            if filters.get("contract_type"):
                where.append("c.contract_type = ?")
                params.append(filters["contract_type"])
            if filters.get("impl_owner"):
                where.append("c.impl_owner = ?")
                params.append(filters["impl_owner"])
            if filters.get("impl_status"):
                where.append("c.impl_status = ?")
                params.append(filters["impl_status"])
            if filters.get("keyword"):
                where.append("(c.title LIKE ? OR c.contract_no LIKE ?)")
                kw = f"%{filters['keyword']}%"
                params.extend([kw, kw])

            where_sql = " AND ".join(where)

            # 总数
            total_row = conn.execute(
                f"SELECT COUNT(*) AS n FROM cr_contracts c WHERE {where_sql}",
                params,
            ).fetchone()
            total = total_row["n"]

            # 分页
            offset = (page - 1) * page_size
            rows = conn.execute(
                f"""SELECT c.* FROM cr_contracts c
                    WHERE {where_sql}
                    ORDER BY c.id DESC
                    LIMIT ? OFFSET ?""",
                params + [page_size, offset],
            ).fetchall()

            items = []
            for r in rows:
                d = dict(r)
                if mask:
                    # 脱敏处理
                    d["party_a"] = mask_name(decrypt(d.get("party_a", "")))
                    d["party_b"] = mask_name(decrypt(d.get("party_b", "")))
                    d["amount_display"] = mask_amount(d.get("amount", 0))
                else:
                    d["party_a"] = decrypt(d.get("party_a", ""))
                    d["party_b"] = decrypt(d.get("party_b", ""))
                items.append(d)

            return {"items": items, "total": total, "page": page, "page_size": page_size}
        finally:
            conn.close()

    def audit_log(self, contract_id: int) -> list[dict]:
        """获取合同的审计日志（审批日志 + 审计追踪）。"""
        conn = _db.get_connection(self.db_path)
        try:
            # 审批日志
            approval_rows = conn.execute(
                """SELECT * FROM cr_approval_log
                   WHERE contract_id = ? ORDER BY created_at""",
                (contract_id,),
            ).fetchall()

            # 审计追踪
            audit_rows = conn.execute(
                """SELECT * FROM cr_audit_trail
                   WHERE contract_id = ? ORDER BY created_at""",
                (contract_id,),
            ).fetchall()

            return {
                "approval_log": [dict(r) for r in approval_rows],
                "audit_trail": [dict(r) for r in audit_rows],
            }
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 风险扫描
    # ══════════════════════════════════════════════════════════

    def scan_risks(self, contract_id: int, contract_content: str = "") -> list[dict]:
        """对合同执行风险扫描并持久化结果。"""
        if not contract_content:
            # 尝试从合同详情获取内容
            contract = self.get_contract(contract_id)
            if contract:
                contract_content = f"{contract.get('title', '')} {contract.get('contract_type', '')}"

        results = self.engine.scan_risks(contract_content)

        conn = _db.get_connection(self.db_path)
        try:
            saved = []
            for r in results:
                r.contract_id = contract_id
                cur = conn.execute(
                    """INSERT INTO cr_risk_scan_results
                       (contract_id, scan_batch, risk_category, risk_level,
                        issue_summary, suggestion, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (r.contract_id, r.scan_batch, r.risk_category, r.risk_level,
                     r.issue_summary, r.suggestion, r.status, r.created_at),
                )
                r.id = cur.lastrowid
                saved.append({
                    "id": r.id,
                    "risk_category": r.risk_category,
                    "risk_level": r.risk_level,
                    "issue_summary": r.issue_summary,
                    "suggestion": r.suggestion,
                })
            conn.commit()
            return saved
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 标的对比分析
    # ══════════════════════════════════════════════════════════

    def analyze_subject(self, contract_id: int,
                        kb_items: list[dict] = None) -> dict:
        """合同标的对比分析。"""
        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"合同 {contract_id} 不存在")
        if kb_items is None:
            kb_items = []
        return self.engine.analyze_subject(contract, kb_items)


    # ─── 审核建议生成（场景 A）───

    def generate_review_suggestions(self, contract_id: int) -> dict:
        """生成可编辑的审核建议（结构化 JSON）。

        包含：条款修改建议、自动填充字段、风险提示。
        对齐 DESIGN-DETAIL §2.2 输出格式。

        Args:
            contract_id: 合同 ID

        Returns:
            {
                "contract_no": str,
                "overall_risk": "high"|"medium"|"low",
                "suggestions": [
                    {"clause_type": str, "current_text": str, "suggested_text": str,
                     "risk_level": str, "law_ref": str, "reason": str},
                    ...
                ],
                "auto_fill_fields": {
                    "party_a": str,
                    "amount": float,
                    "effective_date": str,
                    ...
                }
            }
        """
        from .review_suggestions import ReviewSuggestionGenerator

        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"合同 {contract_id} 不存在")

        # 获取风险扫描结果（如果没扫过就扫一次）
        conn = _db.get_connection(self.db_path)
        try:
            risk_rows = conn.execute(
                """SELECT * FROM cr_risk_scan_results
                   WHERE contract_id = ? AND status = 'open'
                   ORDER BY risk_level DESC, created_at DESC""",
                (contract_id,),
            ).fetchall()
            risk_results = [dict(r) for r in risk_rows]
        finally:
            conn.close()

        # 如果还没有风险结果，执行扫描
        if not risk_results:
            risk_results = self.scan_risks(contract_id)

        # 获取条款明细
        conn = _db.get_connection(self.db_path)
        try:
            clause_rows = conn.execute(
                """SELECT * FROM cr_contract_clauses
                   WHERE contract_id = ? AND (deleted_at IS NULL OR deleted_at = '')
                   ORDER BY sort_order""",
                (contract_id,),
            ).fetchall()
            clauses = [dict(r) for r in clause_rows]
        finally:
            conn.close()

        # 生成审核建议
        generator = ReviewSuggestionGenerator()
        suggestions = generator.generate(contract, risk_results, clauses)

        return suggestions

    # ─── OA 自动获取（场景 A/B）───

    def fetch_from_oa(self, contract_no: str = None, fetch_type: str = "single") -> dict:
        """通过 integration I-02 连接器从 OA 获取合同。

        注意：实际的浏览器自动化操作由 integration 模块的 I-02 OA 连接器负责。
        本方法提供统一入口，尝试调用连接器；不可用时返回降级信息。

        Args:
            contract_no: 合同编号（single/ledger 类型时使用）
            fetch_type: 获取类型
                - "single": 按编号获取单份合同
                - "batch": 获取待审批列表（场景 A）
                - "ledger": 获取台账列表（场景 B）

        Returns:
            {
                "contracts": list[dict],
                "source": "oa",
                "fetch_type": str,
                "count": int,
                "degraded": bool,     # 是否降级（浏览器自动化不可用时）
                "degrade_reason": str,
            }
        """
        from .errors import OaFetchError, DegradationInfo

        # 尝试调用 integration 模块的 OA 连接器
        try:
            result = self._try_integration_oa_fetch(contract_no, fetch_type)
            if result:
                return {
                    "contracts": result.get("contracts", []),
                    "source": "oa",
                    "fetch_type": fetch_type,
                    "count": len(result.get("contracts", [])),
                    "degraded": False,
                    "degrade_reason": "",
                }
        except Exception as e:
            degrade_reason = str(e)
        else:
            degrade_reason = "integration 模块不可用"

        # 降级：返回空结果 + 降级信息
        return {
            "contracts": [],
            "source": "oa",
            "fetch_type": fetch_type,
            "count": 0,
            "degraded": True,
            "degrade_reason": degrade_reason,
            "fallback": "请手动导入合同或使用 OCR 导入功能",
        }

    def _try_integration_oa_fetch(self, contract_no: str = None,
                                   fetch_type: str = "single") -> dict | None:
        """尝试调用 integration 模块的 OA 连接器。

        Returns:
            连接器结果 dict，或 None 表示连接器不可用。
        """
        try:
            from bdms.modules.data_integration.connectors import get_connector
            connector = get_connector("oa")
            if connector is None:
                return None

            if fetch_type == "single":
                if not contract_no:
                    raise ValueError("single 模式需要 contract_no")
                return connector.fetch_contract(contract_no)
            elif fetch_type == "batch":
                return connector.fetch_approval_list()
            elif fetch_type == "ledger":
                return connector.fetch_ledger(contract_no=contract_no)
            else:
                raise ValueError(f"未知的 fetch_type: {fetch_type}")
        except ImportError:
            return None

    # ─── 合同关联关系 ───

    def get_related_contracts(self, contract_id: int) -> dict:
        """获取合同关联关系树。

        对齐 DESIGN-DETAIL §7.3 接口定义。

        Args:
            contract_id: 合同 ID

        Returns:
            {
                "source": {"id": int, "contract_no": str, "title": str},
                "relations": [
                    {"contract": {...}, "relation_type": str, "match_rule": str},
                    ...
                ]
            }
        """
        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"合同 {contract_id} 不存在")

        # 先自动构建一次关联（增量，幂等）
        try:
            self.engine.auto_build_relations(contract_id)
        except Exception:
            pass  # 自动构建失败不影响查询

        # 查询已有关系
        relations = self.engine.list_relations(contract_id)

        # 格式化输出
        formatted_relations = []
        for rel in relations:
            other_id = rel["target_contract_id"] if rel["direction"] == "source"                 else rel["source_contract_id"]
            other_contract = self.get_contract(other_id)
            if other_contract:
                # 脱敏（关系列表也脱敏）
                from ._crypto import mask_name, mask_amount
                other_contract["party_a"] = mask_name(other_contract.get("party_a", ""))
                other_contract["party_b"] = mask_name(other_contract.get("party_b", ""))
                other_contract["amount_display"] = mask_amount(other_contract.get("amount", 0))

            formatted_relations.append({
                "contract": other_contract or {},
                "relation_type": rel["relation_type"],
                "match_rule": rel["match_rule"],
                "direction": rel["direction"],
            })

        return {
            "source": {
                "id": contract_id,
                "contract_no": contract["contract_no"],
                "title": contract["title"],
            },
            "relations": formatted_relations,
        }

    # ══════════════════════════════════════════════════════════
    # 生成合同文档
    # ══════════════════════════════════════════════════════════

    def generate_docx(self, contract_id: int, template_path: str = None,
                      output_path: str = None) -> str:
        """生成合同 Word 文档。

        Args:
            contract_id: 合同 ID
            template_path: 模板路径（可选）
            output_path: 输出路径（可选）

        Returns:
            生成的文件路径
        """
        from .docx_generator import ContractDocxGenerator

        contract = self.get_contract(contract_id)
        if not contract:
            raise ValueError(f"合同 {contract_id} 不存在")

        generator = ContractDocxGenerator()
        return generator.generate(contract, template_path, output_path)

    # ══════════════════════════════════════════════════════════
    # 软删除
    # ══════════════════════════════════════════════════════════

    def soft_delete(self, contract_id: int, operator: str = "") -> dict:
        """软删除合同。

        Raises:
            PermissionError: 无 cr_delete 权限（当已设置角色时）
        """
        if self._current_roles:
            self._require_permission("cr_delete")
        conn = _db.get_connection(self.db_path)
        try:
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE cr_contracts SET deleted_at = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                (now, now, operator, contract_id),
            )
            self._write_audit(conn, contract_id, "DELETE", "deleted_at",
                              "", now, operator)
            conn.commit()
            return {"id": contract_id, "deleted_at": now}
        finally:
            conn.close()

    # ══════════════════════════════════════════════════════════
    # 内部工具
    # ══════════════════════════════════════════════════════════

    def _generate_contract_no(self, conn) -> str:
        """生成合同编号：CR-YYYYMMDD-XXXX。"""
        prefix = f"CR-{datetime.now().strftime('%Y%m%d')}-"
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM cr_contracts WHERE contract_no LIKE ?",
            (f"{prefix}%",),
        ).fetchone()
        seq = (row["n"] or 0) + 1
        return f"{prefix}{seq:04d}"

    @staticmethod
    def _write_audit(conn, contract_id: int, operation: str,
                     field_name: str, old_value: str, new_value: str,
                     operator: str) -> None:
        """写入审计追踪。"""
        conn.execute(
            """INSERT INTO cr_audit_trail
               (contract_id, operation, field_name, old_value, new_value, operator, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (contract_id, operation, field_name, str(old_value), str(new_value),
             operator, datetime.now().isoformat()),
        )

    # ══════════════════════════════════════════════════════════
    # 合同关系管理
    # ══════════════════════════════════════════════════════════

    def add_relation(self, source_contract_id: int, target_contract_id: int,
                     relation_type: str, operator: str = "",
                     match_rule: str = "manual") -> dict:
        """添加合同关系。

        Args:
            source_contract_id: 源合同 ID
            target_contract_id: 目标合同 ID
            relation_type: 关系类型（master_slave / related / supplementary / ...）
            operator: 操作人
            match_rule: 匹配规则

        Returns:
            {"relation_id": int}
        """
        rel_id = self.engine.add_relation(
            source_contract_id, target_contract_id, relation_type, match_rule
        )
        # 写审计（给源合同）
        conn = _db.get_connection(self.db_path)
        try:
            self._write_audit(
                conn, source_contract_id, "ADD_RELATION",
                "relation", f"{relation_type}:{target_contract_id}",
                f"relation_id={rel_id}", operator,
            )
            conn.commit()
        finally:
            conn.close()
        return {"relation_id": rel_id}

    def remove_relation(self, relation_id: int, operator: str = "") -> bool:
        """删除合同关系。

        Args:
            relation_id: 关系 ID
            operator: 操作人

        Returns:
            True = 删除成功
        """
        return self.engine.remove_relation(relation_id)

    def list_relations(self, contract_id: int,
                       relation_type: str = None) -> list[dict]:
        """列出合同的所有关系（双向）。"""
        return self.engine.list_relations(contract_id, relation_type)

    def get_contract_tree(self, contract_id: int,
                          relation_type: str = None,
                          max_depth: int = 5) -> dict:
        """获取合同关系树。"""
        return self.engine.get_contract_tree(contract_id, relation_type, max_depth)

    # ══════════════════════════════════════════════════════════
    # 合同导出（Excel）
    # ══════════════════════════════════════════════════════════

    def export(self, filters: dict = None, out_path: Optional[Path] = None) -> Path:
        """导出合同列表为 Excel。

        Raises:
            PermissionError: 无 cr_export 权限（当已设置角色时）

        导出字段：合同号、合同名称、客户、金额、签约日期、生效日期、
                  合同类型、状态、实施负责人、实施状态

        Args:
            filters: 过滤条件（同 list_contracts）
            out_path: 输出路径，默认自动生成

        Returns:
            导出文件路径
        """
        # RBAC
        if self._current_roles:
            self._require_permission("cr_export")

        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
        from bdms.core.paths import output_path

        # 获取数据（不脱敏，导出完整数据）
        result = self.list_contracts(filters=filters, page_size=10000, mask=False)
        items = result["items"]

        wb = Workbook()
        ws = wb.active
        ws.title = "合同列表"

        # 表头
        headers = [
            "合同号", "合同名称", "客户", "金额",
            "签约日期", "生效日期", "合同类型", "状态",
            "实施负责人", "实施状态",
        ]
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="305496", end_color="305496", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            thin = Side(border_style="thin", color="B4B4B4")
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

        ws.row_dimensions[1].height = 28

        # 状态和实施状态的中文映射
        status_labels = {
            "draft": "起草",
            "review1": "一级审批",
            "review2": "二级审批",
            "review3": "三级审批",
            "review4": "四级审批",
            "approved": "审批通过",
            "signed": "已签署",
            "archived": "已归档",
            "rejected": "已驳回",
        }
        type_labels = {
            "software_license": "软件授权",
            "service": "服务合同",
            "framework": "框架协议",
            "nda": "保密协议",
        }
        impl_status_labels = {
            "not_started": "未开始",
            "in_progress": "实施中",
            "completed": "已完成",
            "suspended": "暂停",
            "cancelled": "取消",
        }

        # 数据行
        for row_idx, item in enumerate(items, 2):
            values = [
                item.get("contract_no", ""),
                item.get("title", ""),
                item.get("party_b", ""),      # 客户 = 乙方
                item.get("amount", 0),
                item.get("signed_date", ""),
                item.get("effective_date", ""),
                type_labels.get(item.get("contract_type", ""), item.get("contract_type", "")),
                status_labels.get(item.get("status", ""), item.get("status", "")),
                item.get("impl_owner", ""),
                impl_status_labels.get(item.get("impl_status", ""), item.get("impl_status", "")),
            ]
            for col_idx, val in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = Font(name="微软雅黑", size=10)
                thin = Side(border_style="thin", color="B4B4B4")
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if col_idx == 4:  # 金额列
                    cell.number_format = "#,##0.00"

        # 自动列宽
        col_widths = [22, 30, 25, 15, 15, 15, 15, 12, 15, 12]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

        if out_path:
            target = Path(out_path)
        else:
            target = output_path("contract_export.xlsx")

        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)
        return target
