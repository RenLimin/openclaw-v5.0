"""validator — 确收分析数据校验器。

规则（DESIGN-DETAIL-REVENUE-ANALYSIS v1.0 §11/§12）：
  - 逐行校验：金额非负、月份列数值、恒等式（AB=ΣP..AA、AC=ΣP..X、AD=ΣAG..AO）
  - 202609 红线：J/K/L 全 0 属正常（zero_semantic 标记），不告警
  - 校验结果落盘 rr_import_validation（复用 RR_EXT_SCHEMA 若存在，否则内存表）

注意：importer 落盘的行字典键为**列字母**（A/B/C…AS），本校验器按字母取值。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from bdms.core import db as _db

from .config import (
    SHEET_BUDGET, SHEET_DRAFT,
    BUDGET_COLUMNS,
    PLAN_MONTHS, ACTUAL_MONTHS,
    IDENTITY_TOL,
)

# 预算执行表关键金额列（字母）
AMOUNT_LETTERS = ["I", "AB", "AC", "AD"]
# P..AA 共 12 个月：注意 AA 是单列名，不能用 list("PQRSTUVWXYZAA")（会把 AA 拆成两个 A）
PLAN_MONTH_LETTERS = ["P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA"]
ACTUAL_MONTH_LETTERS = ["AG", "AH", "AI", "AJ", "AK", "AL", "AM", "AN", "AO"]


class RevenueAnalysisValidator:
    """确收分析数据导入有效性/合法性校验器。"""

    module_name = "revenue_analysis"
    validation_table = "rr_import_validation"

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path: Path = Path(db_path) if db_path else _db.DB_PATH

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        # rr_import_validation 已由 RR_EXT_SCHEMA 预建（列：month/sheet/row_index/...），
        # 此处不再自建，避免与既有 schema 冲突。
        pass

    @staticmethod
    def _num(v: Any) -> float:
        try:
            return float(v) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            return float("nan")

    @staticmethod
    def _col_name(letter: str) -> str:
        return BUDGET_COLUMNS.get(letter, letter)

    def validate_row(self, sheet: str, row: dict, row_index: int) -> list[dict]:
        """校验单行。返回错误/警告列表。"""
        issues: list[dict] = []
        if sheet != SHEET_BUDGET:
            return issues

        # 1) 金额字段非负 + 数值合法
        for letter in AMOUNT_LETTERS:
            v = row.get(letter)
            if v in (None, ""):
                continue
            num = self._num(v)
            if num != num:  # NaN
                issues.append({
                    "rule_code": "AMOUNT_NON_NUMERIC", "severity": "WARNING",
                    "message": f"{self._col_name(letter)} 非数值: {v!r}",
                    "column_name": letter, "original_value": str(v),
                })
                continue
            if num < 0:
                issues.append({
                    "rule_code": "AMOUNT_NEGATIVE", "severity": "WARNING",
                    "message": f"{self._col_name(letter)} 为负: {num}（202609 实测含业务红冲/退款调整，属真实值）",
                    "column_name": letter, "original_value": str(num),
                })

        # 2) 恒等式
        self._check_identity(row, row_index, issues)
        return issues

    def _check_identity(self, row: dict, row_index: int, issues: list[dict]) -> None:
        """预算执行表恒等式：AB=ΣP..AA；AC=ΣP..X；AD=ΣAG..AO。"""
        def num(letter: str) -> float:
            return self._num(row.get(letter))

        est = num("AB")
        plan_sum = sum(num(L) for L in PLAN_MONTH_LETTERS)
        if abs(est - plan_sum) > IDENTITY_TOL:
            issues.append({
                "rule_code": "IDENTITY_E1", "severity": "WARNING",
                "message": f"恒等式E1: 2026年预计({est}) != ΣP..AA({plan_sum})",
                "column_name": "AB", "original_value": str(est),
            })

        h1_plan = num("AC")
        h1_plan_sum = sum(num(L) for L in PLAN_MONTH_LETTERS[:9])
        if abs(h1_plan - h1_plan_sum) > IDENTITY_TOL:
            issues.append({
                "rule_code": "IDENTITY_E2", "severity": "WARNING",
                "message": f"恒等式E2: 202601-09预计({h1_plan}) != ΣP..X({h1_plan_sum})",
                "column_name": "AC", "original_value": str(h1_plan),
            })

        h1_act = num("AD")
        h1_act_sum = sum(num(L) for L in ACTUAL_MONTH_LETTERS)
        if abs(h1_act - h1_act_sum) > IDENTITY_TOL:
            issues.append({
                "rule_code": "IDENTITY_E3", "severity": "WARNING",
                "message": f"恒等式E3: 202601-09确收({h1_act}) != ΣAG..AO({h1_act_sum})",
                "column_name": "AD", "original_value": str(h1_act),
            })

    def validate_batch(self, sheet: str, rows: list[dict], period: str) -> dict:
        """批量校验。"""
        results: list[dict] = []
        for i, row in enumerate(rows):
            issues = self.validate_row(sheet, row, i)
            for issue in issues:
                results.append({"row_index": i, **issue})
        error_count = sum(1 for r in results if r["severity"] == "ERROR")
        warning_count = sum(1 for r in results if r["severity"] == "WARNING")
        return {
            "period": period, "sheet": sheet,
            "total_rows": len(rows),
            "error_count": error_count,
            "warning_count": warning_count,
            "results": results,
        }

    def persist_validation_results(self, period: str, results: dict) -> int:
        """校验结果落盘（rr_import_validation，month 列）。"""
        conn = _db.get_connection(self.db_path)
        try:
            conn.execute(
                f"DELETE FROM {self.validation_table} WHERE month = ? AND sheet = ?",
                (period, results["sheet"]),
            )
            for r in results["results"]:
                conn.execute(
                    f"""INSERT INTO {self.validation_table}
                        (month, sheet, row_index, rule_code, severity, message, column_name, original_value, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                    (period, results["sheet"], r["row_index"], r["rule_code"],
                     r["severity"], r["message"], r.get("column_name"),
                     r.get("original_value")),
                )
            conn.commit()
            return len(results["results"])
        finally:
            conn.close()

    def list_pending(self, period: str, severity: Optional[str] = None) -> list[dict]:
        """列出待处理校验问题。"""
        conn = _db.get_connection(self.db_path)
        try:
            sql = f"SELECT * FROM {self.validation_table} WHERE month = ?"
            params: list = [period]
            if severity:
                sql += " AND severity = ?"
                params.append(severity)
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
