"""交付统计看板 —— 服务层（模块4）。

职责：
  * 编排 engine 的各聚合查询，一次性组装成前端可直接渲染的图表数据
  * 把聚合结果缓存到 db_snapshot 表（唯一允许写的表）
  * 提供下钻穿透入口

与模块契约对齐：
    DashboardService(db_path).get_dashboard(month) -> dict
    DashboardService(db_path).refresh_snapshot(month) -> dict
    DashboardService(db_path).list_available_months() -> list[str]
    DashboardService(db_path).drill_down(...) -> dict
"""

import json
from pathlib import Path
from typing import Optional

from bdms.core import db as _db
from .engine import (
    DashboardEngine,
    MONTHS_2026,
    SHEET_SIGN,
    SHEET_EXCEPTION,
    SHEET_POC,
    COL_DEPT,
    COL_DELIVERY_STATUS,
)


class DashboardService:
    """看板编排服务。"""

    def __init__(self, db_path: Optional[Path] = None,
                 revenue_db_path: Optional[Path] = None):
        self.db_path = db_path
        self.engine = DashboardEngine(db_path, revenue_db_path)

    # ═══════ 汇总入口 ═══════

    def get_dashboard(self, month: str,
                      trend_months: Optional[list[str]] = None,
                      use_cache: bool = True) -> dict:
        """一次性返回看板全部图表数据（供 Web 调用）。

        结构：
          {
            "month": "202608",
            "available_months": [...],
            "kpis": {...},
            "monthly_trend": {...},
            "delivery_status_dist": {...},
            "delivery_status_dist_poc": {...},
            "exception_dist": {...},
            "exception_dist_by_team": {...},
            "dept_stats": {...},
            "drill_options": {...}   # 告诉前端哪些图表可下钻、维度名是什么
          }
        """
        if use_cache:
            cached = self._read_snapshot(month)
            if cached:
                return cached

        data = self._compute_all(month, trend_months)
        # 计算完成后自动落快照（best-effort，不阻塞返回）
        try:
            self._write_snapshot(month, data)
        except Exception:
            pass
        return data

    def _compute_all(self, month: str,
                     trend_months: Optional[list[str]] = None) -> dict:
        """实际计算全部图表数据。"""
        months = self.engine.list_available_months()
        trend_months = trend_months or MONTHS_2026

        return {
            "month": month,
            "available_months": months,
            "kpis": self.engine.compute_kpis(month),
            "monthly_trend": self.engine.compute_monthly_trend(trend_months),
            "delivery_status_dist": self.engine.compute_delivery_status_dist(
                month, sheet=SHEET_SIGN),
            "delivery_status_dist_poc": self.engine.compute_delivery_status_dist(
                month, sheet=SHEET_POC),
            "exception_dist": self.engine.compute_exception_dist(month, "type"),
            "exception_dist_by_team": self.engine.compute_exception_dist(month, "team"),
            "dept_stats": self.engine.compute_dept_stats(month),
            "drill_options": {
                "delivery_status_dist": {
                    "sheet": SHEET_SIGN, "dimension": "delivery_status"},
                "delivery_status_dist_poc": {
                    "sheet": SHEET_POC, "dimension": "delivery_status"},
                "exception_dist": {
                    "sheet": SHEET_EXCEPTION, "dimension": "exception_type"},
                "exception_dist_by_team": {
                    "sheet": SHEET_EXCEPTION, "dimension": "exception_team"},
                "dept_stats": {"sheet": SHEET_SIGN, "dimension": "dept"},
            },
        }

    # ═══════ 下钻 ═══════

    def drill_down(self, month: str, dimension: str, value: str,
                   sheet: Optional[str] = None, limit: int = 500) -> dict:
        """下钻穿透查询明细。sheet 缺省时按维度自动推断。"""
        if sheet is None:
            sheet = SHEET_EXCEPTION if dimension.startswith("exception") else SHEET_SIGN
        return self.engine.drill_down(month, sheet, dimension, value, limit=limit)

    # ═══════ 快照缓存（db_snapshot） ═══════

    SNAPSHOT_METRICS = [
        "kpis", "monthly_trend", "delivery_status_dist",
        "delivery_status_dist_poc", "exception_dist",
        "exception_dist_by_team", "dept_stats", "drill_options",
    ]

    def refresh_snapshot(self, month: str,
                         trend_months: Optional[list[str]] = None) -> dict:
        """强制重算并覆盖快照。"""
        data = self._compute_all(month, trend_months)
        self._write_snapshot(month, data, overwrite=True)
        return {
            "month": month,
            "metrics": list(self.SNAPSHOT_METRICS),
            "written": self._count_snapshot(month),
            "refreshed": True,
        }

    def _write_snapshot(self, month: str, data: dict,
                        overwrite: bool = True) -> None:
        """把聚合结果写入 db_snapshot（metric + dimension 唯一）。"""
        conn = _db.get_connection(self.db_path)
        try:
            if overwrite:
                conn.execute("DELETE FROM db_snapshot WHERE month = ?", (month,))
            for metric in self.SNAPSHOT_METRICS:
                if metric not in data:
                    continue
                payload = data[metric]
                # dimension 存维度标识（有 dimension 字段则用之，否则 None）
                dim = None
                if isinstance(payload, dict):
                    dim = payload.get("dimension")
                conn.execute(
                    """INSERT OR REPLACE INTO db_snapshot
                       (month, metric, dimension, value, extra, updated_at)
                       VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))""",
                    (month, metric, dim,
                     self._scalar_value(payload),
                     json.dumps(payload, ensure_ascii=False, default=str)),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _scalar_value(payload) -> Optional[float]:
        """从聚合结果里抽一个代表数值（便于 SQL 侧排序/筛选）。"""
        if isinstance(payload, dict):
            for key in ("total", "actual_revenue", "delivery_project_count"):
                v = payload.get(key)
                if isinstance(v, (int, float)):
                    return float(v)
        return None

    def _read_snapshot(self, month: str) -> Optional[dict]:
        """读取快照；缺任一 metric 视为未命中。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT metric, extra FROM db_snapshot WHERE month = ?", (month,)
            ).fetchall()
            if not rows:
                return None
            found = {r["metric"]: r["extra"] for r in rows}
            if not set(self.SNAPSHOT_METRICS) <= set(found):
                return None
            out = {
                metric: json.loads(found[metric])
                for metric in self.SNAPSHOT_METRICS
            }
            out["month"] = month
            out["available_months"] = self.engine.list_available_months()
            out["_cached"] = True
            return out
        finally:
            conn.close()

    def _count_snapshot(self, month: str) -> int:
        conn = _db.get_connection(self.db_path)
        try:
            return conn.execute(
                "SELECT COUNT(*) c FROM db_snapshot WHERE month = ?", (month,)
            ).fetchone()["c"]
        finally:
            conn.close()

    def clear_snapshot(self, month: Optional[str] = None) -> int:
        """清空快照（month=None 清全部）。返回删除行数。"""
        conn = _db.get_connection(self.db_path)
        try:
            if month:
                cur = conn.execute("DELETE FROM db_snapshot WHERE month = ?", (month,))
            else:
                cur = conn.execute("DELETE FROM db_snapshot")
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    # ═══════ 便捷查询 ═══════

    def list_available_months(self) -> list[str]:
        return self.engine.list_available_months()

    def get_kpis(self, month: str) -> dict:
        return self.engine.compute_kpis(month)
