# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""DeliveryReportValidator — 交付月报原始数据校验器。

对齐 DESIGN-DETAIL-DELIVERY-REPORT-v2.1.md §3.2（12 条规则）+ Step 2 校验流程。
规则分类：
- 非空检查（必填字段）
- 数据类型检查（date/numeric/text）
- 枚举值检查（状态标志、类型编码）
- 行数合理性（与上月偏差 >20% 警告）
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from bdms.core import db as _db

# 各 Sheet 必填列（黄金基准解析结论）
REQUIRED_COLS: Dict[str, List[str]] = {
    "签约": ["合同编号", "项目名称", "所属产线", "签约日期"],
    "POC&提前实施": ["合同编号", "项目名称", "所属产线"],
    "异常项目": ["项目名称", "异常报备日期"],
    "确收交接": ["合同编号", "确收金额"],
    "验收交接": ["合同编号", "验收日期"],
}

# 枚举约束（黄金基准 Sheet-15 图例；业务列 → legend 列名）
# v1.0.1 订正：废弃不存在的「签约.履约状态」；仅启用真实数据验证过的映射
# （202606 真实 17177 行 100% 命中，见 DESIGN-DETAIL-MANUAL-CALIBRATION §2.3.1）。
# 新增枚举列必须先用真实数据做命中率分析（建议 ≥99%）并更新设计文档后启用。
ENUM_COLS: Dict[str, Dict[str, str]] = {
    "异常项目": {
        "状态": "状态",
    },
}

_DATE_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def get_enum_options(db_path, sheet: str, column: str) -> List[str]:
    """从 md_reference legend_config 读取枚举允许集合（保序去重）。

    仅对 ENUM_COLS 映射列生效；非映射列返回空（空集=不做枚举阻断，
    与校准保存前置的降级口径一致）。模块级函数供 validator 与
    CalibrationService 共用同一枚举源。
    """
    legend_col = ENUM_COLS.get(sheet, {}).get(column)
    if not legend_col:
        return []
    conn = _db.get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT extra FROM md_reference "
            "WHERE data_type='legend_config' AND enabled=1 "
            "ORDER BY sort_order").fetchall()
    finally:
        conn.close()
    options: List[str] = []
    seen = set()
    for r in rows:
        try:
            extra = json.loads(r["extra"])
        except (ValueError, TypeError):
            continue
        v = extra.get(legend_col, "")
        if isinstance(v, str) and v.strip() and v.strip() not in seen:
            seen.add(v.strip())
            options.append(v.strip())
    return options


class DeliveryReportValidator:
    """原始数据校验器（12 条规则）。"""

    def __init__(self, db_path=None):
        self.db_path = db_path

    # ========================================================
    # 单条规则
    # ========================================================

    def _load_enum_options(self, sheet: str, column: str) -> List[str]:
        """实例便捷方法：委托模块级 get_enum_options。"""
        return get_enum_options(self.db_path, sheet, column)

    def validate_not_null(self, df: pd.DataFrame,
                          required_cols: List[str]) -> List[Dict]:
        """R01-R05: 非空检查。返回 [{row, col, value}]。"""
        errors = []
        for col in required_cols:
            if col not in df.columns:
                errors.append({"row": -1, "col": col,
                               "issue": "missing_column", "value": None})
                continue
            for idx, v in df[col].items():
                if v is None or (isinstance(v, float) and pd.isna(v)) \
                        or (isinstance(v, str) and not v.strip()):
                    errors.append({"row": int(idx), "col": col,
                                   "issue": "null", "value": None})
        return errors

    def validate_data_type(self, df: pd.DataFrame,
                           col_types: Dict[str, str]) -> List[Dict]:
        """R06-R09: 数据类型检查（date/numeric/text）。"""
        errors = []
        for col, typ in col_types.items():
            if col not in df.columns:
                continue
            for idx, v in df[col].items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue  # 空值由非空规则管
                s = str(v).strip()
                if typ == "date" and not self._is_date(s):
                    errors.append({"row": int(idx), "col": col,
                                   "issue": "type_date", "value": s[:50]})
                elif typ == "numeric" and not self._is_numeric(s):
                    errors.append({"row": int(idx), "col": col,
                                   "issue": "type_numeric", "value": s[:50]})
        return errors

    def validate_enum(self, df: pd.DataFrame,
                      col_enums: Dict[str, List[str]]) -> List[Dict]:
        """R10: 枚举值检查。"""
        errors = []
        for col, allowed in col_enums.items():
            if col not in df.columns or not allowed:
                continue
            allowed_set = {str(a).strip() for a in allowed}
            for idx, v in df[col].items():
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                if str(v).strip() not in allowed_set:
                    errors.append({"row": int(idx), "col": col,
                                   "issue": "enum", "value": str(v)[:50]})
        return errors

    def validate_row_count(self, sheet: str, current: int, previous: int,
                           threshold: float = 0.2) -> Dict:
        """R11: 行数合理性（与上月偏差 >threshold 警告）。"""
        if previous <= 0:
            return {"sheet": sheet, "current": current, "previous": previous,
                    "warning": False, "deviation": 0.0}
        deviation = abs(current - previous) / previous
        return {
            "sheet": sheet,
            "current": current,
            "previous": previous,
            "warning": deviation > threshold,
            "deviation": round(deviation, 3),
        }

    def validate_duplicates(self, df: pd.DataFrame,
                            key_cols: List[str]) -> List[Dict]:
        """R12: 主键重复检查（如合同编号）。"""
        errors = []
        existing = [c for c in key_cols if c in df.columns]
        if not existing:
            return errors
        dup_mask = df.duplicated(subset=existing, keep=False)
        for idx in df[dup_mask].index:
            errors.append({
                "row": int(idx),
                "col": "+".join(existing),
                "issue": "duplicate",
                "value": str(df.loc[idx, existing[0]])[:50],
            })
        return errors

    # ========================================================
    # 存疑数据收集 + 人工调整
    # ========================================================

    def collect_suspicious(self, month: str,
                           sheets_data: Optional[Dict[str, pd.DataFrame]] = None) -> Dict:
        """收集某月全部存疑数据（从 DB 读原始数据）。

        Args:
            month: YYYYMM
            sheets_data: 可选，直接传入数据（否则从 DB 读）
        """
        if sheets_data is None:
            sheets_data = self._load_from_db(month)
        return self.collect_suspicious_from_df(month, sheets_data)

    def collect_suspicious_from_df(self, month: str,
                                   sheets_data: Dict[str, pd.DataFrame],
                                   only_sheets: Optional[set] = None) -> Dict:
        """对传入的数据集执行校验规则（规则单份实现，供校准重校验增量复用）。

        Args:
            month: YYYYMM
            sheets_data: 待校验的数据集（可为原始或校准后 effective）
            only_sheets: 只校验指定 Sheet 集合；None 表示全部
        """
        errors: List[Dict] = []
        warnings: List[Dict] = []

        for sheet, df in sheets_data.items():
            if only_sheets is not None and sheet not in only_sheets:
                continue
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            # 非空
            for e in self.validate_not_null(df, REQUIRED_COLS.get(sheet, [])):
                errors.append({"sheet": sheet, **e})
            # 类型（日期列）
            date_cols = {
                c: "date" for c in df.columns
                if isinstance(c, str) and any(k in c for k in ("日期", "时间"))
            }
            for e in self.validate_data_type(df, date_cols):
                errors.append({"sheet": sheet, **e})
            # 去重（合同编号）
            if sheet in ("签约", "确收交接", "验收交接"):
                for e in self.validate_duplicates(df, ["合同编号"]):
                    errors.append({"sheet": sheet, **e})
            # 行数合理性（与上月）
            prev = self._prev_month_rows(month, sheet)
            if prev:
                rc = self.validate_row_count(sheet, len(df), prev)
                if rc["warning"]:
                    warnings.append({
                        "sheet": sheet,
                        "row": -1,
                        "col": "",
                        "issue": f"行数偏差 {rc['deviation']*100:.0f}%"
                                 f"（上月 {prev}，本月 {len(df)}）",
                    })
            # 枚举（R10：仅 ENUM_COLS 映射列，从 legend 动态读允许集合）
            enum_map: Dict[str, List[str]] = {}
            for col in ENUM_COLS.get(sheet, {}):
                allowed = self._load_enum_options(sheet, col)
                if allowed:
                    enum_map[col] = allowed
            if enum_map:
                for e in self.validate_enum(df, enum_map):
                    errors.append({"sheet": sheet, **e})

        return {
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "total_errors": len(errors),
                "total_warnings": len(warnings),
            },
        }

    def apply_manual_fixes(self, month: str, fixes: List[Dict]) -> Dict:
        """[DEPRECATED] 旧人工调整路径 —— 已收敛到校准覆盖层。

        不再直接 UPDATE dr_sheet_row（原始行永不修改）；
        委托 CalibrationService.upsert 写校准表。保留签名兼容。
        """
        from .calibration import CalibrationService
        _cs = CalibrationService(self.db_path)
        applied = 0
        for fix in fixes:
            sheet = fix.get("sheet")
            row_index = fix.get("row_index")
            col = fix.get("col")
            if sheet is None or row_index is None or col is None:
                continue
            _cs.upsert(
                month, sheet, row_index, col,
                str(fix.get("value") or ""),
                str(fix.get("reason") or "legacy-manual-fix"),
                str(fix.get("operator") or "legacy"),
            )
            applied += 1
        return {"applied": applied, "total": len(fixes)}

    # ========================================================
    # 内部工具
    # ========================================================

    def _load_from_db(self, month: str) -> Dict[str, pd.DataFrame]:
        """从 DB 读某月数据。"""
        from bdms.modules.delivery_report.engine import DeliveryReportEngine
        engine = DeliveryReportEngine(self.db_path)
        try:
            return engine.load(month)
        except Exception:
            return {}

    def _prev_month_rows(self, month: str, sheet: str) -> int:
        """查上月某 Sheet 行数。"""
        y, m = int(month[:4]), int(month[4:6])
        if m == 1:
            prev = f"{y-1}12"
        else:
            prev = f"{y}{m-1:02d}"
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT row_count FROM dr_sheet_meta "
                "WHERE month = ? AND sheet = ?",
                (prev, sheet),
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0
        finally:
            conn.close()

    @staticmethod
    def _is_date(s: str) -> bool:
        if _DATE_RE.match(s):
            try:
                datetime.strptime(
                    s.replace("/", "-").replace(".", "-"), "%Y-%m-%d"
                )
                return True
            except ValueError:
                return False
        return False

    @staticmethod
    def _is_numeric(s: str) -> bool:
        return bool(_NUMERIC_RE.match(s))
