"""交付月报服务层 — 人机协作幂等编排。

模式：
  auto       默认：DB 有 → 读取；DB 无 → 生成
  read       强制从 DB 读取（不重算）
  regenerate 强制重算 + 覆盖 DB

人机协作状态机（审核状态）：
  generating → validating → reviewing → approved → exported
                   ↑________↓
                      rejected
"""

from pathlib import Path
from typing import Optional, List, Dict

from bdms.core import db as _db
from .engine import DeliveryReportEngine
from .validator import DeliveryReportValidator

MODE_AUTO = "auto"
MODE_READ = "read"
MODE_REGENERATE = "regenerate"


class DeliveryReportService:
    """交付月报编排服务（人机协作模式）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.engine = DeliveryReportEngine(db_path)
        self.db_path = db_path

    # ──────────────────────────────────────────────────────
    #  状态查询
    # ──────────────────────────────────────────────────────

    def get_review_status(self, month: str) -> dict:
        """获取某月的审核状态（人机协作流程位置）。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM dr_review_status WHERE month = ?", (month,)
            ).fetchone()
            if row:
                return dict(row)
            return {
                "month": month, "status": "not_started",
                "total_errors": 0, "total_warnings": 0, "pending_fixes": 0,
            }
        finally:
            conn.close()

    def list_review_months(self) -> list[dict]:
        """列出所有已生成月份的审核状态（按月份倒序）。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT month, status, total_errors, total_warnings, pending_fixes, "
                "generated_at, validated_at, reviewed_at, approved_at, reviewer "
                "FROM dr_review_status ORDER BY month DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def list_review_issues(self, month: str, status_filter: str = None) -> dict:
        """列出某月的所有校验问题。"""
        conn = _db.get_connection(self.db_path)
        try:
            sql = "SELECT * FROM dr_import_validation WHERE month = ?"
            params = [month]
            if status_filter:
                sql += " AND status = ?"
                params.append(status_filter)
            sql += " ORDER BY sheet, row_index"
            rows = conn.execute(sql, params).fetchall()
            return {
                "month": month,
                "issues": [dict(r) for r in rows],
                "total": len(rows),
                "pending": sum(1 for r in rows if r["status"] == "pending"),
                "confirmed": sum(1 for r in rows if r["status"] == "confirmed"),
                "rejected": sum(1 for r in rows if r["status"] == "rejected"),
            }
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────
  #  人机协作审核操作
    # ──────────────────────────────────────────────────────

    def approve_review(self, month: str, reviewer: str = "") -> dict:
        """人工确认：审批通过，进入 approved 状态。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM dr_review_status WHERE month = ?", (month,)
            ).fetchone()
            if not row:
                raise ValueError(f"{month} 无审核记录")
            if row["status"] == "approved":
                raise ValueError(f"{month} 已审核通过，无需重复操作")

            conn.execute(
                "UPDATE dr_review_status SET status='approved', approved_at=datetime('now','localtime'), "
                "reviewer=?, updated_at=datetime('now','localtime') WHERE month=?",
                (reviewer, month)
            )
            conn.commit()
            return {"month": month, "status": "approved", "reviewer": reviewer}
        finally:
            conn.close()

    def reject_review(self, month: str, reason: str = "", reviewer: str = "") -> dict:
        """人工驳回：打回 reviewing 状态等待修正。"""
        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE dr_review_status SET status='reviewing', reviewer=?, "
                "updated_at=datetime('now','localtime') WHERE month=?",
                (reviewer, month)
            )
            conn.commit()
            return {"month": month, "status": "reviewing", "reason": reason}
        finally:
            conn.close()

    def revalidate(self, month: str) -> dict:
        """人工触发：重新校验（修正后验证）。"""
        validator = DeliveryReportValidator(self.db_path)
        result = validator.collect_suspicious(month)

        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                "UPDATE dr_review_status SET status='validating', "
                "total_errors=?, total_warnings=?, pending_fixes=?, "
                "updated_at=datetime('now','localtime') WHERE month=?",
                (result["summary"]["total_errors"],
                 result["summary"]["total_warnings"],
                 result["summary"]["total_errors"],
                 month)
            )
            conn.commit()
        finally:
            conn.close()

        return {"month": month, "validation": result}

    # ──────────────────────────────────────────────────────
    #  原有方法
    # ──────────────────────────────────────────────────────

    def generate(self, month: str, mode: str = MODE_AUTO) -> dict:
        """生成/读取交付月报数据。"""
        if mode not in (MODE_AUTO, MODE_READ, MODE_REGENERATE):
            raise ValueError(f"未知模式: {mode}")

        conn = _db.get_connection(self.db_path)
        try:
            job_id = _db.create_job(conn, "delivery_report", month, mode)
            conn.commit()
        finally:
            conn.close()

        try:
            has_data = self.engine.has_data(month)

            if mode == MODE_READ:
                if not has_data:
                    raise ValueError(f"{month} 无数据可读，请先用 auto/regenerate 生成")
                action = "read"
            elif mode == MODE_REGENERATE:
                action = "generated"
            else:
                action = "read" if has_data else "generated"

            if action == "read":
                data = self.engine.load(month)
                counts = {k: len(v) for k, v in data.items()}
            else:
                computed = self.engine.compute(month)
                counts = self.engine.persist(month, computed,
                                             overwrite=(mode == MODE_REGENERATE or has_data))

            self._finish_job(job_id, "done", 100,
                             message=f"{action}: {sum(counts.values())} 行")

            # 更新审核状态为 validating（等待人工审核）
            self._update_review_status(month, "validating", counts=counts)

            return {
                "month": month, "mode": mode, "action": action,
                "sheets": counts, "job_id": job_id,
                "total_rows": sum(counts.values()),
                "review_status": "validating",
            }
        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

    def _update_review_status(self, month: str, status: str, counts: dict = None):
        """更新审核状态。"""
        conn = _db.get_connection(self.db_path)
        try:
            existing = conn.execute(
                "SELECT id FROM dr_review_status WHERE month = ?", (month,)
            ).fetchone()

            set_parts = ["status=?", "updated_at=datetime('now','localtime')"]
            if status == "generating":
                set_parts.append("generated_at=datetime('now','localtime')")
            elif status == "validating":
                set_parts.append("validated_at=datetime('now','localtime')")

            if existing:
                set_clause = ", ".join(set_parts)
                conn.execute(
                    f"UPDATE dr_review_status SET {set_clause} WHERE month=?",
                    (status, month)
                )
            else:
                conn.execute(
                    "INSERT INTO dr_review_status (month, status, generated_at, updated_at) "
                    "VALUES (?, ?, datetime('now','localtime'), datetime('now','localtime'))",
                    (month, status)
                )

            # 同步校验统计
            if status == "validating":
                validator = DeliveryReportValidator(self.db_path)
                result = validator.collect_suspicious(month)
                conn.execute(
                    "UPDATE dr_review_status SET total_errors=?, total_warnings=?, pending_fixes=? "
                    "WHERE month=?",
                    (result["summary"]["total_errors"],
                     result["summary"]["total_warnings"],
                     result["summary"]["total_errors"],
                     month)
                )

            conn.commit()
        finally:
            conn.close()

    def _finish_job(self, job_id: int, status: str, progress: int,
                    message: str = None, output_path: str = None) -> None:
        conn = _db.get_connection(self.db_path)
        try:
            _db.update_job_status(conn, job_id, status, progress, message, output_path)
            conn.commit()
        finally:
            conn.close()

    def has_data(self, month: str) -> bool:
        return self.engine.has_data(month)

    def list_months(self) -> list[dict]:
        conn = _db.get_connection(self.db_path)
        try:
            return _db.list_months(conn, "delivery_report")
        finally:
            conn.close()

    # ─── 分步生成（v2.1：Step 1-3 + 校验）───

    def generate_with_validation(self, month: str,
                                 fixes: List[Dict] = None) -> dict:
        """带校验的生成流程（Step 1 → 2 → 3）。"""
        validator = DeliveryReportValidator(self.db_path)

        if fixes:
            validator.apply_manual_fixes(month, fixes)

        if not self.engine.has_data(month):
            result = self.generate(month, mode=MODE_REGENERATE)
        else:
            result = {"month": month, "action": "read"}

        suspicious = validator.collect_suspicious(month)

        return {
            **result,
            "validation": suspicious,
            "pending_fixes": suspicious["summary"]["total_errors"] > 0,
        }

    def validate(self, month: str) -> dict:
        """单独执行 Step 2 校验。"""
        return DeliveryReportValidator(self.db_path).collect_suspicious(month)

    def apply_fixes(self, month: str, fixes: List[Dict]) -> dict:
        """单独应用人工调整。"""
        return DeliveryReportValidator(self.db_path).apply_manual_fixes(month, fixes)
