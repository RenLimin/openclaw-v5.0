"""确认收入管理 —— 服务层（对齐 MODULE-CONTRACT 的 service 契约）。

职责：
  1. 统一幂等语义（auto / read / regenerate），与模块1 delivery_report 保持一致
  2. 对接 BDMS 元数据表（job 日志）
  3. 为 CLI / Web 提供稳定入口，不让上层直接摸 engine

模式语义（与 delivery_report 完全对齐）：
  auto        已有数据则 read，否则 generated
  read        只读；无数据时报错
  regenerate  强制重新计算，覆盖旧数据
"""

from pathlib import Path
from typing import Optional

from bdms.core import db as _db

from .engine import RevenueEngineAdapter

MODE_AUTO = "auto"
MODE_READ = "read"
MODE_REGENERATE = "regenerate"


class RevenueService:
    """确认收入服务层。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.adapter = RevenueEngineAdapter(db_path)
        self.db_path = self.adapter.db_path
        # 元数据表在 BDMS 主库
        from bdms.core.paths import DATA_DIR
        self.meta_db_path = DATA_DIR / "bdms.db"

    # ─── 幂等生成 ───

    def generate(self, month: str, mode: str = MODE_AUTO) -> dict:
        """生成/读取确认收入数据。

        返回 {"month", "mode", "action", "sheets", "job_id"}
        """
        if mode not in (MODE_AUTO, MODE_READ, MODE_REGENERATE):
            raise ValueError(f"未知模式: {mode}")

        conn = _db.get_connection(self.meta_db_path)
        try:
            job_id = _db.create_job(conn, "revenue", month, mode)
            conn.commit()
        finally:
            conn.close()
        try:
            has_data = self.has_data(month)

            if mode == MODE_READ:
                if not has_data:
                    raise ValueError(f"{month} 无数据可读，请先用 auto/regenerate 生成")
                action = "read"
            elif mode == MODE_REGENERATE:
                action = "generated"
            else:  # auto
                action = "read" if has_data else "generated"

            if action == "generated":
                sheets = self.adapter.compute(month)
                sheets = {k: (len(v) if isinstance(v, (list, dict)) else v)
                          for k, v in sheets.items()}
            else:
                sheets = self.summary_counts(month)
        except Exception as e:
            self._finish_job(job_id, "failed", 0, message=str(e)[:500])
            raise

        self._finish_job(job_id, "done", 100,
                         message=f"{action}: {len(sheets)} sheets")
        return {"month": month, "mode": mode, "action": action,
                "sheets": sheets, "job_id": job_id}

    def _finish_job(self, job_id: int, status: str, progress: int,
                    message: str = None, output_path: str = None) -> None:
        conn = _db.get_connection(self.meta_db_path)
        try:
            _db.update_job_status(conn, job_id, status, progress, message, output_path)
            conn.commit()
        finally:
            conn.close()

    # ─── 状态查询 ───

    def has_data(self, month: str) -> bool:
        return self.adapter.has_data(month)

    def list_months(self) -> list:
        """DB 中已有数据的月份。"""
        if not self.db_path.exists():
            return []
        conn = _db.get_connection(self.db_path)
        try:
            if not _db.table_exists(conn, "budget_exec"):
                return []
            rows = conn.execute(
                """SELECT DISTINCT archive_month AS m FROM budget_exec
                   WHERE archive_month IS NOT NULL ORDER BY m DESC"""
            ).fetchall()
            return [r["m"] for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def summary_counts(self, month: str) -> dict:
        """已落盘数据的规模概览（read 模式下用）。"""
        if not self.db_path.exists():
            return {}
        counts: dict = {}
        conn = _db.get_connection(self.db_path)
        try:
            for t in ("plan_draft", "budget_exec", "monthly_summary",
                      "performance_summary"):
                if not _db.table_exists(conn, t):
                    continue
                try:
                    row = conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()
                    counts[t] = row["n"] if row else 0
                except Exception:
                    counts[t] = "?"
        finally:
            conn.close()
        return counts

    # ─── 导入 ───

    def import_source(self, month: str, excel_path: Optional[Path] = None) -> dict:
        """导入原始确收对比表。"""
        return self.adapter.import_source(month, excel_path)

    def sources_available(self, month: str) -> bool:
        return self.adapter.sources_available(month)

    # ─── 汇总 ───

    def summary(self, month: str) -> dict:
        """Web/CLI 用的确认收入汇总。"""
        from .summary_engine import SummaryEngine
        return SummaryEngine().compute_summary(month)
