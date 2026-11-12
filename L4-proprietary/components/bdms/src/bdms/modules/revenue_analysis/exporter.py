"""exporter — 确收分析 Excel 导出（10 Sheet + 样式规范）。

契约：DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 §9.3 / §10：
  - 输出 output/确认收入分析_{period}.xlsx；
  - Sheet 顺序：预算执行表 → 计划确收底稿 → 汇总 → 汇总分析 →
    预算趋势分析 → 确收差异分析 → 重拆履约 → 图例 → 月度汇总记录 → 履约汇总记录；
  - 样式：微软雅黑、主表头 FF4472C4 白字 bold、子表头 FFD9E1F2、
    数据 FFD9D9D9 薄边框、金额 #,##0.00、完成率 0.0000、万元金额 #,##0.00；
  - 预算趋势分析金额列受 202609 J/K/L 全 0 红线 → 输出空（不硬摊）。

数据全部来自 rr_sheet_row / ra_trend_row / ra_trend_cell（不重算、不读财报）。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Union

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from bdms.core.paths import DB_PATH, output_path
from bdms.modules.base import ExportError

from .config import (
    SHEET_BUDGET, SHEET_DRAFT, SHEET_SUMMARY, SHEET_SUMMARY_ANALYSIS,
    SHEET_TREND, SHEET_DIFF, SHEET_RESTRUCTURE, SHEET_LEGEND,
    SHEET_MONTHLY_RECORD, SHEET_PERF_RECORD,
    BUDGET_COLUMNS, BUDGET_COLUMNS_202606, DRAFT_COLUMNS, COMPUTED_COLUMNS,
    LEDGER_HEADERS, AMOUNT_UNIT_TREND,
)

# ─── 样式常量（§10）───

FONT_NAME = "微软雅黑"
HEADER_FILL = "4472C4"       # 主表头深蓝
SUBHEADER_FILL = "D9E1F2"    # 子表头浅蓝
BORDER_COLOR = "D9D9D9"      # 浅灰边框
FMT_AMOUNT = "#,##0.00"
FMT_RATE = "0.0000"
FMT_INT = "#,##0"

# 预算趋势分析 17 列表头（§5.2）
TREND_HEADERS = [
    "期间", "类型",
    "期初-合同数量", "期初-涉及金额(万)",
    "本年正常交付-合同数量", "本年正常交付-涉及金额(万)",
    "异常中-合同数量", "异常中-涉及金额(万)",
    "合同消失-合同数量", "合同消失-涉及金额(万)",
    "未来交付-合同数量", "未来交付-涉及金额(万)",
    "校验-数量", "校验-金额(万)",
    "异常说明-未立项", "异常说明-已立项", "",
]

# 汇总 13 列（§4.3）
SUMMARY_HEADERS = [
    "", "期间", "新签合同额",
    "新签-预计确收", "新签-实际确收", "新签-完成率",
    "递延-预计确收", "递延-实际确收", "递延-完成率",
    "合计-预计确收", "合计-实际确收", "合计-完成率", "校验",
]


class RevenueAnalysisExporter:
    """确收分析 Excel 导出器。"""

    module_name = "revenue_analysis"

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = Path(db_path) if db_path else DB_PATH

    # ─── 主入口 ───

    def export(self, period: str, out_path: Optional[Path] = None) -> Path:
        """导出 Excel 文件。"""
        try:
            from bdms.core import db as _db
            conn = _db.get_connection(self.db_path)
            try:
                wb = Workbook()
                if wb.active:
                    wb.remove(wb.active)
                self._write_all_sheets(wb, period, conn)
            finally:
                conn.close()

            if out_path:
                target = Path(out_path)
            else:
                target = output_path(f"确认收入分析_{period}.xlsx")
            target.parent.mkdir(parents=True, exist_ok=True)
            wb.save(target)
            return target
        except Exception as e:
            raise ExportError(f"导出失败: {e}", details={"period": period}) from e

    # ─── Sheet 编排 ───

    def _write_all_sheets(self, wb: Workbook, period: str, conn: Any) -> None:
        self._write_sheet_rows(wb, period, conn, SHEET_BUDGET)
        self._write_sheet_rows(wb, period, conn, SHEET_DRAFT)
        self._write_summary(wb, period, conn)
        self._write_summary_analysis(wb, period, conn)
        self._write_trend(wb, period, conn)
        self._write_sheet_rows(wb, period, conn, SHEET_DIFF)
        self._write_sheet_rows(wb, period, conn, SHEET_RESTRUCTURE)
        self._write_sheet_rows(wb, period, conn, SHEET_LEGEND)
        self._write_sheet_rows(wb, period, conn, SHEET_MONTHLY_RECORD)
        self._write_sheet_rows(wb, period, conn, SHEET_PERF_RECORD)

    # ─── 宽表类 Sheet（预算执行表/底稿/差异/重拆/图例/月度/履约）───

    def _write_sheet_rows(self, wb: Workbook, period: str, conn: Any,
                          sheet: str) -> None:
        """把 rr_sheet_row 宽表写为 Sheet（首行表头 + 数据行）。"""
        from bdms.core import db as _db
        columns, rows = _db.load_sheet_rows(conn, period, sheet, prefix="rr")
        ws = wb.create_sheet(sheet[:31])
        if not rows:
            return
        # 表头：列字母 → 中文名（预算执行表/底稿用配置映射；其余用原键）
        header_map = self._header_map(sheet)
        for j, col in enumerate(columns, start=1):
            label = header_map.get(col, col)
            self._header_cell(ws, 1, j, label)
        # 数据
        for i, r in enumerate(rows, start=2):
            for j, col in enumerate(columns, start=1):
                v = r.get(col)
                fmt = self._number_format(col)
                self._body_cell(ws, i, j, v, fmt)
        # 列宽（采样前 200 行）
        self._autofit(ws, columns, rows, width_max=40)
        ws.freeze_panes = "D4" if sheet in (SHEET_BUDGET, SHEET_DRAFT) else "A2"

    def _header_map(self, sheet: str) -> dict[str, str]:
        """列字母 → 中文表头（预算执行表/底稿专用映射）。

        202606 投影行含扩展键（C_calib/Q_adj/AV..CO），用 202606 映射补中文名。
        """
        if sheet == SHEET_BUDGET:
            m = dict(BUDGET_COLUMNS)
            for c in COMPUTED_COLUMNS:
                m.setdefault(c, c)
            # 扩展键 → 202606 中文表头
            for key, src in (("C_calib", "C"), ("Q_adj", "Q")):
                m.setdefault(key, BUDGET_COLUMNS_202606.get(src, key))
            for c in BUDGET_COLUMNS_202606:
                m.setdefault(c, BUDGET_COLUMNS_202606[c])
            return m
        if sheet == SHEET_DRAFT:
            return dict(DRAFT_COLUMNS)
        if sheet in LEDGER_HEADERS:
            return {str(i): h for i, h in enumerate(LEDGER_HEADERS[sheet])}
        return {}

    def _number_format(self, col: str) -> Optional[str]:
        """金额/数量列数字格式（按列字母粗判）。"""
        if col in ("AB", "AC", "AD", "AE", "AF", "AP", "AQ", "AR"):
            return FMT_AMOUNT
        if col in ("AL", "AM", "AN", "AO", "I"):
            return FMT_AMOUNT
        if col in ("P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
                   "AA", "AG", "AH", "AI", "AJ", "AK", "AK"):
            return FMT_AMOUNT
        if col in ("AK",):
            return FMT_INT
        return None

    # ─── 单位转换（内部元 → 展示万；台账冻结值本就为万，不透传转换）───

    @staticmethod
    def _to_wan(v: Any) -> Any:
        """元 → 万元（2 位小数）。None/空/非数值原样。"""
        if v in (None, ""):
            return v
        try:
            return round(float(v) / 10000, 2)
        except (TypeError, ValueError):
            return v

    # ─── 汇总 ───

    def _write_summary(self, wb: Workbook, period: str, conn: Any) -> None:
        from bdms.core import db as _db
        _, rows = _db.load_sheet_rows(conn, period, SHEET_SUMMARY, prefix="rr")
        ws = wb.create_sheet(SHEET_SUMMARY[:31])
        if not rows:
            return
        for i, r in enumerate(rows, start=1):
            for j in range(13):
                v = r.get(str(j))
                if i == 1:
                    self._header_cell(ws, i, j + 1, SUMMARY_HEADERS[j] or "")
                else:
                    # 金额列（内部元）→ 万元展示；完成率/校验/文本列原样
                    if i >= 4 and j in (2, 3, 4, 6, 7, 9, 10):
                        v = self._to_wan(v)
                    fmt = FMT_RATE if j in (5, 8, 11) else FMT_AMOUNT
                    self._body_cell(ws, i, j + 1, v, fmt if isinstance(v, (int, float)) else None)
        ws.freeze_panes = "B4"
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 14

    # ─── 汇总分析 ───

    def _write_summary_analysis(self, wb: Workbook, period: str,
                                conn: Any) -> None:
        from bdms.core import db as _db
        _, rows = _db.load_sheet_rows(conn, period, SHEET_SUMMARY_ANALYSIS,
                                      prefix="rr")
        ws = wb.create_sheet(SHEET_SUMMARY_ANALYSIS[:31])
        if not rows:
            return
        headers = ["", "期间", "新签合同额", "新签-预计", "新签-实际", "新签-完成率",
                   "递延-预计", "递延-实际", "递延-完成率",
                   "合计-预计", "合计-实际", "合计-完成率"]
        for j, h in enumerate(headers, start=1):
            self._header_cell(ws, 1, j, h)
        for i, r in enumerate(rows, start=2):
            for j in range(len(headers)):
                v = r.get(str(j))
                if j in (2, 3, 4, 6, 7, 9, 10):
                    v = self._to_wan(v)
                fmt = FMT_RATE if j in (5, 8, 11) else FMT_AMOUNT
                self._body_cell(ws, i, j + 1, v,
                                fmt if isinstance(v, (int, float)) else None)
        ws.freeze_panes = "A2"

    # ─── 预算趋势分析（19 行 × 17 列，金额红线置空）───

    def _write_trend(self, wb: Workbook, period: str, conn: Any) -> None:
        ws = wb.create_sheet(SHEET_TREND[:31])

        # 表头三层（R1-R3）
        for j, h in enumerate(TREND_HEADERS, start=1):
            self._header_cell(ws, 1, j, h)
        # 读 ra_trend_row
        row_map: dict[int, dict] = {}
        for r in conn.execute(
            "SELECT * FROM ra_trend_row WHERE period=? ORDER BY row_index",
            (period,),
        ):
            row_map[r["row_index"]] = dict(r)
        cell_map: dict[tuple, str] = {}
        for c in conn.execute(
            "SELECT row_index, col_index, value FROM ra_trend_cell WHERE period=?",
            (period,),
        ):
            cell_map[(c["row_index"], c["col_index"])] = c["value"]

        # R4-R18：递延 6 行 + 合计 + 新签 5 行 + 合计 + 共计
        # 每行 17 列；金额列（4/6/8/10/12/14/16）红线置空
        for row_index in (4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18):
            r = row_map.get(row_index)
            if not r:
                continue
            excel_row = self._trend_excel_row(row_index)
            group = r.get("category_group") or ""
            status = r.get("status") or ""
            ws.cell(row=excel_row, column=1, value=group)
            ws.cell(row=excel_row, column=2, value=status)
            # 数量列
            for col_idx, key in ((3, "init_count"), (5, "normal_count"),
                                 (7, "exception_count"), (9, "disappear_count"),
                                 (11, "future_count"), (13, "check_count")):
                self._body_cell(ws, excel_row, col_idx, r.get(key), FMT_INT)
            # 金额列：红线置空，但样式保留
            for col_idx in (4, 6, 8, 10, 12, 14, 16):
                self._body_cell(ws, excel_row, col_idx, None, FMT_AMOUNT)
            # 样式应用到 C-N
            for j in range(3, 15):
                cell = ws.cell(row=excel_row, column=j)
                self._border(cell)
            # 合计行浅蓝底
            if row_index in (10, 17, 18):
                for j in range(1, 18):
                    ws.cell(row=excel_row, column=j).fill = PatternFill(
                        start_color=SUBHEADER_FILL, end_color=SUBHEADER_FILL,
                        fill_type="solid")

        # R19 新签预计确收率（数值在 ra_trend_cell）
        r19 = row_map.get(19)
        if r19:
            excel_row = self._trend_excel_row(19)
            ws.cell(row=excel_row, column=1, value="新签")
            ws.cell(row=excel_row, column=2, value="新签预计确收率")
            # 数量列复用 R19 的 init/check 计数
            for col_idx, key in ((3, "init_count"), (5, "normal_count"),
                                 (7, "exception_count"), (9, "disappear_count"),
                                 (11, "future_count"), (13, "check_count")):
                self._body_cell(ws, excel_row, col_idx, r19.get(key), FMT_INT)
            rate_cell = cell_map.get((19, 0))
            if rate_cell:
                try:
                    val = json.loads(rate_cell).get("value")
                    self._body_cell(ws, excel_row, 13, val, FMT_RATE)
                except (json.JSONDecodeError, TypeError):
                    pass
            for j in range(1, 18):
                self._border(ws.cell(row=excel_row, column=j))

        ws.freeze_panes = "A4"
        for col in ("A", "B"):
            ws.column_dimensions[col].width = 16
        for j in range(3, 15):
            ws.column_dimensions[get_column_letter(j)].width = 12

    @staticmethod
    def _trend_excel_row(row_index: int) -> int:
        """ra_trend_row 行号 → Excel 行号（R4 起，跳过 R11 新签表头）。"""
        if row_index >= 12:
            return row_index + 1  # R12→R13（R11 表头占一行）
        return row_index

    # ─── 样式辅助 ───

    def _header_cell(self, ws: Any, row: int, col: int, value: Any) -> None:
        cell = ws.cell(row=row, column=col, value=value)
        cell.font = Font(name=FONT_NAME, size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color=HEADER_FILL, end_color=HEADER_FILL,
                                fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        self._border(cell)

    def _body_cell(self, ws: Any, row: int, col: int, value: Any,
                   fmt: Optional[str] = None) -> None:
        cell = ws.cell(row=row, column=col, value=value)
        cell.font = Font(name=FONT_NAME, size=10)
        cell.alignment = Alignment(vertical="center")
        if isinstance(value, (int, float)):
            cell.alignment = Alignment(horizontal="right", vertical="center")
            if fmt:
                cell.number_format = fmt
        elif isinstance(value, str):
            cell.alignment = Alignment(horizontal="left", vertical="center")
        self._border(cell)

    def _border(self, cell: Any) -> None:
        thin = Side(border_style="thin", color=BORDER_COLOR)
        cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def _autofit(self, ws: Any, columns: list[str], rows: list[dict],
                 width_max: int = 40) -> None:
        """列宽：采样前 200 行按内容自适应，上限 width_max。"""
        for j, col in enumerate(columns, start=1):
            max_len = len(str(col))
            for r in rows[:200]:
                v = r.get(col)
                if isinstance(v, str):
                    max_len = max(max_len, len(v))
                elif v is not None:
                    max_len = max(max_len, len(f"{v:.2f}"))
            ws.column_dimensions[get_column_letter(j)].width = min(
                max_len + 2, width_max)
