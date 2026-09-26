# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProfitService — 项目利润管理服务层。

对齐 DESIGN-DETAIL-PROFIT-MANAGEMENT-v2.1.md §3.2：
- 工时提交/审批（pf_timesheet）
- 差旅导入（Excel/CSV）
- 利润报表 + 多项目利润列表
- 收入同步
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from bdms.core.db import get_connection
from bdms.modules.base import NotFoundError, ValidationError

from .engine import ProfitEngine


class ProfitService:
    """利润管理服务层。"""

    def __init__(self, db_path=None):
        self.engine = ProfitEngine(db_path)
        self.db_path = self.engine.db_path

    # ========================================================
    # 工时（§3.2 submit/approve_timesheet）
    # ========================================================

    def submit_timesheet(
        self,
        project_id: int,
        person_id: str,
        work_date: str,
        hours: float,
        work_type: str = "",
        description: str = "",
        submitter: str = "",
    ) -> Dict[str, Any]:
        """提交工时记录（pending 状态，幂等更新）。"""
        if not person_id:
            raise ValidationError("person_id is required")
        if not (0 < hours <= 24):
            raise ValidationError(f"hours must be in (0, 24], got {hours}")
        # 未来日期校验
        try:
            if date.fromisoformat(work_date) > date.today():
                raise ValidationError(f"未来日期不可提交: {work_date}")
        except ValueError:
            raise ValidationError(f"work_date 格式非法: {work_date}")

        self._ensure_project(project_id)

        conn = get_connection(self.db_path)
        try:
            # 幂等：同项目+人+日期+类型 pending 更新
            existing = conn.execute(
                """SELECT id FROM pf_timesheet
                   WHERE project_id = ? AND person_id = ? AND work_date = ?
                     AND work_type = ? AND status = 'pending'""",
                (project_id, person_id, work_date, work_type),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE pf_timesheet SET hours = ?, description = ? WHERE id = ?",
                    (hours, description, existing["id"]),
                )
                conn.commit()
                return {"timesheet_id": existing["id"], "status": "pending",
                        "message": "已更新待审批记录"}

            cur = conn.execute(
                """INSERT INTO pf_timesheet
                   (project_id, person_id, work_date, hours, work_type,
                    description, status, created_by)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (project_id, person_id, work_date, hours, work_type,
                 description, submitter),
            )
            conn.commit()
            return {"timesheet_id": cur.lastrowid, "status": "pending",
                    "message": "已提交"}
        finally:
            conn.close()

    def approve_timesheet(
        self,
        timesheet_id: int,
        approver: str,
        approved: bool = True,
        comment: str = "",
    ) -> Dict[str, Any]:
        """审批工时记录。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM pf_timesheet WHERE id = ?",
                (timesheet_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"工时记录 {timesheet_id} 不存在")
            if row["status"] != "pending":
                raise ValidationError(
                    f"工时状态为 {row['status']}，只有 pending 可审批"
                )
            status = "approved" if approved else "rejected"
            conn.execute(
                """UPDATE pf_timesheet
                   SET status = ?, approver = ?, approved_at = ?, approval_comment = ?
                   WHERE id = ?""",
                (status, approver, datetime.now().isoformat(), comment, timesheet_id),
            )
            conn.commit()
            return {"timesheet_id": timesheet_id, "status": status,
                    "message": "审批完成"}
        finally:
            conn.close()

    # ========================================================
    # 差旅导入（§3.2 import_travel_cost）
    # ========================================================

    def import_travel_cost(
        self,
        project_id: int,
        file_path: str,
        operator: str = "",
    ) -> Dict[str, Any]:
        """导入差旅费用（Excel/CSV）。

        期望列: 员工姓名/employee, 金额/amount, 日期/date, 费用类型/type
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        self._ensure_project(project_id)

        # 读取
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        elif path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path)
        else:
            raise ValidationError(f"不支持的文件格式: {path.suffix}")

        # 列映射（中英文兼容）
        col_map = {}
        for c in df.columns:
            cl = str(c).strip().lower()
            if cl in ("员工姓名", "employee", "姓名", "name"):
                col_map[c] = "employee"
            elif cl in ("金额", "amount"):
                col_map[c] = "amount"
            elif cl in ("日期", "date", "出差日期"):
                col_map[c] = "date"
            elif cl in ("费用类型", "type", "cost_type"):
                col_map[c] = "type"

        if "employee" not in col_map.values() or "amount" not in col_map.values():
            raise ValidationError(
                f"缺少必要列（员工姓名/金额）。实际列: {list(df.columns)[:10]}"
            )

        df = df.rename(columns=col_map)

        conn = get_connection(self.db_path)
        imported = 0
        errors: List[Dict] = []
        total_amount = 0.0
        try:
            for i, row in df.iterrows():
                try:
                    raw_emp = row.get("employee")
                    employee = "" if pd.isna(raw_emp) else str(raw_emp).strip()
                    amount = float(row.get("amount", 0) or 0)
                    if not employee:
                        raise ValueError("员工姓名为空")
                    if amount < 0:
                        raise ValueError(f"金额为负: {amount}")
                    td = row.get("date")
                    travel_date = (
                        str(td)[:10] if pd.notna(td) and td else date.today().isoformat()
                    )
                    conn.execute(
                        """INSERT INTO pf_travel_cost
                           (project_id, employee_name, travel_date, cost_type, amount)
                           VALUES (?, ?, ?, ?, ?)""",
                        (project_id, employee, travel_date,
                         str(row.get("type", "") or ""), amount),
                    )
                    imported += 1
                    total_amount += amount
                except (ValueError, TypeError) as e:
                    errors.append({"row": int(i), "error": str(e)})
            conn.commit()
        finally:
            conn.close()

        return {
            "imported": imported,
            "failed": len(errors),
            "errors": errors[:20],
            "total_amount": round(total_amount, 2),
        }

    # ========================================================
    # 报表（§3.2 get_profit_report / list_projects_profit）
    # ========================================================

    def get_profit_report(self, project_id: int, period: str) -> Dict[str, Any]:
        """获取项目利润报表（单项目单期间）。"""
        conn = get_connection(self.db_path)
        try:
            project = conn.execute(
                "SELECT * FROM pm_projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if not project:
                raise NotFoundError(f"项目 {project_id} 不存在")
            project = dict(project)
        finally:
            conn.close()

        profit = self.engine.compute_profit(project_id, period)
        cost_detail = self.engine.get_cost_summary(project_id)

        # 预算状态
        budget_status = "normal"
        if project["budget"] and project["budget"] > 0:
            usage = profit["cost"] / project["budget"]
            if usage > 1.0:
                budget_status = "over_budget"
            elif usage > 0.9:
                budget_status = "warning"

        # 近 6 个月趋势
        y, m = int(period[:4]), int(period[5:7])
        months = []
        for _ in range(6):
            months.append(f"{y}-{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        monthly_trend = self.engine.aggregate_by_period(project_id, list(reversed(months)))

        return {
            "project": {
                "id": project["id"],
                "project_name": project["project_name"],
                "dept": project["dept"],
                "pm": project["pm"],
            },
            "period": period,
            "revenue": profit["revenue"],
            "cost": profit["cost"],
            "profit": profit["profit"],
            "profit_margin": profit["profit_margin"],
            "cost_detail": cost_detail,
            "revenue_detail": {"source": "budget_progress_estimate"},
            "budget_status": budget_status,
            "monthly_trend": monthly_trend,
        }

    def list_projects_profit(
        self,
        period: str,
        dept: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: str = "profit_margin",
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """列出多项目利润汇总。"""
        conn = get_connection(self.db_path)
        try:
            where = "deleted_at IS NULL"
            params: list = []
            if dept:
                where += " AND dept = ?"
                params.append(dept)
            if status:
                where += " AND status = ?"
                params.append(status)
            projects = conn.execute(
                f"SELECT id FROM pm_projects WHERE {where}", params
            ).fetchall()
        finally:
            conn.close()

        items = []
        for p in projects:
            try:
                profit = self.engine.compute_profit(p["id"], period)
                items.append({"project_id": p["id"], **profit})
            except (NotFoundError, ValidationError):
                continue

        # 排序
        if sort_by in ("profit_margin", "profit", "revenue", "cost"):
            items.sort(key=lambda x: x.get(sort_by, 0), reverse=True)

        total = len(items)
        start = (max(page, 1) - 1) * page_size
        return {
            "items": items[start:start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ========================================================
    # 收入同步（§3.2 sync_revenue）
    # ========================================================

    def sync_revenue(self, project_id: int, period: str,
                     revenue: float) -> Dict[str, Any]:
        """手工同步收入（后续接 revenue 模块自动同步）。"""
        profit = self.engine.compute_profit(
            project_id, period, revenue_override=revenue
        )
        return {"synced": True, "period": period, "profit": profit}

    # ========================================================
    # 内部工具
    # ========================================================

    def _ensure_project(self, project_id: int) -> None:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM pm_projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"项目 {project_id} 不存在")
        finally:
            conn.close()
