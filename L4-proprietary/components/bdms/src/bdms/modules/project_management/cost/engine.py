# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""CostEngine — 成本核算引擎（工时 + 设备 + 差旅）。

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md §7.1。
成本计算规则：
- 工时成本 = SUM(approved_hours × staff_rate)，仅 approved 状态计入
- 设备成本 = SUM(total_cost)
- 差旅成本 = SUM(amount)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from bdms.core.db import get_connection
from bdms.modules.base import BaseEngine, NotFoundError, ValidationError


class CostEngine(BaseEngine):
    """成本核算引擎：工时记录 + 人员单价 + 设备使用 + 差旅费用 + 成本汇总。"""

    table_name = "ct_timesheets"
    soft_delete = True

    # ========================================================
    # 工时记录（§7.1.1 ~ 7.1.2）
    # ========================================================

    def submit_timesheet(
        self,
        project_id: int,
        person_id: str,
        work_date: str,
        hours: float,
        work_type: str = "",
        description: str = "",
        submitted_by: str = "system",
    ) -> int:
        """提交工时记录（幂等：同项目+人+日期+类型的 pending 记录更新 hours）。

        Raises:
            ValidationError: hours ≤ 0 或 > 24，或缺少必填字段
        """
        if not person_id:
            raise ValidationError("person_id is required")
        if not work_date:
            raise ValidationError("work_date is required")
        if not (0 < hours <= 24):
            raise ValidationError(f"hours must be in (0, 24], got {hours}")

        conn = get_connection(self.db_path)
        try:
            # 幂等：更新已有 pending 记录
            existing = conn.execute(
                """SELECT id FROM ct_timesheets
                   WHERE project_id = ? AND person_id = ? AND work_date = ?
                     AND work_type = ? AND status = 'pending' AND deleted_at IS NULL""",
                (project_id, person_id, work_date, work_type),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE ct_timesheets SET hours = ?, description = ? WHERE id = ?",
                    (hours, description, existing["id"]),
                )
                conn.commit()
                return existing["id"]

            cur = conn.execute(
                """INSERT INTO ct_timesheets
                   (project_id, person_id, work_date, hours, work_type, description,
                    status, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (project_id, person_id, work_date, hours, work_type, description, submitted_by),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def approve_timesheet(
        self, timesheet_id: int, approver: str, approved: bool, comment: str = ""
    ) -> None:
        """审批工时记录（pending → approved/rejected）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM ct_timesheets WHERE id = ? AND deleted_at IS NULL",
                (timesheet_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"工时记录 {timesheet_id} 不存在")
            if row["status"] != "pending":
                raise ValidationError(
                    f"工时记录状态为 {row['status']}，只有 pending 状态可审批"
                )
            conn.execute(
                """UPDATE ct_timesheets
                   SET status = ?, approver = ?, approved_at = ?
                   WHERE id = ?""",
                ("approved" if approved else "rejected", approver,
                 datetime.now().isoformat(), timesheet_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_timesheets(
        self,
        project_id: Optional[int] = None,
        person_id: Optional[str] = None,
        status: Optional[str] = None,
        month: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询工时记录。month 格式 YYYYMM。"""
        conditions = ["deleted_at IS NULL"]
        params: list = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if person_id:
            conditions.append("person_id = ?")
            params.append(person_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if month:
            conditions.append("substr(work_date, 1, 7) = ?")
            params.append(f"{month[:4]}-{month[4:6]}")

        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM ct_timesheets WHERE " + " AND ".join(conditions)
                + " ORDER BY work_date DESC, id DESC",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ========================================================
    # 人员单价（§7.1.3 ~ 7.1.4）
    # ========================================================

    def set_staff_rate(
        self,
        person_name: str,
        rate: float,
        role: str = "",
        currency: str = "CNY",
        effective_date: Optional[str] = None,
    ) -> int:
        """设置人员工时单价（元/小时）。"""
        if not person_name:
            raise ValidationError("person_name is required")
        if rate < 0:
            raise ValidationError(f"rate must be >= 0, got {rate}")

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO ct_staff_rates
                   (person_name, role, rate, currency, effective_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (person_name, role, rate, currency,
                 effective_date or date.today().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_staff_rate(self, person_name: str, currency: str = "CNY") -> float:
        """获取人员工时单价（最新生效日期的）。找不到返回 0。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                """SELECT rate FROM ct_staff_rates
                   WHERE person_name = ? AND currency = ? AND deleted_at IS NULL
                   ORDER BY effective_date DESC, id DESC LIMIT 1""",
                (person_name, currency),
            ).fetchone()
            return float(row["rate"]) if row else 0.0
        finally:
            conn.close()

    # ========================================================
    # 设备使用（§7.1.5）
    # ========================================================

    def record_device_usage(
        self,
        project_id: int,
        device_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        cost_per_day: float = 0.0,
        total_cost: float = 0.0,
    ) -> int:
        """登记设备使用记录。"""
        if not device_name:
            raise ValidationError("device_name is required")
        # 未显式给 total_cost 时按天数 × 日租金计算
        if total_cost == 0 and cost_per_day > 0 and start_date and end_date:
            days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1
            total_cost = days * cost_per_day

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO ct_device_usage
                   (project_id, device_name, start_date, end_date,
                    cost_per_day, total_cost, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'in_use')""",
                (project_id, device_name, start_date, end_date, cost_per_day, total_cost),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def return_device(self, usage_id: int) -> None:
        """设备归还（in_use → returned）。"""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE ct_device_usage SET status = 'returned' WHERE id = ?",
                (usage_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 差旅费用（§7.1.6）
    # ========================================================

    def add_travel_cost(
        self,
        project_id: int,
        employee_name: str,
        amount: float,
        travel_date: Optional[str] = None,
        cost_type: str = "",
        description: str = "",
    ) -> int:
        """添加差旅费用记录。"""
        if not employee_name:
            raise ValidationError("employee_name is required")
        if amount < 0:
            raise ValidationError(f"amount must be >= 0, got {amount}")

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO ct_travel_costs
                   (project_id, employee_name, travel_date, cost_type, amount, description)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (project_id, employee_name,
                 travel_date or date.today().isoformat(), cost_type, amount, description),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def list_travel_costs(self, project_id: int) -> List[Dict[str, Any]]:
        """查询差旅费用。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM ct_travel_costs WHERE project_id = ? ORDER BY travel_date",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ========================================================
    # 成本汇总（§7.1.7）
    # ========================================================

    def get_cost_summary(self, project_id: int) -> Dict[str, Any]:
        """获取项目成本汇总（按人 + 按月）。

        工时成本只计 approved 状态。
        """
        conn = get_connection(self.db_path)
        try:
            # 工时（approved only）× 费率
            sheets = conn.execute(
                """SELECT person_id, work_date, hours FROM ct_timesheets
                   WHERE project_id = ? AND status = 'approved' AND deleted_at IS NULL""",
                (project_id,),
            ).fetchall()

            labor_cost = 0.0
            by_person: Dict[str, Dict[str, float]] = {}
            labor_by_month: Dict[str, float] = {}
            for s in sheets:
                rate = self.get_staff_rate(s["person_id"])
                cost = s["hours"] * rate
                labor_cost += cost
                p = by_person.setdefault(
                    s["person_id"], {"person_id": s["person_id"], "hours": 0.0,
                                     "rate": rate, "cost": 0.0}
                )
                p["hours"] += s["hours"]
                p["cost"] += cost
                m = str(s["work_date"])[:7].replace("-", "")
                labor_by_month[m] = labor_by_month.get(m, 0.0) + cost

            # 设备
            devices = conn.execute(
                "SELECT total_cost, start_date FROM ct_device_usage WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            device_cost = sum(float(d["total_cost"] or 0) for d in devices)
            device_by_month: Dict[str, float] = {}
            for d in devices:
                m = str(d["start_date"] or "")[:7].replace("-", "")
                device_by_month[m] = device_by_month.get(m, 0.0) + float(d["total_cost"] or 0)

            # 差旅
            travels = conn.execute(
                "SELECT amount, travel_date FROM ct_travel_costs WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            travel_cost = sum(float(t["amount"] or 0) for t in travels)
            travel_by_month: Dict[str, float] = {}
            for t in travels:
                m = str(t["travel_date"] or "")[:7].replace("-", "")
                travel_by_month[m] = travel_by_month.get(m, 0.0) + float(t["amount"] or 0)

            # 按月合并
            all_months = sorted(set(labor_by_month) | set(device_by_month) | set(travel_by_month))
            by_month = [
                {
                    "month": m,
                    "labor_cost": round(labor_by_month.get(m, 0), 2),
                    "device_cost": round(device_by_month.get(m, 0), 2),
                    "travel_cost": round(travel_by_month.get(m, 0), 2),
                    "total": round(
                        labor_by_month.get(m, 0)
                        + device_by_month.get(m, 0)
                        + travel_by_month.get(m, 0),
                        2,
                    ),
                }
                for m in all_months
            ]

            return {
                "total": round(labor_cost + device_cost + travel_cost, 2),
                "labor_cost": round(labor_cost, 2),
                "device_cost": round(device_cost, 2),
                "travel_cost": round(travel_cost, 2),
                "total_hours": round(sum(s["hours"] for s in sheets), 2),
                "by_person": [
                    {
                        "person_id": p["person_id"],
                        "hours": round(p["hours"], 2),
                        "rate": p["rate"],
                        "cost": round(p["cost"], 2),
                    }
                    for p in by_person.values()
                ],
                "by_month": by_month,
            }
        finally:
            conn.close()

    # ========================================================
    # BaseEngine 抽象方法实现（CRUD 型）
    # ========================================================

    def compute(self, month: str) -> Dict[str, Any]:
        """按月统计成本指标。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM ct_timesheets WHERE deleted_at IS NULL"
            ).fetchone()
            return {"total_timesheets": row["n"], "month": month}
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
                "SELECT COUNT(*) FROM ct_timesheets WHERE deleted_at IS NULL"
            ).fetchone()[0]
            return n > 0
        finally:
            conn.close()
