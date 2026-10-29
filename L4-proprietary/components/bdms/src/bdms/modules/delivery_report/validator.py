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

# 各 Sheet 必填列。
# v1.1 订正（2026-10-29，对齐 202606 真实宽表 schema，17181 行实测）：
#   旧值照黄金基准精简 demo 表列名编写，与真实导出（76 列宽表）严重错位，
#   导致 2.5 万条误报。以下列名均来自真实 dr_sheet_row.data 表头且空值率为 0。
#   - 签约/异常项目实为本月全部履约项导出（行数相等 17181/17177），不是仅异常行；
#   - POC 的「销售合同编号」「BI履约ID」大量为空属正常（未关联合同），不设必填；
#   - 异常项目「异常报备日期」仅对真正异常行有值，全量导出时整列空 → 不设必填。
REQUIRED_COLS: Dict[str, List[str]] = {
    "签约": ["ID", "销售合同编号", "标题", "所属产线", "立项日期"],
    "POC&提前实施": ["ID", "标题", "所属产线", "立项日期"],
    "异常项目": ["ID", "销售合同编号", "客户名称", "标题", "状态"],
    "确收交接": ["ID", "合同编号", "客户名称", "交接日期", "标题"],
    "验收交接": ["ID", "合同编号", "客户名称", "交接日期", "标题"],
}

# 业务唯一键（去重）。
# v1.1：真实宽表里同一合同编号在确收/验收表天然多行（一合同多履约项/多次交接），
# 不能拿「合同编号」当唯一键（旧规则误报 876 行）。履约项粒度的唯一键是 ID；
# 同一 ID 对应不同合同/日期才是真异常（实测确收/验收各 8 行，需人工核对）。
DUP_KEYS: Dict[str, List[str]] = {
    "签约": ["ID"],
    "POC&提前实施": ["ID"],
    "异常项目": ["ID"],
    "确收交接": ["ID"],
    "验收交接": ["ID"],
}

# 源系统哨兵值：语义等同"空"，不作为必填缺失或类型非法逐条人工处理。
# （#N/A、Excel 零时刻 00:00:00、NaN/NaT 等，多为公式/导出产物）
_SENTINELS = {
    "", "#n/a", "nan", "nat", "#ref!", "#value!", "#div/0!",
    "null", "none", "00:00:00", "00:00:00.0", "-",
}

_DATE_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
# 带时间后缀：2025-11-14 00:00:00（可截断为日期，视为合法）
_DATE_TIME_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}[ T]\d{1,2}:\d{2}(:\d{1,2})?$")
# Excel 浮点日期序列：20260609.0（YYYYMMDD，可转日期，视为合法）
_DATE_FLOAT8_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(\.0+)?$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")

# 枚举约束（黄金基准 Sheet-15 图例；业务列 → legend 列名）
# v1.0.1 订正：废弃不存在的「签约.履约状态」；仅启用真实数据验证过的映射
# （202606 真实 17177 行 100% 命中，见 DESIGN-DETAIL-MANUAL-CALIBRATION §2.3.1）。
# 新增枚举列必须先用真实数据做命中率分析（建议 ≥99%）并更新设计文档后启用。
ENUM_COLS: Dict[str, Dict[str, str]] = {
    "异常项目": {
        "状态": "状态",
    },
}




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

    @staticmethod
    def _is_empty(v: Any) -> bool:
        """统一空值判定：None / NaN / 空白 / 源系统哨兵值。"""
        if v is None:
            return True
        if isinstance(v, float) and pd.isna(v):
            return True
        s = str(v).strip()
        if not s:
            return True
        return s.lower() in _SENTINELS

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
                if self._is_empty(v):
                    errors.append({"row": int(idx), "col": col,
                                   "issue": "null",
                                   "value": None if v is None else str(v)[:50]})
        return errors

    def validate_data_type(self, df: pd.DataFrame,
                           col_types: Dict[str, str]) -> List[Dict]:
        """R06-R09: 数据类型检查（date/numeric）。

        v1.1：哨兵值（#N/A / 00:00:00 等）语义为空，跳过（空值归非空规则）；
        日期宽容接受「带时间后缀」与「Excel float YYYYMMDD」两种可规范化形态。
        """
        errors = []
        for col, typ in col_types.items():
            if col not in df.columns:
                continue
            for idx, v in df[col].items():
                if self._is_empty(v):
                    continue  # 空/哨兵由非空规则管
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
                if self._is_empty(v):
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
            # 业务唯一键去重（v1.1：履约项粒度 ID，非合同编号）
            key_cols = DUP_KEYS.get(sheet)
            if key_cols:
                for e in self.validate_duplicates(df, key_cols):
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
        """宽容日期判定：ISO 分隔 / 带时间后缀 / Excel float(YYYYMMDD)。"""
        s = str(s).strip()
        if _DATE_RE.match(s):
            try:
                datetime.strptime(s.replace("/", "-").replace(".", "-"),
                                  "%Y-%m-%d")
                return True
            except ValueError:
                return False
        if _DATE_TIME_RE.match(s):
            head = re.split(r"[ T]", s, 1)[0]
            try:
                datetime.strptime(head.replace("/", "-").replace(".", "-"),
                                  "%Y-%m-%d")
                return True
            except ValueError:
                return False
        mf = _DATE_FLOAT8_RE.match(s)
        if mf:
            mo, da = int(mf.group(2)), int(mf.group(3))
            return 1 <= mo <= 12 and 1 <= da <= 31
        return False

    @staticmethod
    def _is_numeric(s: str) -> bool:
        return bool(_NUMERIC_RE.match(str(s).strip()))
