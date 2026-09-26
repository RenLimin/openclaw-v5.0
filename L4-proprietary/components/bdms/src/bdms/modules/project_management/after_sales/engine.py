# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""AfterSalesEngine — 售后管理引擎。

职责：
- 售后工单 CRUD + 状态机
- SLA 计算（响应/解决时限）
- 维保合同管理
- 工单历史记录
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from bdms.core.db import get_connection, transaction
from bdms.modules.base import BaseEngine, NotFoundError, StateTransitionError, ValidationError

from ..models import (
    TicketState,
    TicketPriority,
    ServiceLevel,
    SLA_HOURS,
    is_valid_ticket_transition,
)


class AfterSalesEngine(BaseEngine):
    """售后管理引擎：工单 + 维保合同 + SLA。"""

    table_name = "as_tickets"
    soft_delete = True

    # ========================================================
    # 工单创建
    # ========================================================

    def create_ticket(
        self,
        title: str,
        description: str = "",
        source: str = "other",
        project_id: Optional[int] = None,
        customer_name: str = "",
        customer_contact: str = "",
        customer_phone: str = "",
        priority: str = "medium",
        service_level: str = "silver",
        created_by: str = "system",
    ) -> int:
        """创建售后工单。

        自动计算 SLA 响应/解决截止时间。
        初始状态: open。

        Returns:
            ticket_id
        """
        if not title:
            raise ValidationError("title is required")

        # 校验优先级
        valid_priorities = {"low", "medium", "high", "critical"}
        if priority not in valid_priorities:
            raise ValidationError(f"Invalid priority: {priority}. Must be one of {valid_priorities}")

        # 校验服务等级
        valid_levels = {"gold", "silver", "bronze"}
        if service_level not in valid_levels:
            raise ValidationError(f"Invalid service_level: {service_level}. Must be one of {valid_levels}")

        # 计算实际服务等级（CRITICAL 优先级提升一级）
        effective_level = service_level
        if priority == "critical":
            level_up = {"bronze": "silver", "silver": "gold", "gold": "gold"}
            effective_level = level_up.get(service_level, service_level)

        # 自动生成工单号
        ticket_no = self._generate_ticket_no()

        # 计算 SLA 截止时间
        now = datetime.now()
        sla_hours = SLA_HOURS[effective_level]
        response_deadline = now + timedelta(hours=sla_hours["response"])
        resolution_deadline = now + timedelta(hours=sla_hours["resolution"])

        data = {
            "ticket_no": ticket_no,
            "title": title,
            "description": description,
            "state": TicketState.OPEN.value,
            "priority": priority,
            "service_level": service_level,
            "source": source,
            "project_id": project_id,
            "customer_name": customer_name,
            "customer_contact": customer_contact,
            "customer_phone": customer_phone,
            "created_by": created_by,
            "response_deadline": response_deadline.isoformat(),
            "resolution_deadline": resolution_deadline.isoformat(),
            "updated_by": created_by,
        }

        ticket_id = self._insert(data)

        # 记录历史
        self._add_history(ticket_id, None, "open", "create", "工单创建", created_by)

        return ticket_id

    def get_ticket(self, ticket_id: int) -> Dict[str, Any]:
        """获取工单详情（含历史记录）。"""
        ticket = self._get_by_id_or_raise(ticket_id)
        history = self._get_ticket_history(ticket_id)
        return {
            "ticket": ticket,
            "history": history,
            "sla": self._calculate_sla_status(ticket),
        }

    def list_tickets(
        self,
        state: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        project_id: Optional[int] = None,
        customer_keyword: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """工单列表查询。"""
        conn = get_connection(self.db_path)
        conditions = ["deleted_at IS NULL"]
        params: List[Any] = []

        if state:
            conditions.append("state = ?")
            params.append(state)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if assignee:
            conditions.append("assignee = ?")
            params.append(assignee)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if customer_keyword:
            conditions.append("(customer_name LIKE ? OR customer_contact LIKE ?)")
            like = f"%{customer_keyword}%"
            params.extend([like, like])
        if date_from:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at <= ?")
            params.append(date_to)

        where = "WHERE " + " AND ".join(conditions)

        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM as_tickets {where}", params
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM as_tickets {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        ).fetchall()

        return [dict(r) for r in rows], total

    def update_ticket(self, ticket_id: int, updated_by: str = "system", **kwargs) -> None:
        """更新工单基本信息（不包含状态变更）。"""
        # 禁止直接改状态
        kwargs.pop("state", None)
        for key in ("id", "ticket_no", "created_by", "created_at"):
            kwargs.pop(key, None)

        if not kwargs:
            return

        self._get_by_id_or_raise(ticket_id)
        kwargs["updated_by"] = updated_by
        kwargs["updated_at"] = datetime.now().isoformat()
        self._update(ticket_id, kwargs)

    def delete_ticket(self, ticket_id: int, operator: str = "system") -> None:
        """软删除工单。"""
        self._get_by_id_or_raise(ticket_id)
        self._soft_delete(ticket_id, operator)

    # ========================================================
    # 工单状态机
    # ========================================================

    def assign_ticket(
        self,
        ticket_id: int,
        assignee: str,
        assigner: str = "system",
        comment: str = "",
    ) -> None:
        """分派工单：open → assigned。"""
        if not assignee:
            raise ValidationError("assignee is required")

        ticket = self._get_by_id_or_raise(ticket_id)
        from_state = ticket["state"]

        # 幂等：已分派给同一人
        if from_state == "assigned" and ticket["assignee"] == assignee:
            return

        target_state = "assigned"
        if not is_valid_ticket_transition(from_state, target_state):
            raise StateTransitionError(
                f"Cannot assign ticket from state '{from_state}'. "
                f"Allowed transitions: {from_state} -> assigned"
            )

        with transaction(self.db_path):
            self._update(ticket_id, {
                "state": target_state,
                "assignee": assignee,
                "updated_by": assigner,
                "updated_at": datetime.now().isoformat(),
            })
            self._add_history(
                ticket_id, from_state, target_state,
                "assign", f"分派给 {assignee}。{comment}", assigner
            )

    def start_ticket(self, ticket_id: int, operator: str) -> None:
        """开始处理：assigned → in_progress。记录响应时间。"""
        ticket = self._get_by_id_or_raise(ticket_id)
        from_state = ticket["state"]

        if from_state == "in_progress":
            return  # 幂等

        target_state = "in_progress"
        if not is_valid_ticket_transition(from_state, target_state):
            raise StateTransitionError(
                f"Cannot start ticket from state '{from_state}'."
            )

        now = datetime.now().isoformat()
        with transaction(self.db_path):
            self._update(ticket_id, {
                "state": target_state,
                "response_at": now,
                "updated_by": operator,
                "updated_at": now,
            })
            self._add_history(
                ticket_id, from_state, target_state,
                "start", "开始处理", operator
            )

    def resolve_ticket(
        self,
        ticket_id: int,
        resolver: str,
        resolution: str,
        resolution_type: str = "fixed",
    ) -> None:
        """解决工单：in_progress → resolved。"""
        if not resolution:
            raise ValidationError("resolution is required")

        valid_types = {"fixed", "workaround", "duplicate", "wont_fix"}
        if resolution_type not in valid_types:
            raise ValidationError(
                f"Invalid resolution_type: {resolution_type}. Must be one of {valid_types}"
            )

        ticket = self._get_by_id_or_raise(ticket_id)
        from_state = ticket["state"]

        if from_state == "resolved":
            return  # 幂等

        target_state = "resolved"
        if not is_valid_ticket_transition(from_state, target_state):
            raise StateTransitionError(
                f"Cannot resolve ticket from state '{from_state}'."
            )

        now = datetime.now().isoformat()
        with transaction(self.db_path):
            self._update(ticket_id, {
                "state": target_state,
                "resolution": resolution,
                "resolution_type": resolution_type,
                "resolved_at": now,
                "updated_by": resolver,
                "updated_at": now,
            })
            self._add_history(
                ticket_id, from_state, target_state,
                "resolve", f"解决方案：{resolution}", resolver
            )

    def close_ticket(
        self,
        ticket_id: int,
        closer: str,
        close_note: str = "",
    ) -> None:
        """关闭工单：resolved → closed。"""
        ticket = self._get_by_id_or_raise(ticket_id)
        from_state = ticket["state"]

        if from_state == "closed":
            return  # 幂等

        target_state = "closed"
        if not is_valid_ticket_transition(from_state, target_state):
            raise StateTransitionError(
                f"Cannot close ticket from state '{from_state}'."
            )

        now = datetime.now().isoformat()
        with transaction(self.db_path):
            self._update(ticket_id, {
                "state": target_state,
                "close_note": close_note,
                "closed_at": now,
                "updated_by": closer,
                "updated_at": now,
            })
            self._add_history(
                ticket_id, from_state, target_state,
                "close", f"关闭：{close_note}", closer
            )

    def reopen_ticket(
        self,
        ticket_id: int,
        reopener: str,
        reason: str,
    ) -> None:
        """重新打开工单：resolved/closed → in_progress。"""
        if not reason:
            raise ValidationError("reopen reason is required")

        ticket = self._get_by_id_or_raise(ticket_id)
        from_state = ticket["state"]

        target_state = "in_progress"
        if not is_valid_ticket_transition(from_state, target_state):
            raise StateTransitionError(
                f"Cannot reopen ticket from state '{from_state}'."
            )

        now = datetime.now().isoformat()
        with transaction(self.db_path):
            self._update(ticket_id, {
                "state": target_state,
                "closed_at": None,
                "updated_by": reopener,
                "updated_at": now,
            })
            self._add_history(
                ticket_id, from_state, target_state,
                "reopen", f"重新打开：{reason}", reopener
            )

    # ========================================================
    # SLA 计算
    # ========================================================

    def _calculate_sla_status(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """计算工单 SLA 状态。

        Returns:
            {
                "response_sla_met": bool,
                "response_sla_hours": float,
                "response_hours_used": float,
                "resolution_sla_met": bool,
                "resolution_sla_hours": float,
                "resolution_hours_used": float,
                "is_overdue_response": bool,
                "is_overdue_resolution": bool,
            }
        """
        now = datetime.now()
        created_at = datetime.fromisoformat(ticket["created_at"])
        level = ticket.get("service_level", "silver")
        sla_hours = SLA_HOURS.get(level, SLA_HOURS["silver"])

        # 响应 SLA
        response_hours_used = 0.0
        response_sla_met = True
        is_overdue_response = False

        if ticket.get("response_at"):
            response_at = datetime.fromisoformat(ticket["response_at"])
            response_hours_used = (response_at - created_at).total_seconds() / 3600
            response_sla_met = response_hours_used <= sla_hours["response"]
        else:
            response_hours_used = (now - created_at).total_seconds() / 3600
            is_overdue_response = response_hours_used > sla_hours["response"]

        # 解决 SLA
        resolution_hours_used = 0.0
        resolution_sla_met = True
        is_overdue_resolution = False

        if ticket.get("resolved_at"):
            resolved_at = datetime.fromisoformat(ticket["resolved_at"])
            resolution_hours_used = (resolved_at - created_at).total_seconds() / 3600
            resolution_sla_met = resolution_hours_used <= sla_hours["resolution"]
        elif ticket["state"] not in ("closed", "resolved"):
            resolution_hours_used = (now - created_at).total_seconds() / 3600
            is_overdue_resolution = resolution_hours_used > sla_hours["resolution"]

        return {
            "response_sla_met": response_sla_met,
            "response_sla_hours": sla_hours["response"],
            "response_hours_used": round(response_hours_used, 2),
            "resolution_sla_met": resolution_sla_met,
            "resolution_sla_hours": sla_hours["resolution"],
            "resolution_hours_used": round(resolution_hours_used, 2),
            "is_overdue_response": is_overdue_response,
            "is_overdue_resolution": is_overdue_resolution,
        }

    def get_ticket_summary(self, project_id: Optional[int] = None) -> Dict[str, Any]:
        """工单状态汇总（结项前置检查用）。

        Returns:
            {"total", "open", "assigned", "in_progress", "resolved", "closed",
             "overdue_resolution"}
        """
        conn = get_connection(self.db_path)
        try:
            conditions = ["deleted_at IS NULL"]
            params: List[Any] = []
            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)
            where = " AND ".join(conditions)

            rows = conn.execute(
                f"SELECT state, resolution_deadline, resolved_at FROM as_tickets WHERE {where}",
                params,
            ).fetchall()

            by_state: Dict[str, int] = {}
            overdue = 0
            now = datetime.now().isoformat()
            for r in rows:
                by_state[r["state"]] = by_state.get(r["state"], 0) + 1
                if (r["state"] not in ("closed",) and r["resolution_deadline"]
                        and r["resolution_deadline"] < now):
                    overdue += 1

            return {
                "total": len(rows),
                "open": by_state.get("open", 0),
                "assigned": by_state.get("assigned", 0),
                "in_progress": by_state.get("in_progress", 0),
                "resolved": by_state.get("resolved", 0),
                "closed": by_state.get("closed", 0),
                "overdue_resolution": overdue,
            }
        finally:
            conn.close()

    def get_sla_summary(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        service_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """SLA 统计概览。"""
        conn = get_connection(self.db_path)
        conditions = ["deleted_at IS NULL"]
        params: List[Any] = []

        if period_start:
            conditions.append("created_at >= ?")
            params.append(period_start)
        if period_end:
            conditions.append("created_at <= ?")
            params.append(period_end)
        if service_level:
            conditions.append("service_level = ?")
            params.append(service_level)

        where = "WHERE " + " AND ".join(conditions)

        # 总工单数
        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM as_tickets {where}", params
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        if total == 0:
            return {
                "total_tickets": 0,
                "response_sla_rate": 0.0,
                "resolution_sla_rate": 0.0,
                "avg_response_time_hours": 0.0,
                "avg_resolution_time_hours": 0.0,
                "overdue_response": 0,
                "overdue_resolution": 0,
            }

        # 有响应的工单数
        resp_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM as_tickets {where} AND response_at IS NOT NULL",
            params
        ).fetchone()
        total_with_response = resp_row["cnt"] if resp_row else 0

        # 已解决的工单数
        res_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM as_tickets {where} AND resolved_at IS NOT NULL",
            params
        ).fetchone()
        total_resolved = res_row["cnt"] if res_row else 0

        # 计算 SLA 达标（用 SQL 算超时数）
        overdue_resp_row = conn.execute(
            f"""SELECT COUNT(*) as cnt FROM as_tickets {where}
                AND response_at IS NOT NULL
                AND julianday(response_at) - julianday(created_at) >
                    (CASE service_level
                        WHEN 'gold' THEN {SLA_HOURS['gold']['response']}/24.0
                        WHEN 'silver' THEN {SLA_HOURS['silver']['response']}/24.0
                        WHEN 'bronze' THEN {SLA_HOURS['bronze']['response']}/24.0
                        ELSE {SLA_HOURS['silver']['response']}/24.0
                     END)""",
            params
        ).fetchone()
        overdue_response = overdue_resp_row["cnt"] if overdue_resp_row else 0

        overdue_res_row = conn.execute(
            f"""SELECT COUNT(*) as cnt FROM as_tickets {where}
                AND resolved_at IS NOT NULL
                AND julianday(resolved_at) - julianday(created_at) >
                    (CASE service_level
                        WHEN 'gold' THEN {SLA_HOURS['gold']['resolution']}/24.0
                        WHEN 'silver' THEN {SLA_HOURS['silver']['resolution']}/24.0
                        WHEN 'bronze' THEN {SLA_HOURS['bronze']['resolution']}/24.0
                        ELSE {SLA_HOURS['silver']['resolution']}/24.0
                     END)""",
            params
        ).fetchone()
        overdue_resolution = overdue_res_row["cnt"] if overdue_res_row else 0

        # 平均响应/解决时间
        avg_resp_row = conn.execute(
            f"""SELECT AVG((julianday(response_at) - julianday(created_at)) * 24) as avg_hours
                FROM as_tickets {where} AND response_at IS NOT NULL""",
            params
        ).fetchone()
        avg_response = round(float(avg_resp_row["avg_hours"]), 2) if avg_resp_row and avg_resp_row["avg_hours"] else 0.0

        avg_res_row = conn.execute(
            f"""SELECT AVG((julianday(resolved_at) - julianday(created_at)) * 24) as avg_hours
                FROM as_tickets {where} AND resolved_at IS NOT NULL""",
            params
        ).fetchone()
        avg_resolution = round(float(avg_res_row["avg_hours"]), 2) if avg_res_row and avg_res_row["avg_hours"] else 0.0

        response_sla_rate = round((total_with_response - overdue_response) / total_with_response * 100, 2) if total_with_response > 0 else 100.0
        resolution_sla_rate = round((total_resolved - overdue_resolution) / total_resolved * 100, 2) if total_resolved > 0 else 100.0

        return {
            "total_tickets": total,
            "response_sla_rate": response_sla_rate,
            "resolution_sla_rate": resolution_sla_rate,
            "avg_response_time_hours": avg_response,
            "avg_resolution_time_hours": avg_resolution,
            "overdue_response": overdue_response,
            "overdue_resolution": overdue_resolution,
        }

    # ========================================================
    # 维保合同
    # ========================================================

    def create_warranty_contract(
        self,
        project_id: int,
        warranty_start: Optional[str] = None,
        warranty_end: Optional[str] = None,
        warranty_period_months: int = 12,
        service_level: str = "silver",
        remaining_tickets: int = 0,
        customer_contact: str = "",
        customer_phone: str = "",
    ) -> int:
        """创建维保合同。"""
        conn = get_connection(self.db_path)

        today = date.today()
        start = warranty_start or today.isoformat()

        if not warranty_end:
            # 计算结束日期
            start_date = date.fromisoformat(start)
            end_year = start_date.year
            end_month = start_date.month + warranty_period_months
            while end_month > 12:
                end_month -= 12
                end_year += 1
            end_day = start_date.day
            # 处理月末
            try:
                end_date = date(end_year, end_month, end_day)
            except ValueError:
                # 月末溢出（如 1/31 + 1 month = 2/31 -> 2/28）
                if end_month == 2:
                    # 简单处理：设置为28号
                    end_date = date(end_year, 2, 28)
                else:
                    end_date = date(end_year, end_month, end_day - 1)
            end = end_date.isoformat()
        else:
            end = warranty_end

        contract_no = self._generate_warranty_no(project_id)

        cursor = conn.execute(
            """INSERT INTO as_warranty_contracts
               (contract_no, project_id, warranty_start, warranty_end,
                service_level, remaining_tickets, status,
                customer_contact, customer_phone)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
            (contract_no, project_id, start, end, service_level,
             remaining_tickets, customer_contact, customer_phone)
        )
        warranty_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return warranty_id

    def get_warranty_by_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """获取项目的维保合同（active 状态的）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                """SELECT * FROM as_warranty_contracts
                   WHERE project_id = ? AND status = 'active'
                   ORDER BY id DESC LIMIT 1""",
                (project_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _generate_ticket_no(self) -> str:
        """生成工单号：TK-YYYYMMDD-NNNN。"""
        conn = get_connection(self.db_path)
        try:
          today = date.today().strftime("%Y%m%d")
          prefix = f"TK-{today}-"
          row = conn.execute(
              "SELECT COUNT(*) as cnt FROM as_tickets WHERE ticket_no LIKE ?",
              (prefix + "%",)
          ).fetchone()
          seq = (row["cnt"] if row else 0) + 1
          return f"{prefix}{seq:04d}"
        finally:
            conn.close()

    def _generate_warranty_no(self, project_id: int) -> str:
        """生成维保合同号：WC-PROJID-NNN。"""
        conn = get_connection(self.db_path)
        try:
          prefix = f"WC-{project_id}-"
          row = conn.execute(
              "SELECT COUNT(*) as cnt FROM as_warranty_contracts WHERE contract_no LIKE ?",
              (prefix + "%",)
          ).fetchone()
          seq = (row["cnt"] if row else 0) + 1
          return f"{prefix}{seq:03d}"
        finally:
            conn.close()

    def _add_history(
        self,
        ticket_id: int,
        from_state: Optional[str],
        to_state: str,
        action: str,
        comment: str,
        operator: str,
    ) -> None:
        """添加工单历史记录。"""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """INSERT INTO as_ticket_history
                   (ticket_id, from_state, to_state, action, comment, operator)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ticket_id, from_state, to_state, action, comment, operator)
            )
            conn.commit()
        finally:
            conn.close()

    def _get_ticket_history(self, ticket_id: int) -> List[Dict[str, Any]]:
        """获取工单历史记录。"""
        conn = get_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM as_ticket_history WHERE ticket_id = ? ORDER BY id",
            (ticket_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ============================================================
    # BaseEngine 抽象方法实现（CRUD 型引擎，非月度计算）
    # ============================================================

    def compute(self, month: str) -> dict:
        """计算指定月份的统计数据。"""
        conn = get_connection(self.db_path)
        count = conn.execute(
            f"SELECT COUNT(*) FROM {as_tickets} WHERE deleted_at IS NULL"
        ).fetchone()[0]
        return {"total": count, "month": month}

    def persist(self, month: str, data: dict, overwrite: bool = True) -> dict:
        """持久化（CRUD 型不需要，空实现）。"""
        return {"inserted": 0, "updated": 0, "deleted": 0}

    def load(self, month: str) -> dict:
        """加载数据（CRUD 型直接查 DB）。"""
        return self.compute(month)

    def has_data(self, month: str) -> bool:
        """检查是否有数据。"""
        conn = get_connection(self.db_path)
        count = conn.execute(
            f"SELECT COUNT(*) FROM {as_tickets} WHERE deleted_at IS NULL"
        ).fetchone()[0]
        return count > 0
