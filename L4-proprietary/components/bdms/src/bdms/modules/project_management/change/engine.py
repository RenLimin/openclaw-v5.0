# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ChangeManagementEngine — 变更管理引擎。

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md §4.4（ch_change_requests）。
状态流: draft → submitted → assessing → approved/rejected → executing → completed/cancelled
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bdms.core.db import get_connection
from bdms.modules.base import BaseEngine, NotFoundError, ValidationError


class ChangeManagementEngine(BaseEngine):
    """变更管理引擎：变更请求 → 评估 → 审批 → 执行。"""

    table_name = "ch_change_requests"
    soft_delete = True

    VALID_TRANSITIONS = {
        "draft": {"submitted", "cancelled"},
        "submitted": {"assessing", "cancelled"},
        "assessing": {"approved", "rejected", "cancelled"},
        "approved": {"executing", "cancelled"},
        "rejected": set(),
        "executing": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }

    VALID_CHANGE_TYPES = {"scope", "schedule", "cost", "resource", "quality"}

    # ========================================================
    # 变更请求 CRUD
    # ========================================================

    def create_change_request(
        self,
        project_id: int,
        change_type: str,
        title: str,
        description: str = "",
        reason: str = "",
        proposed_changes: str = "",
        impact_delivery_days: int = 0,
        impact_cost_delta: float = 0.0,
        impact_revenue_delta: float = 0.0,
        submitted_by: str = "system",
    ) -> int:
        """创建变更请求（直接 submitted 状态）。"""
        if not title or not title.strip():
            raise ValidationError("title is required")
        if change_type not in self.VALID_CHANGE_TYPES:
            raise ValidationError(
                f"Invalid change_type: {change_type}. Must be one of {self.VALID_CHANGE_TYPES}"
            )

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO ch_change_requests
                   (project_id, change_type, title, description, reason, proposed_changes,
                    impact_delivery_days, impact_cost_delta, impact_revenue_delta,
                    status, submitted_by, submitted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?, ?)""",
                (project_id, change_type, title.strip(), description, reason,
                 proposed_changes, impact_delivery_days, impact_cost_delta,
                 impact_revenue_delta, submitted_by, datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_change_request(self, change_id: int) -> Optional[Dict[str, Any]]:
        """获取变更请求详情。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM ch_change_requests WHERE id = ? AND deleted_at IS NULL",
                (change_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_change_requests(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        change_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """查询变更请求列表。"""
        conditions = ["deleted_at IS NULL"]
        params: list = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if change_type:
            conditions.append("change_type = ?")
            params.append(change_type)

        where = " AND ".join(conditions)
        conn = get_connection(self.db_path)
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM ch_change_requests WHERE {where}", params
            ).fetchone()[0]
            offset = (max(page, 1) - 1) * page_size
            rows = conn.execute(
                f"SELECT * FROM ch_change_requests WHERE {where} "
                f"ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
            return [dict(r) for r in rows], total
        finally:
            conn.close()

    # ========================================================
    # 变更流程（评估 → 审批 → 执行）
    # ========================================================

    def assess_change(self, change_id: int, assessor: str, note: str = "") -> None:
        """评估变更（submitted → assessing）。"""
        self._transition(change_id, "assessing", assessor, note)

    def approve_change(self, change_id: int, approver: str, note: str = "") -> None:
        """审批通过（assessing → approved）。"""
        conn = get_connection(self.db_path)
        try:
            self._transition(change_id, "approved", approver, note)
            conn.execute(
                "UPDATE ch_change_requests SET approved_by = ?, approved_at = ? WHERE id = ?",
                (approver, datetime.now().isoformat(), change_id),
            )
            conn.commit()
        finally:
            conn.close()

    def reject_change(self, change_id: int, approver: str, note: str = "") -> None:
        """拒绝变更（assessing → rejected）。"""
        self._transition(change_id, "rejected", approver, note)

    def execute_change(self, change_id: int, operator: str = "system") -> None:
        """执行变更（approved → executing → completed）。"""
        conn = get_connection(self.db_path)
        try:
            self._transition(change_id, "executing", operator, "开始执行")
            self._transition(change_id, "completed", operator, "执行完成")
            conn.execute(
                "UPDATE ch_change_requests SET executed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), change_id),
            )
            conn.commit()
        finally:
            conn.close()

    def cancel_change(self, change_id: int, operator: str, reason: str = "") -> None:
        """取消变更（非终态 → cancelled）。"""
        self._transition(change_id, "cancelled", operator, reason)

    def get_change_log(self, project_id: int) -> List[Dict[str, Any]]:
        """获取项目变更日志。"""
        changes, _ = self.list_change_requests(project_id=project_id, page_size=10000)
        return changes

    # ========================================================
    # BaseEngine 抽象方法实现（CRUD 型）
    # ========================================================

    def compute(self, month: str) -> Dict[str, Any]:
        conn = get_connection(self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM ch_change_requests WHERE deleted_at IS NULL"
            ).fetchone()[0]
            return {"total_changes": n, "month": month}
        finally:
            conn.close()

    def persist(self, month: str, data: Dict[str, Any], overwrite: bool = True) -> Dict[str, int]:
        return {"inserted": 0, "updated": 0, "deleted": 0}

    def load(self, month: str) -> Dict[str, Any]:
        return self.compute(month)

    def has_data(self, month: str) -> bool:
        conn = get_connection(self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM ch_change_requests WHERE deleted_at IS NULL"
            ).fetchone()[0]
            return n > 0
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _transition(self, change_id: int, to_status: str,
                    operator: str, note: str = "") -> None:
        """状态转换（含合法性校验 + commit）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM ch_change_requests WHERE id = ? AND deleted_at IS NULL",
                (change_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"变更请求 {change_id} 不存在")

            current = row["status"]
            if current == to_status:
                return  # 幂等
            if to_status not in self.VALID_TRANSITIONS.get(current, set()):
                raise ValidationError(
                    f"非法状态转换: {current} → {to_status}"
                )

            conn.execute(
                "UPDATE ch_change_requests SET status = ?, updated_at = ? WHERE id = ?",
                (to_status, datetime.now().isoformat(), change_id),
            )
            conn.commit()
        finally:
            conn.close()
