# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""CalibrationService — 人工校准覆盖层（唯一校准口径）。

对齐 DESIGN-DETAIL-MANUAL-CALIBRATION-v1.0.md §2/§7：
- 原始 dr_sheet_row 永不修改；校准只写 dr_calibration(+history)。
- apply_overlays 是"原始 → effective"的唯一转换点，入参不被修改。
- 单次 upsert/revoke 与其 history 在一个事务内提交。
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from bdms.core import db as _db

_DATE_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")

# key = (sheet, row_index, column_name)
CellKey = Tuple[str, int, str]


class CalibrationError(Exception):
    """校准保存前置校验失败。code 映射 API 400。"""

    def __init__(self, message: str, code: str = "INVALID_VALUE",
                 value: Any = None):
        super().__init__(message)
        self.code = code
        self.value = value

    def to_dict(self) -> dict:
        """统一错误响应（对齐 DESIGN-DETAIL §4.8）。"""
        return {"detail": {"code": self.code, "message": str(self)}}


def _is_calibration_error(e) -> bool:
    return isinstance(e, CalibrationError)


class CalibrationService:
    """人工校准覆盖层服务。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    # ========================================================
    # 读取 / 解析
    # ========================================================
    def get_active_map(self, month: str) -> Dict[CellKey, Dict[str, Any]]:
        """返回 {(sheet,row_index,column_name): {corrected_value,operator,reason,updated_at}}。

        旧库未升级（无 dr_calibration 表）时返回空 —— 校准是增量能力，
        未建表时读取优雅降级（导出/浏览不崩）；写操作仍会正常报错。
        """
        conn = _db.get_connection(self.db_path)
        try:
            try:
                rows = _db.get_active_calibrations(conn, month)
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    return {}
                raise
        finally:
            conn.close()
        out: Dict[CellKey, Dict[str, Any]] = {}
        for r in rows:
            key = (r["sheet"], int(r["row_index"]), r["column_name"])
            out[key] = {
                "original_value": r["original_value"],
                "corrected_value": r["corrected_value"],
                "operator": r["operator"],
                "reason": r["reason"],
                "updated_at": r["updated_at"],
                "issue_id": r["issue_id"],
                "id": r["id"],
            }
        return out

    def apply_overlays(
        self,
        month: str,
        raw_sheets: Dict[str, pd.DataFrame],
    ) -> Dict[str, pd.DataFrame]:
        """把 active 校准覆盖到 raw DataFrame，返回 effective（不修改入参）。

        定位不到（行越界 / 列消失）只记 warnings，不抛异常中断整体。
        """
        active_map = self.get_active_map(month)
        warnings: List[Dict[str, str]] = []
        result: Dict[str, pd.DataFrame] = {}

        # 按 sheet 分组，避免对每个 sheet 遍历全部
        by_sheet: Dict[str, List[Tuple[CellKey, Dict[str, Any]]]] = {}
        for key, cal in active_map.items():
            by_sheet.setdefault(key[0], []).append((key, cal))

        for sheet, df in raw_sheets.items():
            eff = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
            for (s, row_index, col), cal in by_sheet.get(sheet, []):
                if col not in eff.columns:
                    warnings.append(
                        {"sheet": sheet, "row_index": row_index, "column_name": col,
                         "reason": "column_missing_after_regenerate"})
                    continue
                if not (0 <= row_index < len(eff)):
                    warnings.append(
                        {"sheet": sheet, "row_index": row_index, "column_name": col,
                         "reason": "row_out_of_range"})
                    continue
                coerced = _coerce_to_dtype(eff[col].dtype, cal["corrected_value"])
                eff.iat[row_index, eff.columns.get_loc(col)] = coerced
            result[sheet] = eff

        result["__warnings__"] = warnings  # type: ignore[assignment]
        return result

    # ========================================================
    # 写入
    # ========================================================
    def upsert(
        self,
        month: str,
        sheet: str,
        row_index: int,
        column_name: str,
        corrected_value: str,
        reason: str,
        operator: str,
        issue_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """新增/修改校准；修改时旧 corrected_value 入 history('revise')。"""
        if not reason or not str(reason).strip():
            raise CalibrationError("校准原因不能为空", code="EMPTY_REASON")
        if not operator or not str(operator).strip():
            raise CalibrationError("操作人不能为空", code="EMPTY_OPERATOR")
        self._assert_writable(month)

        corrected_value = "" if corrected_value is None else str(corrected_value).strip()
        self._validate_value(sheet, column_name, corrected_value)

        conn = _db.get_connection(self.db_path)
        try:
            self._check_busy(conn, month)
            self._check_locked(conn, month)
            existing = _db.get_calibration(
                conn, month, sheet, row_index, column_name)
            original_value = self._read_original(
                conn, month, sheet, row_index, column_name)

            if existing is None:
                cal_id = _db.insert_calibration(
                    conn, month, sheet, row_index, column_name,
                    original_value, corrected_value, reason, operator, issue_id)
                action = "created"
            else:
                cal_id = existing["id"]
                old_corrected = existing["corrected_value"]
                # 旧校准值入 history（revise），再更新当前行
                _db.insert_calibration_history(
                    conn, cal_id, month, sheet, row_index, column_name,
                    original_value, old_corrected,
                    existing["reason"], existing["operator"], "revise")
                _db.revise_calibration(conn, cal_id, corrected_value)
                # issue_id / reason / operator 在 revise 时也刷新
                conn.execute(
                    "UPDATE dr_calibration SET reason=?, operator=?, issue_id=? "
                    "WHERE id=?",
                    (reason, operator, issue_id, cal_id))
                action = "revised"

            # 回填关联 issue 的 corrected_value（不强制状态流转，状态由重校验驱动）
            if issue_id is not None:
                conn.execute(
                    "UPDATE dr_import_validation SET corrected_value=? "
                    "WHERE id=?",
                    (corrected_value, issue_id))

            conn.commit()
            return {"id": cal_id, "status": "active", "action": action}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def revoke(
        self,
        month: str,
        sheet: str,
        row_index: int,
        column_name: str,
        operator: str,
    ) -> Dict[str, Any]:
        """撤销：当前行置 revoked 并写 history('revoke')。"""
        self._assert_writable(month)
        conn = _db.get_connection(self.db_path)
        try:
            self._check_busy(conn, month)
            self._check_locked(conn, month)
            existing = _db.get_calibration(
                conn, month, sheet, row_index, column_name)
            if existing is None:
                raise CalibrationError(
                    "该单元格没有生效中的校准", code="NOT_FOUND")

            cal_id = existing["id"]
            original_value = self._read_original(
                conn, month, sheet, row_index, column_name)
            _db.insert_calibration_history(
                conn, cal_id, month, sheet, row_index, column_name,
                original_value, existing["corrected_value"],
                existing["reason"], existing["operator"], "revoke")
            _db.revoke_calibration(conn, cal_id)
            conn.commit()
            return {"id": cal_id, "status": "revoked"}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ========================================================
    # 查询 / 台账
    # ========================================================
    def list_calibrations(
        self,
        month: str,
        sheet: Optional[str] = None,
        row_index: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        conn = _db.get_connection(self.db_path)
        try:
            items = _db.list_calibrations(
                conn, month, sheet=sheet, row_index=row_index,
                status_filter=status)
        finally:
            conn.close()
        return {"month": month, "total": len(items), "items": items}

    def overview(self, month: str) -> Dict[str, Any]:
        conn = _db.get_connection(self.db_path)
        try:
            active = _db.get_active_calibrations(conn, month)
            revoked = _db.list_calibrations(
                conn, month, status_filter="revoked")
            pending = conn.execute(
                "SELECT COUNT(*) AS n FROM dr_import_validation "
                "WHERE month=? AND status='pending'",
                (month,)).fetchone()
            locked_row = conn.execute(
                "SELECT status FROM dr_review_status "
                "WHERE month=? AND status='approved'",
                (month,)).fetchone()
        finally:
            conn.close()

        by_sheet: Dict[str, int] = {}
        for r in active:
            by_sheet[r["sheet"]] = by_sheet.get(r["sheet"], 0) + 1

        return {
            "month": month,
            "active_calibrations": len(active),
            "revoked": len(revoked),
            "pending_issues": int(pending["n"]) if pending else 0,
            "by_sheet": by_sheet,
            "review_locked": bool(locked_row),
        }

    def ledger_rows(self, month: str) -> List[List[Any]]:
        """校准台账行（active + revoked，供导出 Sheet）。"""
        conn = _db.get_connection(self.db_path)
        try:
            items = _db.list_calibrations(conn, month)
        finally:
            conn.close()
        rows: List[List[Any]] = []
        for r in items:
            rows.append([
                month, r["sheet"], r["row_index"], r["column_name"],
                r["original_value"], r["corrected_value"], r["operator"],
                r["updated_at"], r["reason"], r["status"],
            ])
        return rows

    # ========================================================
    # 内部：原值读取 + 值校验
    # ========================================================
    def _assert_writable(self, month: str) -> None:
        """BR-06：月报 approved 后锁定校准，需先驳回。"""
        conn = _db.get_connection(self.db_path)
        try:
            row = conn.execute(
                "SELECT status FROM dr_review_status WHERE month=?", (month,),
            ).fetchone()
        finally:
            conn.close()
        if row and row["status"] == "approved":
            raise CalibrationError(
                f"月报 {month} 已审核通过，需先驳回才能校准", code="LOCKED")

    @staticmethod
    def _check_busy(conn: sqlite3.Connection, month: str) -> None:
        """409 忙锁：同一 month 的校准重校验 job 进行中，拒绝新写操作。"""
        running = conn.execute(
            "SELECT id FROM job WHERE module='calibration' AND month=? "
            "AND status='running' LIMIT 1",
            (month,),
        ).fetchone()
        if running:
            raise CalibrationError(
                "该月校准重校验进行中，请稍后重试",
                code="CALIBRATION_BUSY")

    @staticmethod
    def _check_locked(conn: sqlite3.Connection, month: str) -> None:
        """400 LOCKED：月报已 approved/exported 后禁止校准（需先驳回）。"""
        row = conn.execute(
            "SELECT status FROM dr_review_status WHERE month=?", (month,)
        ).fetchone()
        if row and row["status"] in ("approved", "exported"):
            raise CalibrationError(
                "该月报已审核通过，校准前请先驳回",
                code="LOCKED")

    @staticmethod
    def _read_original(
        conn: sqlite3.Connection,
        month: str,
        sheet: str,
        row_index: int,
        column_name: str,
    ) -> Optional[str]:
        """从 dr_sheet_row.data JSON 取该单元格原值（只读原始层）。"""
        row = conn.execute(
            "SELECT data FROM dr_sheet_row "
            "WHERE month=? AND sheet=? AND row_index=?",
            (month, sheet, row_index),
        ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            return None
        val = data.get(column_name)
        return None if val is None else str(val)

    def _infer_column_type(self, sheet: str, column_name: str) -> str:
        """从 dr_sheet_meta.columns 与列名推断 date/numeric/text。"""
        conn = _db.get_connection(self.db_path)
        try:
            # 取该 sheet 最近一次 meta（不限月，结构稳定）
            meta = conn.execute(
                "SELECT columns FROM dr_sheet_meta WHERE sheet=? "
                "ORDER BY month DESC LIMIT 1",
                (sheet,)).fetchone()
        finally:
            conn.close()

        columns: List[str] = []
        if meta:
            try:
                columns = json.loads(meta["columns"])
            except (ValueError, TypeError):
                columns = []

        # 列名启发（与 validator.collect_suspicious 同口径）
        if any(k in column_name for k in ("日期", "时间")):
            return "date"
        if any(k in column_name for k in ("金额", "数量", "天数", "人数", "成本")):
            return "numeric"
        return "text"

    def _validate_value(self, sheet: str, column_name: str,
                        value: str) -> None:
        """保存前置：类型 + 枚举校验。空串放行（表示清空，由非空规则管）。"""
        if value == "":
            return
        typ = self._infer_column_type(sheet, column_name)
        if typ == "date":
            if not _DATE_RE.match(value):
                raise CalibrationError(
                    f"日期格式非法：{value}（应为 YYYY-MM-DD）",
                    code="INVALID_TYPE", value=value)
            try:
                datetime.strptime(
                    value.replace("/", "-").replace(".", "-"), "%Y-%m-%d")
            except ValueError:
                raise CalibrationError(
                    f"日期不存在：{value}", code="INVALID_TYPE", value=value)
        elif typ == "numeric":
            if not _NUMERIC_RE.match(value):
                raise CalibrationError(
                    f"数值格式非法：{value}", code="INVALID_TYPE", value=value)
        # 枚举：仅 ENUM_COLS 映射列，允许集合与 validator 同源（legend_config）
        from bdms.modules.delivery_report.validator import get_enum_options
        allowed = get_enum_options(self.db_path, sheet, column_name)
        if allowed and value not in allowed:
            raise CalibrationError(
                f"枚举值非法：{value}（允许：{' / '.join(allowed)}）",
                code="INVALID_VALUE", value=value)


def _coerce_to_dtype(dtype, value: str):
    """按列 dtype 把校准文本写入 DataFrame，避免污染整列类型。"""
    if value == "":
        return None
    try:
        if pd.api.types.is_numeric_dtype(dtype):
            if "." in value:
                return float(value)
            return int(value)
    except (ValueError, OverflowError):
        return value
    return value
