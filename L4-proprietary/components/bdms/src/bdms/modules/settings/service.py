"""【模块5】交付管理系统设定 —— 服务层（编排 + 写操作）。"""

from pathlib import Path
from typing import Any, Optional

from bdms.core import db as _db
from .engine import (
    SettingsEngine, SETTING_DEFS, DEFAULT_MONTHS_BACK, MIN_MONTHS_BACK,
    MAX_MONTHS_BACK, _parse_month,
)


class SettingsService:
    """系统设置服务：get_all / get / set / reset_defaults + 月份聚合。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else None
        self.engine = SettingsEngine(self.db_path)

    # ─── 建表兜底 ───

    def ensure_schema(self) -> None:
        _db.init_db(self.db_path)

    # ─── 查询 ───

    def get_all(self) -> dict:
        """读取所有设置。"""
        return self.engine.get_all()

    def get(self, key: str, default: Any = None) -> Any:
        """读取单个设置。"""
        return self.engine.get_raw(key, default)

    def describe(self) -> list[dict]:
        return self.engine.describe()

    def get_available_months(self, module: Optional[str] = None) -> list[str]:
        """从 report_month 表聚合已生成的月份（降序）。"""
        return self.engine.get_available_months(module)

    def get_month_coverage(self, module: Optional[str] = None) -> list[dict]:
        return self.engine.get_month_coverage(module)

    def get_effective_view(self) -> dict:
        """Web 层有效视图配置（默认月份、窗口、可选月份）。"""
        return self.engine.get_effective_view()

    # ─── 变更 ───

    def set(self, key: str, value: Any) -> dict:
        """写入单个设置（含类型校验/归一化）。

        返回 {"ok", "key", "value", "previous"}；校验失败抛 ValueError。
        """
        key = (key or "").strip()
        if not key:
            raise ValueError("key 不能为空")

        value = self._normalize(key, value)
        conn = _db.get_connection(self.db_path)
        try:
            previous = _db.get_settings(conn, key, None)
            desc = SETTING_DEFS.get(key, (None, None, None))[1]
            _db.upsert_settings(conn, key, value, desc)
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "key": key, "value": value, "previous": previous}

    def set_many(self, values: dict) -> dict:
        """批量写入。"""
        results = []
        for k, v in (values or {}).items():
            results.append(self.set(k, v))
        return {"ok": True, "count": len(results), "results": results}

    def sync_available_months(self) -> dict:
        """重算 view.available_months（从 report_month 聚合）并写回。"""
        months = self.engine.get_available_months()
        r = self.set("view.available_months", months)
        r["months"] = months
        return r

    def reset_defaults(self, keys: Optional[list[str]] = None) -> dict:
        """恢复默认值。keys=None 时恢复全部已知设置项。"""
        targets = keys if keys else list(SETTING_DEFS.keys())
        restored: dict[str, Any] = {}
        for k in targets:
            if k not in SETTING_DEFS:
                continue
            default = SETTING_DEFS[k][0]
            if k == "view.available_months":
                # 该值由数据推导，不用静态默认值覆盖
                default = self.engine.get_available_months()
            self.set(k, default)
            restored[k] = default
        return {"ok": True, "restored": restored}

    # ─── 校验 ───

    def _normalize(self, key: str, value: Any) -> Any:
        """按设置项类型归一化；未知 key 原样存。"""
        if key == "view.default_months_back":
            try:
                n = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"view.default_months_back 必须是整数: {value!r}")
            if not (MIN_MONTHS_BACK <= n <= MAX_MONTHS_BACK):
                raise ValueError(
                    f"view.default_months_back 必须在 {MIN_MONTHS_BACK}-{MAX_MONTHS_BACK} 之间: {n}"
                )
            return n

        if key == "view.default_month":
            if value in (None, "", "null"):
                return None
            m = _parse_month(value)
            if m is None:
                raise ValueError(f"view.default_month 必须是 YYYYMM: {value!r}")
            return m

        if key == "view.available_months":
            if value in (None, ""):
                return []
            if not isinstance(value, (list, tuple)):
                raise ValueError("view.available_months 必须是列表")
            out = []
            for m in value:
                parsed = _parse_month(m)
                if parsed:
                    out.append(parsed)
            return sorted(set(out), reverse=True)

        if key == "report.auto_overwrite":
            if isinstance(value, str):
                return value.strip().lower() in ("1", "true", "yes", "y", "on")
            return bool(value)

        if key == "report.excel_output_dir":
            s = str(value).strip() if value is not None else ""
            return s or "output"

        return value

    # ─── 摘要 ───

    def summary(self) -> dict:
        """设置页概览。"""
        return {
            "settings": self.get_all(),
            "items": self.describe(),
            "available_months": self.get_available_months(),
            "effective": self.get_effective_view(),
            "stats": self.engine.stats(),
        }
