"""交付月报服务层 — 幂等编排。

三种模式：
  auto       默认：DB 有 → 读取；DB 无 → 生成
  read       强制从 DB 读取（不重算）
  regenerate 强制重算 + 覆盖 DB
"""

from pathlib import Path
from typing import Optional

from bdms.core import db as _db
from .engine import DeliveryReportEngine

MODE_AUTO = "auto"
MODE_READ = "read"
MODE_REGENERATE = "regenerate"


class DeliveryReportService:
    """交付月报编排服务。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.engine = DeliveryReportEngine(db_path)
        self.db_path = db_path

    def generate(self, month: str, mode: str = MODE_AUTO) -> dict:
        """生成/读取交付月报数据。

        Returns: {
            "month": str, "mode": str, "action": "read"|"generated",
            "sheets": {name: row_count}, "job_id": int
        }
        """
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

            # 决定动作
            if mode == MODE_READ:
                if not has_data:
                    raise ValueError(f"{month} 无数据可读，请先用 auto/regenerate 生成")
                action = "read"
            elif mode == MODE_REGENERATE:
                action = "generated"
            else:  # auto
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
            return {
                "month": month, "mode": mode, "action": action,
                "sheets": counts, "job_id": job_id,
                "total_rows": sum(counts.values()),
            }
        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

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
