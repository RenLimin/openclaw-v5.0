"""service — 确收分析服务层（幂等编排）。

契约：DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §9.2：
  - generate(period, mode) 三模式幂等（auto/read/regenerate）+ job 记录；
  - import_source / summary / caliber / trend / sources_available / list_periods；
  - caliber/trend 读 ra_caliber / ra_trend_row（结构化快照），无数据 fail-closed。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from bdms.core import db as _db
from bdms.modules.base import BaseService, MODE_AUTO, MODE_READ, MODE_REGENERATE

from .engine import RevenueAnalysisEngine
from .exporter import RevenueAnalysisExporter


class RevenueAnalysisService(BaseService):
    """确收分析服务层。"""

    module_name = "revenue_analysis"

    def __init__(self, db_path: Optional[Path] = None):
        self.engine = RevenueAnalysisEngine(db_path)
        # BaseService 组合模式：显式传 engine，meta_db 与 engine 同库
        super().__init__(module_name=self.module_name, engine=self.engine)

    def generate(self, period: str, mode: str = MODE_AUTO) -> dict:
        """幂等生成/读取 + 快照兜底。

        BaseService 骨架的 auto/read 路径在 has_data=True 时只读宽表，
        不写 ra_caliber/ra_trend_row/ra_period 快照；这里在 read 分支后
        检查快照缺失并补一次 compute+persist，保证双口径/趋势始终可查。
        """
        r = super().generate(period, mode)
        self._ensure_snapshots(period)
        return r

    def _ensure_snapshots(self, period: str) -> None:
        """若 ra_caliber 缺失（仅导入过宽表），补计算并落盘快照。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM ra_caliber WHERE period = ?", (period,)
            ).fetchone()[0]
        finally:
            conn.close()
        if n == 0:
            data = self.engine.compute(period)
            self.engine.persist(period, data, overwrite=True)

    # ─── 数据源 ───

    def import_source(self, period: str,
                      excel_path: Optional[Path] = None) -> dict:
        """导入财报源文件（预算执行表 + 底稿），返回导入统计。"""
        return self.engine.import_source(period, excel_path)

    def sources_available(self, period: str) -> bool:
        return self.engine.sources_available(period)

    def list_periods(self) -> list[str]:
        """已登记账期（ra_period），按期间倒序。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT period FROM ra_period ORDER BY period DESC"
            ).fetchall()
            return [r["period"] for r in rows]
        finally:
            conn.close()

    # ─── 查询 ───

    def summary(self, period: str) -> dict:
        """双口径汇总：ra_caliber 两行 + 差异。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT caliber, total, by_group, by_month FROM ra_caliber "
                "WHERE period = ? ORDER BY caliber", (period,),
            ).fetchall()
            if not rows:
                raise ValueError(f"{period} 无双口径数据，请先 generate")
            out: dict[str, Any] = {"period": period}
            for r in rows:
                out[r["caliber"]] = {
                    "total": r["total"],
                    "by_group": json.loads(r["by_group"]),
                    "by_month": json.loads(r["by_month"]),
                }
            out["difference"] = round(
                out["dynamic"]["total"] - out["locked"]["total"], 2)
            return out
        finally:
            conn.close()

    def caliber(self, period: str) -> dict:
        """双口径（兼容 §9.2 语义，返回与 engine.compute_dual_caliber 同构）。"""
        cal = self.summary(period)
        dyn_group = cal["dynamic"]["by_group"]
        return {
            "period": period,
            "locked": {
                **cal["locked"]["by_group"], "合计": cal["locked"]["total"],
            },
            "dynamic": {
                "DUE_2026": dyn_group.get("DUE_2026", 0.0),
                "IN_PIPELINE": dyn_group.get("IN_PIPELINE", 0.0),
                "OTHER_2027plus": dyn_group.get("OTHER_2027plus", 0.0),
                "MISSING": dyn_group.get("MISSING", 0.0),
                "合计": cal["dynamic"]["total"],
            },
            "difference": cal["difference"],
        }

    def trend(self, period: str) -> list[dict]:
        """预算趋势分析 19 行（ra_trend_row + R19 单元格）。"""
        conn = _db.get_connection(self.engine.db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM ra_trend_row WHERE period = ? "
                "ORDER BY row_index", (period,),
            ).fetchall()
            if not rows:
                raise ValueError(f"{period} 无趋势数据，请先 generate")
            cells = conn.execute(
                "SELECT row_index, col_index, value FROM ra_trend_cell "
                "WHERE period = ?", (period,),
            ).fetchall()
            cell_map = {(c["row_index"], c["col_index"]): c["value"]
                        for c in cells}
            out = []
            for r in rows:
                d = dict(r)
                d.pop("id", None)
                if r["row_index"] == 19:
                    rc = cell_map.get((19, 0))
                    if rc:
                        try:
                            d["recognize_rate_count"] = \
                                json.loads(rc).get("value")
                        except json.JSONDecodeError:
                            d["recognize_rate_count"] = None
                    ra = cell_map.get((19, 1))
                    if ra:
                        try:
                            d["recognize_rate_amount"] = \
                                json.loads(ra).get("value")
                        except json.JSONDecodeError:
                            d["recognize_rate_amount"] = None
                out.append(d)
            return out
        finally:
            conn.close()

    # ─── 导出 ───

    def export(self, period: str, out_path: Optional[Path] = None) -> Path:
        """导出 Excel（确认收入分析_{period}.xlsx）。"""
        return RevenueAnalysisExporter(self.engine.db_path).export(
            period, out_path)
