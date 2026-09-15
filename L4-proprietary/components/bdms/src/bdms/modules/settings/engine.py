"""【模块5】交付管理系统设定 —— 引擎层（纯查询，无副作用）。

关键设置项：
  view.default_months_back   默认显示数据跨度（月）
  view.default_month         默认选中月份（None = 自动取最新已生成月）
  view.available_months      可选月份列表（从 report_month 表自动汇总）
  report.auto_overwrite      自动覆盖
  report.excel_output_dir    Excel 输出目录

设置值统一以 JSON 文本存 sys_settings.value，读取时反序列化，
因此整型/布尔/列表都能原样往返。
"""

from pathlib import Path
from typing import Any, Optional

from bdms.core import db as _db


# 已知设置项定义：key → (默认值, 中文说明, 类型)
SETTING_DEFS: dict[str, tuple] = {
    "view.default_months_back": (12, "默认显示数据跨度（月）", int),
    "view.default_month": (None, "默认选中月份（YYYYMM，None=自动取最新）", str),
    "view.available_months": ([], "可选月份列表（自动汇总）", list),
    "report.auto_overwrite": (False, "生成报表时自动覆盖已有数据", bool),
    "report.excel_output_dir": ("output", "Excel 输出目录", str),
}

DEFAULT_MONTHS_BACK = 12
MIN_MONTHS_BACK = 1
MAX_MONTHS_BACK = 120


def _parse_month(month: Any) -> Optional[str]:
    """归一化月份为 YYYYMM 字符串；非法返回 None。"""
    if month is None:
        return None
    s = str(month).strip().replace("-", "").replace("/", "")
    if len(s) == 6 and s.isdigit():
        return s
    return None


def month_minus(month: str, n: int) -> str:
    """月份减 n 个月（YYYYMM）。"""
    m = _parse_month(month)
    if m is None:
        raise ValueError(f"非法月份: {month}")
    y, mo = int(m[:4]), int(m[4:])
    total = y * 12 + (mo - 1) - n
    return f"{total // 12:04d}{total % 12 + 1:02d}"


def month_diff(later: str, earlier: str) -> int:
    """later - earlier 的月份差。"""
    a, b = _parse_month(later), _parse_month(earlier)
    if a is None or b is None:
        raise ValueError(f"非法月份: {later} / {earlier}")
    return (int(a[:4]) * 12 + int(a[4:])) - (int(b[:4]) * 12 + int(b[4:]))


class SettingsEngine:
    """系统设置引擎 —— 只读查询。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else None

    # ─── 基础读写（薄封装，无副作用）───

    def get_raw(self, key: str, default: Any = None) -> Any:
        conn = _db.get_connection(self.db_path)
        try:
            val = _db.get_settings(conn, key, default)
        finally:
            conn.close()
        return self._coerce(key, val)

    @staticmethod
    def _coerce(key: str, val: Any) -> Any:
        """类型纠偏。

        背景：sys_settings.value 是 TEXT，写入时 json.dumps。json.dumps("202608")
        得到 '"202608"'，但 json.dumps 对**纯数字字符串**之外的场景没问题；
        真正的坑是历史数据/手工写入的裸值（如 value="202608" 未加引号），
        json.loads 会把它解析成 int 202608。这里按设置项声明的类型纠偏，
        保证「月份永远是 str」「跨度永远是 int」。
        """
        if val is None:
            return None
        declared = SETTING_DEFS.get(key)
        if not declared:
            return val
        typ = declared[2]
        if typ is str:
            return None if val is None else str(val)
        if typ is int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return declared[0]
        if typ is bool:
            if isinstance(val, str):
                return val.strip().lower() in ("1", "true", "yes", "y", "on")
            return bool(val)
        if typ is list:
            if isinstance(val, (list, tuple)):
                return list(val)
            return [val] if val else []
        return val

    def get_all(self) -> dict:
        """读取所有设置（缺失的已知项用默认值补齐）。"""
        conn = _db.get_connection(self.db_path)
        try:
            vals = _db.get_all_settings(conn)
        finally:
            conn.close()
        out = dict(_db.DEFAULT_SETTINGS)
        out.update(vals)
        # 已知定义兜底
        for k, (dv, _, _) in SETTING_DEFS.items():
            out.setdefault(k, dv)
        return out

    def describe(self) -> list[dict]:
        """设置项清单（含当前值、默认值、类型、说明）。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT key, value, description, updated_at FROM sys_settings "
                "ORDER BY key"
            ).fetchall()
            raw = {r["key"]: dict(r) for r in rows}
        finally:
            conn.close()

        current = self.get_all()
        out = []
        for key, (dv, desc, typ) in SETTING_DEFS.items():
            meta = raw.get(key, {})
            out.append({
                "key": key,
                "value": current.get(key),
                "default": dv,
                "type": typ.__name__,
                "description": meta.get("description") or desc,
                "updated_at": meta.get("updated_at"),
                "persisted": key in raw,
            })
        # 额外未知 key 也列出，避免隐藏设置
        for key, meta in raw.items():
            if key in SETTING_DEFS:
                continue
            out.append({
                "key": key, "value": current.get(key), "default": None,
                "type": type(current.get(key)).__name__, "description": meta.get("description"),
                "updated_at": meta.get("updated_at"), "persisted": True,
            })
        return out

    # ─── 领域查询 ───

    def get_available_months(self, module: Optional[str] = None) -> list[str]:
        """从 report_month 表聚合已生成月份（降序）。"""
        conn = _db.get_connection(self.db_path)
        try:
            if module:
                rows = conn.execute(
                    "SELECT DISTINCT month FROM report_month WHERE module = ? "
                    "ORDER BY month DESC", (module,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT month FROM report_month ORDER BY month DESC"
                ).fetchall()
            return [r["month"] for r in rows]
        finally:
            conn.close()

    def get_month_coverage(self, module: Optional[str] = None) -> list[dict]:
        """月份覆盖明细：{month, modules: [...], generated_at}。"""
        conn = _db.get_connection(self.db_path)
        try:
            if module:
                rows = conn.execute(
                    "SELECT month, module, generated_at, row_counts FROM report_month "
                    "WHERE module = ? ORDER BY month DESC", (module,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT month, module, generated_at, row_counts FROM report_month "
                    "ORDER BY month DESC"
                ).fetchall()
        finally:
            conn.close()

        agg: dict[str, dict] = {}
        for r in rows:
            m = r["month"]
            e = agg.setdefault(m, {"month": m, "modules": [], "generated_at": None})
            e["modules"].append(r["module"])
            if not e["generated_at"] or (r["generated_at"] or "") > e["generated_at"]:
                e["generated_at"] = r["generated_at"]
        return list(agg.values())

    def resolve_default_month(self, available: Optional[list[str]] = None) -> Optional[str]:
        """解析有效默认月份：配置值有效则用之，否则取最新已生成月份。"""
        avail = available if available is not None else self.get_available_months()
        configured = _parse_month(self.get_raw("view.default_month",
                                               _db.DEFAULT_SETTINGS.get("view.default_month")))
        if configured and configured in avail:
            return configured
        return avail[0] if avail else configured

    def get_effective_view(self) -> dict:
        """Web 层直接可用的有效视图配置（默认月份 + 跨度窗口）。"""
        avail = self.get_available_months()
        months_back = self.get_raw("view.default_months_back", DEFAULT_MONTHS_BACK)
        try:
            months_back = int(months_back)
        except (TypeError, ValueError):
            months_back = DEFAULT_MONTHS_BACK
        default_month = self.resolve_default_month(avail)

        if default_month:
            earliest = month_minus(default_month, months_back - 1)
            window = [m for m in avail
                      if months_back > 0 and earliest <= m <= default_month]
            window.sort()
        else:
            window = sorted(avail)

        return {
            "default_month": default_month,
            "default_months_back": months_back,
            "available_months": avail,
            "month_window": window,
            "earliest_month": window[0] if window else None,
            "latest_month": avail[0] if avail else None,
        }

    def get_available_months_synced(self) -> list[str]:
        """month=available_months 的自动同步值（供 set 时刷新）。"""
        return self.get_available_months()

    def stats(self) -> dict:
        """按模块统计月份覆盖数。"""
        conn = _db.get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT module, COUNT(DISTINCT month) AS months, "
                "MIN(month) AS earliest, MAX(month) AS latest "
                "FROM report_month GROUP BY module ORDER BY module"
            ).fetchall()
            return {"modules": [dict(r) for r in rows],
                    "total_months": len(self.get_available_months())}
        finally:
            conn.close()
