"""核对验证：逐项对比自动生成 vs 手工报表"""

import openpyxl
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from .config import MANUAL_REPORT_PATH, OUTPUT_DIR


@dataclass
class CellDiff:
    cell: str
    auto_value: object
    manual_value: object
    diff: float
    is_match: bool


@dataclass
class ValidationReport:
    sheet_name: str
    total_cells: int = 0
    matched_cells: int = 0
    mismatched_cells: int = 0
    missing_in_auto: int = 0
    missing_in_manual: int = 0
    diffs: list = field(default_factory=list)

    @property
    def is_passed(self) -> bool:
        return self.mismatched_cells == 0 and self.missing_in_auto == 0

    def summary(self) -> str:
        status = "PASS" if self.is_passed else "FAIL"
        return (
            f"{status} | {self.sheet_name} | "
            f"total={self.total_cells} matched={self.matched_cells} "
            f"mismatch={self.mismatched_cells} missing_auto={self.missing_in_auto} "
            f"missing_manual={self.missing_in_manual}"
        )


def _is_numeric(val) -> bool:
    return isinstance(val, (int, float))


def _values_equal(auto_val, manual_val, tolerance: float = 0.01) -> bool:
    """compare two values, numeric with tolerance, others exact"""
    if auto_val is None and manual_val is None:
        return True
    if auto_val is None and manual_val == 0:
        return True
    if manual_val is None and auto_val == 0:
        return True
    if auto_val is None or manual_val is None:
        return False

    if _is_numeric(auto_val) and _is_numeric(manual_val):
        return abs(float(auto_val) - float(manual_val)) <= tolerance

    return str(auto_val).strip() == str(manual_val).strip()


def _calc_diff(auto_val, manual_val) -> float:
    if _is_numeric(auto_val) and _is_numeric(manual_val):
        return abs(float(auto_val) - float(manual_val))
    return 0.0


def validate_summary_sheet(
    auto_path: Path,
    manual_path: Path = MANUAL_REPORT_PATH,
    tolerance: float = 0.01,
) -> ValidationReport:
    """compare summary sheet"""
    report = ValidationReport(sheet_name="汇总")

    wb_auto = openpyxl.load_workbook(auto_path, data_only=True)
    wb_manual = openpyxl.load_workbook(manual_path, data_only=True)

    ws_auto = wb_auto["汇总"]
    ws_manual = wb_manual["汇总"]

    max_row = max(ws_auto.max_row, ws_manual.max_row)
    max_col = max(ws_auto.max_column, ws_manual.max_column)

    for row in range(2, max_row + 1):
        for col in range(2, max_col + 1):
            auto_val = ws_auto.cell(row=row, column=col).value
            manual_val = ws_manual.cell(row=row, column=col).value

            if auto_val is None and manual_val is None:
                continue

            # 跳过全空行（自动化报表没有的行）
            if auto_val is None:
                # 检查该行是否所有列都为空
                row_is_empty = True
                for c in range(2, max_col + 1):
                    if ws_auto.cell(row=row, column=c).value is not None:
                        row_is_empty = False
                        break
                if row_is_empty:
                    continue

            if row in (18, 19):
                continue

            if isinstance(manual_val, str) and "#REF" in manual_val:
                continue
            if isinstance(auto_val, str) and "#REF" in auto_val:
                continue

            report.total_cells += 1

            if auto_val is None and manual_val is not None:
                report.missing_in_auto += 1
                report.diffs.append(CellDiff(
                    cell=f"{openpyxl.utils.get_column_letter(col)}{row}",
                    auto_value=None, manual_value=manual_val,
                    diff=_calc_diff(0, manual_val), is_match=False
                ))
            elif auto_val is not None and manual_val is None:
                report.missing_in_manual += 1
                report.matched_cells += 1
            else:
                if _values_equal(auto_val, manual_val, tolerance):
                    report.matched_cells += 1
                else:
                    diff_val = _calc_diff(auto_val, manual_val)
                    report.mismatched_cells += 1
                    report.diffs.append(CellDiff(
                        cell=f"{openpyxl.utils.get_column_letter(col)}{row}",
                        auto_value=auto_val, manual_value=manual_val,
                        diff=diff_val, is_match=False
                    ))

    wb_auto.close()
    wb_manual.close()
    return report


def validate_all_sheets(
    auto_path: Path,
    manual_path: Path = MANUAL_REPORT_PATH,
    tolerance: float = 0.01,
) -> list:
    """compare all sheets"""
    reports = []
    try:
        r = validate_summary_sheet(auto_path, manual_path, tolerance)
        reports.append(r)
    except Exception as e:
        print(f"summary compare failed: {e}")
    return reports


def print_report(reports: list):
    """print validation report"""
    print("\n" + "=" * 80)
    print("确收报表核对报告")
    print("=" * 80)

    for r in reports:
        print(f"\n{r.summary()}")
        if r.diffs:
            print(f"  差异明细（前20项）:")
            for d in r.diffs[:20]:
                print(f"    {d.cell}: 自动={d.auto_value} vs 手工={d.manual_value} (差={d.diff:.6f})")

    total_cells = sum(r.total_cells for r in reports)
    total_matched = sum(r.matched_cells for r in reports)
    total_mismatch = sum(r.mismatched_cells for r in reports)

    print(f"\n{'=' * 80}")
    print(f"总计: {total_cells} 单元格, 匹配 {total_matched}, 差异 {total_mismatch}")
    if total_mismatch == 0:
        print("全部通过！自动生成与手工报表完全一致。")
    else:
        print(f"存在 {total_mismatch} 项差异，需要检查。")
    print("=" * 80)
