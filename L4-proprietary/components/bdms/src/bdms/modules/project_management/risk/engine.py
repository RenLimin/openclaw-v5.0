# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""RiskEngine — 风险管理引擎。

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md §8（风险子引擎接口）+ §6（风险横向覆盖）。
风险独立于项目状态机：任何项目阶段均可报备。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bdms.core.db import get_connection
from bdms.modules.base import BaseEngine, NotFoundError, ValidationError

from ..models import RiskLevel, RiskStatus, calculate_risk_level


class RiskEngine(BaseEngine):
    """风险管理引擎：报备 → 评审 → 处置 → 关闭。"""

    table_name = "rk_risks"
    soft_delete = True

    VALID_ACTIONS = {"mitigate", "accept", "transfer", "avoid"}
    REVIEW_TARGET_STATUS = {
        "mitigate": "mitigating",
        "accept": "accepted",
        "transfer": "transferred",
        "avoid": "avoided",
    }
    CLOSABLE_FROM = {"assessing", "mitigating", "accepted", "transferred", "avoided"}
    LEVEL_ORDER = ["low", "medium", "high", "critical"]

    # ========================================================
    # 风险报备（§8.1.1）
    # ========================================================

    def report_risk(
        self,
        project_id: int,
        title: str,
        description: str = "",
        risk_type: str = "",
        probability: str = "medium",
        impact: str = "medium",
        reporter: str = "system",
        owner: str = "",
        due_date: Optional[str] = None,
    ) -> int:
        """上报风险。初始状态: open。risk_level 按概率×影响矩阵自动计算。"""
        if not title or not title.strip():
            raise ValidationError("title is required")

        try:
            risk_level = calculate_risk_level(probability, impact)
        except ValueError as e:
            raise ValidationError(str(e))

        risk_no = self._generate_risk_no()

        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """INSERT INTO rk_risks
                   (risk_no, project_id, risk_type, risk_level, title, description,
                    impact, probability, reporter, status, owner, due_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)""",
                (risk_no, project_id, risk_type, risk_level, title.strip(), description,
                 impact, probability, reporter, owner, due_date),
            )
            risk_id = cur.lastrowid

            self._add_history(conn, risk_id, None, "open", "report",
                              f"风险报备（等级: {risk_level}）", reporter)
            conn.commit()
            return risk_id
        finally:
            conn.close()

    # ========================================================
    # 风险评审（§8.1.2）
    # ========================================================

    def review_risk(
        self,
        risk_id: int,
        reviewer: str,
        action: str,
        action_plan: str = "",
        owner: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> None:
        """风险评审：确定处置策略。

        状态转换: open → assessing → mitigating/accepted/transferred/avoided
        """
        if action not in self.VALID_ACTIONS:
            raise ValidationError(
                f"Invalid action: {action}. Must be one of {self.VALID_ACTIONS}"
            )

        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM rk_risks WHERE id = ? AND deleted_at IS NULL",
                (risk_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"风险 {risk_id} 不存在")
            if row["status"] != "open":
                raise ValidationError(
                    f"风险状态为 {row['status']}，只有 open 状态可评审"
                )

            target = self.REVIEW_TARGET_STATUS[action]
            now = datetime.now().isoformat()
            conn.execute(
                """UPDATE rk_risks
                   SET status = 'assessing', updated_at = ?
                   WHERE id = ?""",
                (now, risk_id),
            )
            self._add_history(conn, risk_id, "open", "assessing", "review",
                              f"评审处置策略: {action}", reviewer)

            update_fields = ["status = ?", "updated_at = ?"]
            params: list = [target, now]
            if action_plan:
                update_fields.append("description = ?")
                params.append(action_plan)
            if owner is not None:
                update_fields.append("owner = ?")
                params.append(owner)
            if due_date is not None:
                update_fields.append("due_date = ?")
                params.append(due_date)

            conn.execute(
                f"UPDATE rk_risks SET " + ", ".join(update_fields) + " WHERE id = ?",
                [*params, risk_id],
            )
            self._add_history(conn, risk_id, "assessing", target, action,
                              action_plan or f"处置策略: {action}", reviewer)
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 风险升级（§8.1.3）
    # ========================================================

    def escalate(self, risk_id: int, escalate_to: str, reason: str,
                 operator: str = "system") -> None:
        """风险升级：等级升一级并记录。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT risk_level FROM rk_risks WHERE id = ? AND deleted_at IS NULL",
                (risk_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"风险 {risk_id} 不存在")

            current_level = row["risk_level"]
            idx = self.LEVEL_ORDER.index(current_level) if current_level in self.LEVEL_ORDER else 0
            new_level = self.LEVEL_ORDER[min(idx + 1, len(self.LEVEL_ORDER) - 1)]

            conn.execute(
                "UPDATE rk_risks SET risk_level = ?, updated_at = ? WHERE id = ?",
                (new_level, datetime.now().isoformat(), risk_id),
            )
            self._add_history(conn, risk_id, None, None, "escalate",
                              f"升级至 {escalate_to}: {reason}（等级 {current_level} → {new_level}）",
                              operator)
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 风险关闭（§8.1.4）
    # ========================================================

    def close_risk(self, risk_id: int, closer: str, close_reason: str = "") -> None:
        """关闭风险（幂等：已关闭不报错）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM rk_risks WHERE id = ? AND deleted_at IS NULL",
                (risk_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"风险 {risk_id} 不存在")
            if row["status"] == "closed":
                return  # 幂等
            if row["status"] not in self.CLOSABLE_FROM:
                raise ValidationError(
                    f"风险状态为 {row['status']}，仅 {sorted(self.CLOSABLE_FROM)} 可关闭"
                )

            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE rk_risks SET status = 'closed', closed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, risk_id),
            )
            self._add_history(conn, risk_id, row["status"], "closed", "close",
                              close_reason or "风险关闭", closer)
            conn.commit()
        finally:
            conn.close()

    # ========================================================
    # 查询与汇总（§8.1.5）
    # ========================================================

    def get_risk(self, risk_id: int) -> Optional[Dict[str, Any]]:
        """获取风险详情（含历史）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM rk_risks WHERE id = ? AND deleted_at IS NULL",
                (risk_id,),
            ).fetchone()
            if not row:
                return None
            risk = dict(row)
            risk["history"] = [
                dict(h) for h in conn.execute(
                    "SELECT * FROM rk_risk_history WHERE risk_id = ? ORDER BY id",
                    (risk_id,),
                ).fetchall()
            ]
            return risk
        finally:
            conn.close()

    def list_risks(
        self,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
        risk_level: Optional[str] = None,
        risk_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """查询风险列表。"""
        conditions = ["deleted_at IS NULL"]
        params: list = []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if risk_level:
            conditions.append("risk_level = ?")
            params.append(risk_level)
        if risk_type:
            conditions.append("risk_type = ?")
            params.append(risk_type)

        where = " AND ".join(conditions)
        conn = get_connection(self.db_path)
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM rk_risks WHERE {where}", params
            ).fetchone()[0]
            offset = (max(page, 1) - 1) * page_size
            rows = conn.execute(
                f"SELECT * FROM rk_risks WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
            return [dict(r) for r in rows], total
        finally:
            conn.close()

    def get_risk_summary(self, project_id: int) -> Dict[str, Any]:
        """获取项目风险汇总（§8.1.5）。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT status, risk_level, risk_type FROM rk_risks "
                "WHERE project_id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchall()

            by_status: Dict[str, int] = {}
            by_level: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            by_type: Dict[str, int] = {}
            for r in rows:
                by_status[r["status"]] = by_status.get(r["status"], 0) + 1
                if r["risk_level"] in by_level:
                    by_level[r["risk_level"]] += 1
                if r["risk_type"]:
                    by_type[r["risk_type"]] = by_type.get(r["risk_type"], 0) + 1

            return {
                "total": len(rows),
                "open": by_status.get("open", 0),
                "assessing": by_status.get("assessing", 0),
                "mitigating": by_status.get("mitigating", 0),
                "accepted": by_status.get("accepted", 0),
                "transferred": by_status.get("transferred", 0),
                "avoided": by_status.get("avoided", 0),
                "closed": by_status.get("closed", 0),
                "by_level": by_level,
                "by_type": by_type,
            }
        finally:
            conn.close()

    def has_open_high_risks(self, project_id: int) -> bool:
        """是否存在未关闭的 critical/high 风险（验收前置检查用，§6.6）。"""
        conn = get_connection(self.db_path)
        try:
            n = conn.execute(
                """SELECT COUNT(*) FROM rk_risks
                   WHERE project_id = ? AND deleted_at IS NULL
                     AND status != 'closed'
                     AND risk_level IN ('critical', 'high')""",
                (project_id,),
            ).fetchone()[0]
            return n > 0
        finally:
            conn.close()

    def has_unclosed_risks(self, project_id: int) -> bool:
        """是否存在未关闭风险（结项前置检查用，§6.6）。"""
        conn = get_connection(self.db_path)
        try:
            n = conn.execute(
                """SELECT COUNT(*) FROM rk_risks
                   WHERE project_id = ? AND deleted_at IS NULL AND status != 'closed'""",
                (project_id,),
            ).fetchone()[0]
            return n > 0
        finally:
            conn.close()

    # ========================================================
    # BaseEngine 抽象方法实现（CRUD 型）
    # ========================================================

    def compute(self, month: str) -> Dict[str, Any]:
        conn = get_connection(self.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM rk_risks WHERE deleted_at IS NULL"
            ).fetchone()[0]
            return {"total_risks": n, "month": month}
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
                "SELECT COUNT(*) FROM rk_risks WHERE deleted_at IS NULL"
            ).fetchone()[0]
            return n > 0
        finally:
            conn.close()

    # ========================================================
    # 内部工具
    # ========================================================

    def _generate_risk_no(self) -> str:
        """生成风险编号：RISK-YYYYMMDD-NNNN。"""
        from datetime import date as _date
        conn = get_connection(self.db_path)
        try:
            today = _date.today().strftime("%Y%m%d")
            prefix = f"RISK-{today}-"
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM rk_risks WHERE risk_no LIKE ?",
                (f"{prefix}%",),
            ).fetchone()
            return f"{prefix}{(row['n'] or 0) + 1:04d}"
        finally:
            conn.close()

    def _add_history(self, conn, risk_id: int, from_status: Optional[str],
                     to_status: Optional[str], action: str, comment: str,
                     operator: str) -> None:
        """写风险历史（不 commit，由调用方管理事务）。"""
        conn.execute(
            """INSERT INTO rk_risk_history
               (risk_id, from_status, to_status, action, operator, comment)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (risk_id, from_status, to_status, action, operator, comment),
        )
