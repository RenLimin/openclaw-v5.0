# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProfitEngine — 项目利润计算引擎。

对齐 DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md §3.1。
核心公式: profit = revenue - cost; cost = labor + device + travel
成本数据从 pf_* 表读取（v2.1 成本迁移后的新表）。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdms.core import db as _db
from bdms.core.db import get_connection
from bdms.modules.base import BaseEngine, NotFoundError, ValidationError

_PERIOD_RE = re.compile(r"^\d{4}-\d{2}$")


class ProfitEngine(BaseEngine):
    """利润计算引擎（纯计算，无 DB 写入）。"""

    table_name = "pf_profit_snapshot"
    soft_delete = False

    # ========================================================
    # 利润计算（§3.1 compute_profit）
    # ========================================================

    def compute_profit(
        self,
        project_id: int,
        period: str,
        revenue_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """计算项目在某期间的利润。

        period: YYYY-MM（会计期间）
        revenue_override: 收入覆盖值（None 则从 revenue 模块同步/预算估算）
        """
        if not _PERIOD_RE.match(period):
            raise ValidationError(f"period 格式非法: {period}（期望 YYYY-MM）")

        conn = get_connection(self.db_path)
        try:
            project = conn.execute(
                "SELECT * FROM pm_projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if not project:
                raise NotFoundError(f"项目 {project_id} 不存在")

            budget = float(project["budget"] or 0)
            month = period.replace("-", "")

            # 成本（pf_* 新表，approved 工时）
            cost = self._period_cost(conn, project_id, month)

            # 收入
            if revenue_override is not None:
                revenue = float(revenue_override)
            else:
                revenue = self._sync_revenue(conn, project_id, month, budget)

            profit = revenue - cost["total"]
            margin = (profit / revenue) if revenue > 0 else 0.0

            return {
                "project_id": project_id,
                "period": period,
                "revenue": round(revenue, 2),
                "cost": round(cost["total"], 2),
                "profit": round(profit, 2),
                "profit_margin": round(margin, 4),
                "cost_breakdown": {
                    "labor_cost": round(cost["labor"], 2),
                    "device_cost": round(cost["device"], 2),
                    "travel_cost": round(cost["travel"], 2),
                },
                "budget": budget,
                "budget_usage": round(cost["total"] / budget, 4) if budget > 0 else 0.0,
            }
        finally:
            conn.close()

    # ========================================================
    # 成本汇总（§3.1 get_cost_summary）
    # ========================================================

    def get_cost_summary(
        self,
        project_id: int,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取项目成本汇总（pf_* 表口径）。"""
        conn = get_connection(self.db_path)
        try:
            month = period.replace("-", "") if period else None
            sheets = conn.execute(
                "SELECT person_id, work_date, hours FROM pf_timesheet "
                "WHERE project_id = ? AND status = 'approved'"
                + (" AND substr(work_date,1,7) = ?" if month else ""),
                (project_id, month[:4] + "-" + month[4:6]) if month else (project_id,),
            ).fetchall() if month else conn.execute(
                "SELECT person_id, work_date, hours FROM pf_timesheet "
                "WHERE project_id = ? AND status = 'approved'",
                (project_id,),
            ).fetchall()

            labor = 0.0
            by_person: Dict[str, Dict] = {}
            by_month: Dict[str, float] = {}
            total_hours = 0.0
            for s in sheets:
                rate = self._staff_rate(conn, s["person_id"])
                c = s["hours"] * rate
                labor += c
                total_hours += s["hours"]
                p = by_person.setdefault(s["person_id"],
                                         {"person_id": s["person_id"],
                                          "hours": 0.0, "rate": rate, "cost": 0.0})
                p["hours"] += s["hours"]
                p["cost"] += c
                m = str(s["work_date"])[:7].replace("-", "")
                by_month[m] = by_month.get(m, 0.0) + c

            device = conn.execute(
                "SELECT COALESCE(SUM(total_cost), 0) FROM pf_device_usage WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            travel = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM pf_travel_cost WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]

            return {
                "total": round(labor + float(device) + float(travel), 2),
                "labor_cost": round(labor, 2),
                "device_cost": round(float(device), 2),
                "travel_cost": round(float(travel), 2),
                "total_hours": round(total_hours, 2),
                "by_person": [
                    {"person_id": p["person_id"], "hours": round(p["hours"], 2),
                     "rate": p["rate"], "cost": round(p["cost"], 2)}
                    for p in by_person.values()
                ],
                "by_month": [
                    {"month": m, "labor_cost": round(v, 2),
                     "device_cost": 0.0, "travel_cost": 0.0, "total": round(v, 2)}
                    for m, v in sorted(by_month.items())
                ],
            }
        finally:
            conn.close()

    # ========================================================
    # 预算告警（§3.1 check_budget_alert）
    # ========================================================

    def check_budget_alert(
        self,
        project_id: int,
        threshold: float = 0.10,
    ) -> List[Dict[str, Any]]:
        """检查项目成本是否超预算阈值。无异常返回 []。"""
        conn = get_connection(self.db_path)
        try:
            project = conn.execute(
                "SELECT project_name, budget FROM pm_projects "
                "WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if not project:
                raise NotFoundError(f"项目 {project_id} 不存在")

            budget = float(project["budget"] or 0)
            if budget <= 0:
                return []

            summary = self.get_cost_summary(project_id)
            actual = summary["total"]
            over_pct = (actual - budget) / budget

            if over_pct <= 0:
                return []

            level = "critical" if over_pct > threshold else "warning"
            return [{
                "alert_level": level,
                "project_id": project_id,
                "project_name": project["project_name"],
                "budget": budget,
                "actual_cost": actual,
                "over_budget_pct": round(over_pct, 4),
                "message": f"成本超预算 {over_pct*100:.1f}%"
                           f"（预算 {budget:.0f}，实际 {actual:.0f}）",
            }]
        finally:
            conn.close()

    # ========================================================
    # 聚合（§3.1 aggregate_by_department / by_period）
    # ========================================================

    def aggregate_by_department(
        self,
        period: str,
        dept: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """按部门维度聚合利润数据。"""
        conn = get_connection(self.db_path)
        try:
            where = "deleted_at IS NULL"
            params: list = []
            if dept:
                where += " AND dept = ?"
                params.append(dept)
            projects = conn.execute(
                f"SELECT id, dept, project_name FROM pm_projects WHERE {where}",
                params,
            ).fetchall()

            by_dept: Dict[str, Dict] = {}
            for p in projects:
                try:
                    profit = self.compute_profit(p["id"], period)
                except (NotFoundError, ValidationError):
                    continue
                d = by_dept.setdefault(
                    p["dept"] or "未分配",
                    {"dept": p["dept"] or "未分配", "project_count": 0,
                     "total_revenue": 0.0, "total_cost": 0.0, "total_profit": 0.0},
                )
                d["project_count"] += 1
                d["total_revenue"] += profit["revenue"]
                d["total_cost"] += profit["cost"]
                d["total_profit"] += profit["profit"]

            result = []
            for d in by_dept.values():
                d["profit_margin"] = (
                    round(d["total_profit"] / d["total_revenue"], 4)
                    if d["total_revenue"] > 0 else 0.0
                )
                for k in ("total_revenue", "total_cost", "total_profit"):
                    d[k] = round(d[k], 2)
                result.append(d)
            return sorted(result, key=lambda x: x["total_profit"], reverse=True)
        finally:
            conn.close()

    def aggregate_by_period(
        self,
        project_id: int,
        periods: List[str],
    ) -> List[Dict[str, Any]]:
        """按时间维度聚合利润数据。"""
        results = []
        for period in periods:
            try:
                p = self.compute_profit(project_id, period)
                results.append({
                    "period": period,
                    "revenue": p["revenue"],
                    "cost": p["cost"],
                    "profit": p["profit"],
                    "profit_margin": p["profit_margin"],
                })
            except (NotFoundError, ValidationError):
                continue
        return results

    # ========================================================
    # BaseEngine 抽象方法
    # ========================================================

    def compute(self, month: str) -> Dict[str, Any]:
        """按月计算全部项目利润快照。"""
        conn = get_connection(self.db_path)
        try:
            projects = conn.execute(
                "SELECT id FROM pm_projects WHERE deleted_at IS NULL"
            ).fetchall()
            period = f"{month[:4]}-{month[4:6]}" if len(month) == 6 else month
            results = {}
            for p in projects:
                try:
                    results[p["id"]] = self.compute_profit(p["id"], period)
                except (NotFoundError, ValidationError):
                    continue
            return results
        finally:
            conn.close()

    def persist(self, month: str, data: Dict[str, Any], overwrite: bool = True) -> Dict[str, int]:
        """利润快照落盘 pf_profit_snapshot。"""
        conn = get_connection(self.db_path)
        try:
            if overwrite:
                conn.execute(
                    "DELETE FROM pf_profit_snapshot WHERE period = ?", (month,))
            inserted = 0
            for project_id, snapshot in data.items():
                breakdown = snapshot.get("cost_breakdown", {})
                conn.execute(
                    """INSERT INTO pf_profit_snapshot
                       (period, project_id, revenue, cost_labor, cost_device,
                        cost_travel, cost_total, profit, profit_margin,
                        budget, budget_usage, pv, ev)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (month, project_id,
                     snapshot.get("revenue", 0),
                     breakdown.get("labor_cost", 0),
                     breakdown.get("device_cost", 0),
                     breakdown.get("travel_cost", 0),
                     snapshot.get("cost", 0),
                     snapshot.get("profit", 0), snapshot.get("profit_margin", 0),
                     snapshot.get("budget", 0), snapshot.get("budget_usage", 0),
                     snapshot.get("pv"), snapshot.get("ev")),
                )
                inserted += 1
            conn.commit()
            return {"inserted": inserted, "updated": 0, "deleted": 0}
        finally:
            conn.close()

    def load(self, month: str) -> Dict[str, Any]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM pf_profit_snapshot WHERE period = ?",
                (month,),
            ).fetchall()
            return {r["project_id"]: dict(r) for r in rows}
        finally:
            conn.close()

    def has_data(self, month: str) -> bool:
        conn = get_connection(self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM pf_profit_snapshot WHERE period = ?",
                (month,),
            ).fetchone()[0]
            return n > 0
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _period_cost(self, conn, project_id: int, month: str) -> Dict[str, float]:
        """某期间成本（pf_* 表）。"""
        period_prefix = f"{month[:4]}-{month[4:6]}"

        sheets = conn.execute(
            "SELECT person_id, hours FROM pf_timesheet "
            "WHERE project_id = ? AND status = 'approved' "
            "AND substr(work_date, 1, 7) = ?",
            (project_id, period_prefix),
        ).fetchall()
        labor = sum(
            s["hours"] * self._staff_rate(conn, s["person_id"]) for s in sheets
        )

        device = conn.execute(
            "SELECT COALESCE(SUM(total_cost), 0) FROM pf_device_usage "
            "WHERE project_id = ? AND substr(start_date, 1, 7) = ?",
            (project_id, period_prefix),
        ).fetchone()[0]

        travel = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM pf_travel_cost "
            "WHERE project_id = ? AND substr(travel_date, 1, 7) = ?",
            (project_id, period_prefix),
        ).fetchone()[0]

        return {
            "labor": float(labor),
            "device": float(device),
            "travel": float(travel),
            "total": float(labor) + float(device) + float(travel),
        }

    @staticmethod
    def _staff_rate(conn, person_id: str) -> float:
        """人员费率（pf_staff_rate 最新）。"""
        row = conn.execute(
            "SELECT rate FROM pf_staff_rate "
            "WHERE person_name = ? ORDER BY effective_date DESC, id DESC LIMIT 1",
            (person_id,),
        ).fetchone()
        return float(row["rate"]) if row else 0.0

    @staticmethod
    def _sync_revenue(conn, project_id: int, month: str,
                      budget: float) -> float:
        """收入同步：现阶段按预算 × 进度估算，后续接 revenue 模块。"""
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS done
               FROM pm_phases WHERE project_id = ?""",
            (project_id,),
        ).fetchone()
        if row and row["total"]:
            progress = row["done"] / row["total"]
        else:
            progress = 0.0
        # 月度收入 = 预算 × 进度（简化估算；后续替换为 rr 实际确收）
        return budget * progress
