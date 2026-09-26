# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""DashboardCustomizationService — 驾驶舱视图管理（多看板/多驾驶舱）。

对齐 DESIGN-DETAIL-DASHBOARD-v2.1.md §6.2 + db_view_config 表结构
（view_id TEXT / layout / filters / chart_types 分列存储）。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from bdms.core.db import get_connection


class DashboardCustomizationService:
    """视图管理服务。"""

    PRESET_VIEWS = {
        "default": {
            "name": "默认驾驶舱",
            "description": "交付月报 + 确收分析月报统计汇总",
            "layout": ["kpi", "delivery", "revenue", "profit", "risk"],
        },
        "management": {
            "name": "管理视图",
            "description": "全量 KPI + 风险",
            "layout": ["kpi", "risk", "profit", "delivery", "revenue"],
        },
        "delivery": {
            "name": "交付视图",
            "description": "交付月报为主",
            "layout": ["delivery", "kpi", "risk"],
        },
        "revenue": {
            "name": "确收视图",
            "description": "确收分析为主",
            "layout": ["revenue", "kpi", "profit"],
        },
        "profit": {
            "name": "利润视图",
            "description": "成本/利润/毛利率",
            "layout": ["profit", "kpi", "revenue"],
        },
    }

    AVAILABLE_METRICS = [
        "sign_count", "sign_amount", "poc_count", "exception_count",
        "revenue_actual", "revenue_plan", "revenue_diff_rate",
        "cost_total", "profit_total", "profit_margin",
        "risk_open", "risk_critical",
    ]

    AVAILABLE_CHART_TYPES = ["line", "bar", "pie", "table", "kpi_card"]

    def __init__(self, db_path=None):
        self.db_path = db_path

    # ========================================================
    # 视图 CRUD（对齐 db_view_config 表）
    # ========================================================

    def create_view(self, user_id: str, view_name: str,
                    config: Dict, set_default: bool = False) -> Dict:
        """创建新视图。

        config: {"layout": [...], "filters": {...}, "chart_types": {...}}
        """
        if not view_name or not view_name.strip():
            raise ValueError("view_name is required")

        view_id = f"view_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        conn = get_connection(self.db_path)
        try:
            if set_default:
                conn.execute(
                    "UPDATE db_view_config SET is_default = 0 WHERE user_id = ?",
                    (user_id,))
            cur = conn.execute(
                """INSERT INTO db_view_config
                   (view_id, view_name, user_id, is_default,
                    layout, filters, chart_types, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (view_id, view_name.strip(), user_id,
                 1 if set_default else 0,
                 json.dumps(config.get("layout", []), ensure_ascii=False),
                 json.dumps(config.get("filters", {}), ensure_ascii=False),
                 json.dumps(config.get("chart_types", {}), ensure_ascii=False),
                 datetime.now().isoformat(), datetime.now().isoformat()),
            )
            conn.commit()
            return {"id": cur.lastrowid, "view_id": view_id,
                    "view_name": view_name, "is_default": set_default}
        finally:
            conn.close()

    def update_view(self, view_id: str, config: Dict) -> Dict:
        """更新视图配置（view_id 为 TEXT 标识）。"""
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """UPDATE db_view_config
                   SET layout = ?, filters = ?, chart_types = ?, updated_at = ?
                   WHERE view_id = ? AND deleted_at IS NULL""",
                (json.dumps(config.get("layout", []), ensure_ascii=False),
                 json.dumps(config.get("filters", {}), ensure_ascii=False),
                 json.dumps(config.get("chart_types", {}), ensure_ascii=False),
                 datetime.now().isoformat(), view_id),
            )
            if cur.rowcount == 0:
                raise ValueError(f"视图 {view_id} 不存在")
            conn.commit()
            return {"view_id": view_id, "updated": True}
        finally:
            conn.close()

    def delete_view(self, view_id: str) -> Dict:
        """删除视图（软删除）。"""
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                "UPDATE db_view_config SET deleted_at = ? "
                "WHERE view_id = ? AND deleted_at IS NULL",
                (datetime.now().isoformat(), view_id))
            if cur.rowcount == 0:
                raise ValueError(f"视图 {view_id} 不存在")
            conn.commit()
            return {"view_id": view_id, "deleted": True}
        finally:
            conn.close()

    def get_view(self, view_id: str) -> Optional[Dict]:
        """获取视图配置。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM db_view_config "
                "WHERE view_id = ? AND deleted_at IS NULL",
                (view_id,),
            ).fetchone()
            return self._to_view(row) if row else None
        finally:
            conn.close()

    def list_views(self, user_id: str) -> List[Dict]:
        """列出用户所有视图（默认在前）。"""
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """SELECT * FROM db_view_config
                   WHERE user_id = ? AND deleted_at IS NULL
                   ORDER BY is_default DESC, id""",
                (user_id,),
            ).fetchall()
            return [self._to_view(r) for r in rows]
        finally:
            conn.close()

    def set_default_view(self, view_id: str, user_id: str) -> Dict:
        """设置默认视图。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM db_view_config "
                "WHERE view_id = ? AND user_id = ? AND deleted_at IS NULL",
                (view_id, user_id),
            ).fetchone()
            if not row:
                raise ValueError(f"视图 {view_id} 不属于用户 {user_id}")
            conn.execute(
                "UPDATE db_view_config SET is_default = 0 WHERE user_id = ?",
                (user_id,))
            conn.execute(
                "UPDATE db_view_config SET is_default = 1 WHERE view_id = ?",
                (view_id,))
            conn.commit()
            return {"view_id": view_id, "is_default": True}
        finally:
            conn.close()

    def get_default_view(self, user_id: str) -> Optional[Dict]:
        """获取用户的默认视图（无则返回内置默认）。"""
        conn = get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM db_view_config "
                "WHERE user_id = ? AND is_default = 1 AND deleted_at IS NULL",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()
        if row:
            return self._to_view(row)
        return {
            "view_id": "builtin_default",
            "user_id": user_id,
            "view_name": self.PRESET_VIEWS["default"]["name"],
            "config": self.PRESET_VIEWS["default"],
            "is_default": True,
        }

    def apply_preset(self, preset_key: str, user_id: str) -> Dict:
        """应用预置视图模板（创建为新视图）。"""
        if preset_key not in self.PRESET_VIEWS:
            raise ValueError(
                f"未知预置模板: {preset_key}。可选: {list(self.PRESET_VIEWS)}")
        preset = self.PRESET_VIEWS[preset_key]
        return self.create_view(
            user_id, preset["name"],
            {"layout": preset["layout"]}, set_default=False)

    # ========================================================
    # 内部工具
    # ========================================================

    @staticmethod
    def _to_view(row) -> Dict:
        """行 → 视图 dict（合并 layout/filters/chart_types 为 config）。"""
        v = dict(row)
        config = {
            "layout": json.loads(v.pop("layout", "[]") or "[]"),
            "filters": json.loads(v.pop("filters", "{}") or "{}"),
            "chart_types": json.loads(v.pop("chart_types", "{}") or "{}"),
        }
        v["config"] = config
        return v
