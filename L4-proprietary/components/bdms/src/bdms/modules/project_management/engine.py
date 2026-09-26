# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""ProjectEngine — 项目核心引擎。

职责（对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md §3.1）：
- 项目主数据 CRUD + 软删除
- 项目状态机（9 状态 + 合法转换校验）
- 阶段管理（7 阶段模板）
- 团队成员管理
- 里程碑管理
- 交付报告管理
- 实施字段（impl_owner/impl_status/impl_start_date/impl_end_date）
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from bdms.core.db import get_connection
from bdms.modules.base import BaseEngine, NotFoundError, StateTransitionError, ValidationError

from .models import VALID_TRANSITIONS, is_valid_transition, DEFAULT_PHASES_V21, VALID_IMPL_STATUSES


class ProjectEngine(BaseEngine):
    """项目核心引擎：项目主数据 + 状态机 + 阶段/团队/里程碑/交付报告。"""

    table_name = "pm_projects"
    soft_delete = True

    # ========================================================
    # 项目创建与基本信息（§3.1.1 ~ 3.1.2）
    # ========================================================

    def create_project(
        self,
        project_name: str,
        project_type: str = "",
        dept: str = "",
        pm: str = "",
        contract_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        budget: float = 0.0,
        created_by: str = "system",
        project_no: Optional[str] = None,
        impl_owner: Optional[str] = None,
        impl_status: str = "not_started",
        impl_start_date: Optional[str] = None,
        impl_end_date: Optional[str] = None,
    ) -> int:
        """创建项目（立项）。初始状态: initiating。

        项目编号自动生成：PROJ-YYYYMMDD-NNNN（按日自增）。
        """
        if not project_name or not project_name.strip():
            raise ValidationError("project_name is required")

        if impl_status not in VALID_IMPL_STATUSES:
            raise ValidationError(
                f"Invalid impl_status: {impl_status}. Must be one of {VALID_IMPL_STATUSES}"
            )

        if project_no is None:
            project_no = self._generate_project_no()

        data = {
            "project_no": project_no,
            "project_name": project_name.strip(),
            "project_type": project_type,
            "dept": dept,
            "pm": pm,
            "contract_id": contract_id,
            "status": "initiating",
            "start_date": start_date,
            "end_date": end_date,
            "budget": budget,
            "impl_owner": impl_owner,
            "impl_status": impl_status,
            "impl_start_date": impl_start_date,
            "impl_end_date": impl_end_date,
            "created_by": created_by,
            "updated_by": created_by,
        }
        return self._insert(data)

    def update_project(self, project_id: int, **data) -> None:
        """更新项目基本信息（禁止直接改 status / id / project_no / created_by / created_at）。"""
        allowed = {
            "project_name", "project_type", "dept", "pm", "contract_id",
            "start_date", "end_date", "budget",
            "impl_owner", "impl_status", "impl_start_date", "impl_end_date",
        }
        update = {k: v for k, v in data.items() if k in allowed}
        if not update:
            return

        if "impl_status" in update and update["impl_status"] is not None:
            if update["impl_status"] not in VALID_IMPL_STATUSES:
                raise ValidationError(
                    f"Invalid impl_status: {update['impl_status']}. "
                    f"Must be one of {VALID_IMPL_STATUSES}"
                )

        update["updated_by"] = data.get("updated_by", "system")
        update["updated_at"] = datetime.now().isoformat()

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                f"UPDATE {self.table_name} SET "
                + ", ".join(f"{k} = ?" for k in update)
                + " WHERE id = ? AND deleted_at IS NULL",
                [*update.values(), project_id],
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"项目 {project_id} 不存在")
            conn.commit()
        finally:
            conn.close()

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """获取项目详情（含软删除过滤）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_projects(
        self,
        status: Optional[str] = None,
        pm: Optional[str] = None,
        project_type: Optional[str] = None,
        dept: Optional[str] = None,
        keyword: Optional[str] = None,
        impl_owner: Optional[str] = None,
        impl_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """项目列表查询（搜索 + 筛选 + 分页）。"""
        conditions = ["deleted_at IS NULL"]
        params: list = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if pm:
            conditions.append("pm = ?")
            params.append(pm)
        if project_type:
            conditions.append("project_type = ?")
            params.append(project_type)
        if dept:
            conditions.append("dept = ?")
            params.append(dept)
        if impl_owner:
            conditions.append("impl_owner = ?")
            params.append(impl_owner)
        if impl_status:
            conditions.append("impl_status = ?")
            params.append(impl_status)
        if keyword:
            conditions.append("(project_name LIKE ? OR project_no LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        where = " AND ".join(conditions)
        conn = get_connection(self.db_path)
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM {self.table_name} WHERE {where}", params
            ).fetchone()[0]
            offset = (max(page, 1) - 1) * page_size
            rows = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE {where} "
                f"ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
            return [dict(r) for r in rows], total
        finally:
            conn.close()

    def delete_project(self, project_id: int) -> None:
        """软删除项目。"""
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                f"UPDATE {self.table_name} SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (datetime.now().isoformat(), project_id),
            )
            if cur.rowcount == 0:
                raise NotFoundError(f"项目 {project_id} 不存在")
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 状态机（§3.1.3 ~ 3.1.4）
    # ========================================================

    def transition_state(
        self,
        project_id: int,
        to_state: str,
        operator: str = "system",
        comment: str = "",
    ) -> str:
        """推进项目状态（幂等：同状态直接返回）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                f"SELECT status FROM {self.table_name} WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"项目 {project_id} 不存在")

            current = row["status"]
            if current == to_state:
                return current  # 幂等

            if not is_valid_transition(current, to_state):
                allowed = VALID_TRANSITIONS.get(current, set())
                raise StateTransitionError(
                    f"非法状态转换: {current} → {to_state}。"
                    f"当前状态允许: {sorted(allowed)}"
                )

            conn.execute(
                f"UPDATE {self.table_name} SET status = ?, updated_by = ?, "
                f"updated_at = ? WHERE id = ?",
                (to_state, operator, datetime.now().isoformat(), project_id),
            )
            conn.commit()
            return to_state
        finally:
            conn.close()

    def get_status(self, project_id: int) -> str:
        """获取项目当前状态。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                f"SELECT status FROM {self.table_name} WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"项目 {project_id} 不存在")
            return row["status"]
        finally:
            conn.close()

    # ========================================================
    # 阶段管理（§3.1.6 + 7 阶段模板 §3.2.1）
    # ========================================================

    def add_phase(
        self,
        project_id: int,
        phase_name: str,
        phase_order: int = 0,
        planned_start: Optional[str] = None,
        planned_end: Optional[str] = None,
    ) -> int:
        """添加项目阶段。"""
        if not phase_name or not phase_name.strip():
            raise ValidationError("phase_name is required")
        self._ensure_exists(project_id)

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO pm_phases
                   (project_id, phase_name, phase_order, planned_start, planned_end)
                   VALUES (?, ?, ?, ?, ?)""",
                (project_id, phase_name.strip(), phase_order, planned_start, planned_end),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def init_default_phases(self, project_id: int) -> int:
        """初始化 7 阶段默认模板（立项→规划→执行→交付→验收→售后→结项）。"""
        conn = get_connection(self.db_path)
        try:
            for ph in DEFAULT_PHASES_V21:
                conn.execute(
                    """INSERT INTO pm_phases
                       (project_id, phase_name, phase_order)
                       VALUES (?, ?, ?)""",
                    (project_id, ph["phase_name"], ph["phase_order"]),
                )
            conn.commit()
            return len(DEFAULT_PHASES_V21)
        finally:
            conn.close()

    def list_phases(self, project_id: int) -> List[Dict[str, Any]]:
        """获取项目阶段列表（按 order 排序）。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM pm_phases WHERE project_id = ? ORDER BY phase_order",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def update_phase(self, phase_id: int, **data) -> None:
        """更新阶段（status/planned_start/planned_end/actual_start/actual_end）。"""
        allowed = {"status", "planned_start", "planned_end", "actual_start", "actual_end"}
        update = {k: v for k, v in data.items() if k in allowed}
        if not update:
            return
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE pm_phases SET " + ", ".join(f"{k} = ?" for k in update)
                + " WHERE id = ?",
                [*update.values(), phase_id],
            )
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 团队成员管理（§3.1.7）
    # ========================================================

    def add_team_member(
        self,
        project_id: int,
        member_name: str,
        role: str = "",
        allocation: float = 1.0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """添加项目成员。唯一约束: (project_id, member_name, role)。"""
        if not member_name or not member_name.strip():
            raise ValidationError("member_name is required")
        if not (0 < allocation <= 1.0):
            raise ValidationError(f"allocation must be in (0, 1.0], got {allocation}")
        self._ensure_exists(project_id)

        conn = get_connection(self.db_path)
        try:
            try:
                cur = conn.execute(
                    """INSERT INTO pm_team_members
                       (project_id, member_name, role, allocation, start_date, end_date)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (project_id, member_name.strip(), role, allocation, start_date, end_date),
                )
                conn.commit()
                return cur.lastrowid
            except Exception as e:
                if "UNIQUE" in str(e):
                    raise ValidationError(
                        f"成员已存在: {member_name} ({role})。"
                        "同一项目同一成员同一角色唯一。"
                    )
                raise
        finally:
            conn.close()

    def list_team_members(self, project_id: int) -> List[Dict[str, Any]]:
        """获取项目成员列表。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM pm_team_members WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def remove_team_member(self, member_id: int) -> None:
        """移除项目成员。"""
        conn = get_connection(self.db_path)
        try:
            conn.execute("DELETE FROM pm_team_members WHERE id = ?", (member_id,))
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 里程碑管理（§3.1.8）
    # ========================================================

    def add_milestone(
        self,
        project_id: int,
        milestone_name: str,
        planned_date: Optional[str] = None,
        status: str = "pending",
    ) -> int:
        """添加里程碑。"""
        if not milestone_name or not milestone_name.strip():
            raise ValidationError("milestone_name is required")
        self._ensure_exists(project_id)

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO pm_milestones
                   (project_id, milestone_name, planned_date, status)
                   VALUES (?, ?, ?, ?)""",
                (project_id, milestone_name.strip(), planned_date, status),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def list_milestones(self, project_id: int) -> List[Dict[str, Any]]:
        """获取项目里程碑列表。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM pm_milestones WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def achieve_milestone(self, milestone_id: int, actual_date: Optional[str] = None) -> None:
        """达成里程碑。"""
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE pm_milestones SET status = 'achieved', actual_date = ? WHERE id = ?",
                (actual_date or date.today().isoformat(), milestone_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 交付报告管理（§3.1.9）
    # ========================================================

    def submit_delivery_report(
        self,
        project_id: int,
        report_type: str,
        title: str,
        content: str = "",
        attachments: str = "",
        created_by: str = "system",
    ) -> int:
        """提交交付报告（初始状态: submitted）。"""
        if not title or not title.strip():
            raise ValidationError("title is required")
        if not report_type:
            raise ValidationError("report_type is required")
        self._ensure_exists(project_id)

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO pm_delivery_reports
                   (project_id, report_type, title, content, attachments,
                    status, created_by, submitted_at)
                   VALUES (?, ?, ?, ?, ?, 'submitted', ?, ?)""",
                (project_id, report_type, title.strip(), content, attachments,
                 created_by, datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def list_delivery_reports(self, project_id: int) -> List[Dict[str, Any]]:
        """获取项目交付报告列表。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM pm_delivery_reports "
                "WHERE project_id = ? AND deleted_at IS NULL ORDER BY id",
                (project_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def review_delivery_report(
        self, report_id: int, approved: bool, reviewer: str = "system"
    ) -> None:
        """审核交付报告（submitted → approved/rejected）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM pm_delivery_reports WHERE id = ?", (report_id,)
            ).fetchone()
            if not row:
                raise NotFoundError(f"交付报告 {report_id} 不存在")
            if row["status"] != "submitted":
                raise ValidationError(
                    f"交付报告状态为 {row['status']}，只有 submitted 状态可审核"
                )
            conn.execute(
                "UPDATE pm_delivery_reports SET status = ?, reviewed_at = ? WHERE id = ?",
                ("approved" if approved else "rejected",
                 datetime.now().isoformat(), report_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # BaseEngine 抽象方法实现（CRUD 型引擎，非月度计算型）
    # ========================================================

    def compute(self, month: str) -> Dict[str, Any]:
        """按月统计项目指标（供 BaseEngine 契约）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM pm_projects WHERE deleted_at IS NULL"
            ).fetchone()
            return {"total_projects": row["n"], "month": month}
        finally:
            conn.close()

    def persist(self, month: str, data: Dict[str, Any], overwrite: bool = True) -> Dict[str, int]:
        """CRUD 型引擎无需持久化计算结果。"""
        return {"inserted": 0, "updated": 0, "deleted": 0}

    def load(self, month: str) -> Dict[str, Any]:
        """CRUD 型引擎直接查 DB。"""
        return self.compute(month)

    def has_data(self, month: str) -> bool:
        """是否存在项目数据。"""
        conn = get_connection(self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM pm_projects WHERE deleted_at IS NULL"
            ).fetchone()[0]
            return n > 0
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _generate_project_no(self) -> str:
        """生成项目编号：PROJ-YYYYMMDD-NNNN（按日自增）。"""
        conn = get_connection(self.db_path)
        try:
            today = date.today().strftime("%Y%m%d")
            prefix = f"PROJ-{today}-"
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM pm_projects WHERE project_no LIKE ?",
                (f"{prefix}%",),
            ).fetchone()
            seq = (row["n"] or 0) + 1
            return f"{prefix}{seq:04d}"
        finally:
            conn.close()

    def _ensure_exists(self, project_id: int) -> None:
        """确保项目存在，否则抛 NotFoundError。"""
        if not self.get_project(project_id):
            raise NotFoundError(f"项目 {project_id} 不存在")
