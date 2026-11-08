"""service — revenue_forecast 编排层（Phase 4）。

职责（DESIGN-DETAIL-REVENUE-FORECAST §5/§7/§8）：
  - 上传异步 job：保存文件 → parser.parse → engine.forecast → repository.save_result，
    全程把步骤/百分比写 job 行（进度条铁律）；
  - 读模型：periods / overview / monthly / lines，透传 repository；
  - 失败边界：任何异常 job=failed，save_result 只在成功后调用，current 绝不被半成品切换；
  - 恒等式不符（ParseReport.issues）可读但不阻断，除非解析后无有效行。

金额单位：元。不引第三方依赖；SQLite 路径复用 core.paths.DB_PATH（支持 BDMS_DB 覆盖）。
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Optional, Union

from bdms.core import db as _db
from bdms.core.paths import DB_PATH

from .engine import forecast
from .report_parser import parse_report
from .repository import (
    ForecastRepository,
    BASIS_LOCKED,
    BASIS_DYNAMIC_DUE,
    BASIS_PIPELINE,
)

MODULE_NAME = "revenue_forecast"
DEFAULT_YEAR = 2026

# 进度步骤（step, pct）
STEP_QUEUED = ("等待处理", 0)
STEP_PARSE = ("解析财报（预算执行表/底稿）", 25)
STEP_CLASSIFY = ("关联履约项并分类", 55)
STEP_CALC = ("计算双口径预估", 75)
STEP_SAVE = ("结果落库并切换账期", 95)
STEP_DONE = ("完成", 100)

_PERIOD_RE = re.compile(r"(20\d{4})")


class ForecastServiceError(ValueError):
    """service 层业务错误（API 层映射 400）。"""


class ForecastService:
    """上传 job 编排 + 读模型。线程内各自开连接，无线程间共享状态。"""

    # ─── 上传：创建 job + 后台线程 ───

    def start_upload(
        self,
        file_bytes: bytes,
        filename: str,
        period: Optional[str] = None,
        year: int = DEFAULT_YEAR,
    ) -> dict:
        """保存上传文件、创建 job、起后台线程；立即返回 {job_id, period}。"""
        if not file_bytes:
            raise ForecastServiceError("上传文件为空")

        period = self._resolve_period(period, filename or "")
        # xlsx 魔数简单校验留给 parser 抛明确错误；这里先保存
        saved_path = self._save_upload(file_bytes, period, filename or "upload.xlsx")

        conn = _db.get_connection()
        try:
            job_id = _db.create_job(conn, MODULE_NAME, period, "upload")
            _db.update_job_status(conn, job_id, "running", STEP_QUEUED[1],
                                  STEP_QUEUED[0])
            conn.commit()
        finally:
            conn.close()

        thread = threading.Thread(
            target=self._run_guarded,
            args=(job_id, str(saved_path), period, int(year), filename or ""),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id, "period": period}

    def _run_guarded(self, job_id: int, saved_path: str, period: str,
                     year: int, original_name: str) -> None:
        """后台线程外壳：兜底所有异常写 failed，绝不抛出线程。"""
        try:
            self.run_upload_job(job_id, saved_path, period, year, original_name)
        except Exception as exc:  # noqa: BLE001 — 边界要求：任何异常落 failed
            self._set_failed(job_id, exc)

    # ─── 上传 job 主体（也可单测直接调用）───

    def run_upload_job(
        self,
        job_id: int,
        saved_path: Union[str, Path],
        period: str,
        year: int = DEFAULT_YEAR,
        original_name: str = "",
    ) -> None:
        """编排：parse → forecast → save_result，分阶段更新进度。

        - ParseReport.issues（恒等式不符）不阻断；
        - 无有效行（无任何关联上预算执行表的行）视为失败；
        - save_result 成功后 job 才置 done；失败时 current 不切换。
        """
        self._set_progress(job_id, *STEP_PARSE)
        report = parse_report(saved_path, forecast_year=year)

        self._set_progress(job_id, *STEP_CLASSIFY)
        valid_rows = [r for r in report.rows if r.matched_budget]
        if not valid_rows:
            raise ForecastServiceError(
                "财报解析后无有效履约行（底稿与预算执行表零关联），"
                "请确认上传的是收入预算执行对比表"
            )

        self._set_progress(job_id, *STEP_CALC)
        result = forecast(report.rows, period=period, forecast_year=year)

        # 落库前确保 forecast 四张表存在
        repo = self._repository()
        try:
            repo.ensure_schema()
            self._set_progress(job_id, *STEP_SAVE)
            repo.save_result(
                period, report.rows, result,
                source_file=original_name or Path(str(saved_path)).name,
            )
        finally:
            repo.close()

        self._set_done(job_id, report, result)

    # ─── 读模型（透传 repository）───

    def list_periods(self) -> dict:
        """{current, periods[]}。"""
        repo = self._repository()
        try:
            repo.ensure_schema()
            current_row = repo.get_current_period()
            rows = repo.list_periods()
        finally:
            repo.close()
        return {
            "current": current_row["period"] if current_row else None,
            "periods": rows,
        }

    def get_overview(self, period: Optional[str] = None) -> dict:
        """锁定/动态/实际/差异 + 各自 by_group。金额单位元。"""
        period = self._require_period(period)
        repo = self._repository()
        try:
            totals = repo.get_totals(period)
        finally:
            repo.close()
        if totals is None:
            raise ForecastServiceError(f"账期 {period} 不存在，请先上传财报")
        return {
            "period": period,
            "forecast_year": totals.get("forecast_year"),
            "locked": {
                "total": totals["locked_total"],
                "by_group": totals["locked_by_group"],
            },
            "dynamic": {
                "total": totals["dynamic_total"],
                "by_group": totals["dynamic_by_group"],
                "pipeline": totals["dynamic_pipeline"],
            },
            "actual": totals["actual_ytd"],
            "gap": totals["gap"],
        }

    def get_monthly(self, period: Optional[str] = None,
                    basis: str = "locked") -> dict:
        """逐月 + pipeline。

        basis=locked → 锁定 12 月；
        basis=dynamic → DUE_2026 12 月 + pipeline 桶。
        """
        period = self._require_period(period)
        if basis not in ("locked", "dynamic"):
            raise ForecastServiceError("basis 必须为 locked 或 dynamic")
        repo_basis = BASIS_LOCKED if basis == "locked" else BASIS_DYNAMIC_DUE
        repo = self._repository()
        try:
            months = repo.get_monthly(period, repo_basis)
            pipeline = repo.get_monthly(period, BASIS_PIPELINE)["pipeline"]
        finally:
            repo.close()
        return {
            "period": period,
            "basis": basis,
            "months": months,
            "pipeline": pipeline,
        }

    def get_lines(
        self,
        period: Optional[str] = None,
        category: Optional[str] = None,
        in_plan: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """明细分页，透传 repository.query_lines。"""
        period = self._require_period(period)
        repo = self._repository()
        try:
            return repo.query_lines(
                period, category=category, in_plan=in_plan,
                page=page, page_size=page_size,
            )
        finally:
            repo.close()

    def get_progress(self, job_id: int) -> dict:
        """读 job 行 → 契约 {status, step, pct, error}。"""
        conn = _db.get_connection()
        try:
            row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return {"status": "not_found", "step": None, "pct": 0,
                    "error": f"job {job_id} 不存在"}
        d = dict(row)
        failed = d.get("status") == "failed"
        return {
            "status": d.get("status"),
            "step": d.get("message"),
            "pct": d.get("progress") or 0,
            "error": d.get("message") if failed else None,
        }

    # ─── 内部工具 ───

    def _repository(self) -> ForecastRepository:
        return ForecastRepository(DB_PATH)

    def _require_period(self, period: Optional[str]) -> str:
        if period:
            return _db.normalize_month(period)
        repo = self._repository()
        try:
            repo.ensure_schema()
            current = repo.get_current_period()
        finally:
            repo.close()
        if current is None:
            raise ForecastServiceError("未指定 period 且当前无生效账期")
        return current["period"]

    @staticmethod
    def _resolve_period(period: Optional[str], filename: str) -> str:
        """period 缺省时从文件名提取 6 位期间（如 ...202601-09... → 202609）；否则 400。"""
        if period:
            normalized = _db.normalize_month(period)
            if not (len(normalized) == 6 and normalized.isdigit()):
                raise ForecastServiceError(f"period 格式非法: {period!r}，应为 YYYYMM")
            return normalized
        hits = _PERIOD_RE.findall(filename or "")
        if hits:
            return hits[-1]
        raise ForecastServiceError(
            "无法确定账期：请显式传入 period=YYYYMM，或使用含账期的财报文件名"
        )

    @staticmethod
    def _save_upload(file_bytes: bytes, period: str, filename: str) -> Path:
        """保存上传文件到数据目录 forecast_uploads/，返回路径。"""
        from bdms.core.paths import DATA_DIR

        upload_dir = DATA_DIR / "forecast_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name
        stamp = time.strftime("%Y%m%d%H%M%S")
        target = upload_dir / f"{period}_{stamp}_{safe_name}"
        target.write_bytes(file_bytes)
        return target

    @staticmethod
    def _set_progress(job_id: int, step: str, pct: int) -> None:
        conn = _db.get_connection()
        try:
            _db.update_job_status(conn, job_id, "running", pct, step)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _set_done(job_id: int, report, result) -> None:
        issue_n = len(report.issues)
        note = f"完成：{result.line_count} 行；恒等式差异 {issue_n} 处" if issue_n else "完成"
        conn = _db.get_connection()
        try:
            _db.update_job_status(conn, job_id, "done", STEP_DONE[1], note)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _set_failed(job_id: int, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {exc}"[:500]
        conn = _db.get_connection()
        try:
            _db.update_job_status(conn, job_id, "failed", 0, message)
            conn.commit()
        finally:
            conn.close()
