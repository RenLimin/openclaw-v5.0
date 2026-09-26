"""交付月报 Excel 导出（15 Sheet 完整版）。

从 DB 读数据 → 渲染为格式化 Excel。
- 核心数据 Sheet（1-5）：读 dr_sheet_row
- 统计 Sheet（6-14）：读 DASHBOARD 实时聚合（delivery_report_connector）
- 图例 Sheet（15）：读 md_reference legend_config
"""

from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

from bdms.core import db as _db
from bdms.core.paths import OUTPUT_DIR, output_path
from .engine import DeliveryReportEngine

# 样式（对齐源实现的视觉规范）
HEADER_FONT = Font(name="微软雅黑", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF4472C4")
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
DATA_FONT = Font(name="微软雅黑", size=10)
DATA_ALIGN = Alignment(horizontal="left", vertical="center")

THIN = Side(style="thin", color="FFD9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# Sheet 顺序（15 Sheet，对齐黄金基准）
SHEET_ORDER = [
    "签约", "POC&提前实施", "异常项目", "确收交接", "验收交接",   # 核心数据 1-5
    "异常台账", "交付效率统计", "签约统计", "产品-授权&维保统计",     # 统计 6-9
    "POC&提前实施统计", "提前实施分事业部统计", "异常统计",           # 统计 10-12
    "交付异常分事业部统计", "交接统计", "图例",                       # 统计 13-14 + 图例 15
]

# 统计 Sheet（通过 DASHBOARD 实时聚合）
STAT_SHEETS = {
    "异常台账", "交付效率统计", "签约统计", "交接统计",
}


class DeliveryReportExporter:
    """交付月报 Excel 导出器（只做 IO + 格式，不做业务计算）。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.engine = DeliveryReportEngine(db_path)
        self.db_path = db_path

    def export(self, month: str, out_path: Optional[Path] = None) -> Path:
        """导出某月数据为 Excel（15 Sheet）。

        要求数据已在 DB 中（先调用 service.generate）。
        """
        conn = _db.get_connection(self.db_path)
        try:
            sheets = _db.list_sheets(conn, month, prefix="dr")
            if not sheets:
                raise ValueError(f"{month} 无数据，请先生成")

            wb = Workbook()
            wb.remove(wb.active)

            # 按业务顺序排列，多余的追加
            ordered = [s for s in SHEET_ORDER if s in sheets or s in STAT_SHEETS or s == "图例"]
            ordered += [s for s in sheets if s not in SHEET_ORDER]

            # 手工报表的「签约」/「POC&提前实施」sheet 在 r1 有日期标题行
            # （形如 2026-06-30），表头下移一行；其余 sheet 无标题行
            titled = {"签约", "POC&提前实施"}
            title_dt = _month_end_date(month)

            # 统计 Sheet：DASHBOARD 实时聚合
            from bdms.modules.dashboard.delivery_report_connector import DeliveryReportConnector
            connector = DeliveryReportConnector(self.db_path)
            stats_cache = connector.build_stats_sheets(month)

            for sheet in ordered:
                if sheet == "图例":
                    legend_df = connector.get_legend_config()
                    if legend_df is not None and not legend_df.empty:
                        self._write_sheet(wb, "图例", legend_df)
                    continue
                if sheet in STAT_SHEETS:
                    df = stats_cache.get(sheet)
                    if df is not None and not df.empty:
                        self._write_sheet(wb, sheet, df)
                    continue

                columns, rows = _db.load_sheet_rows(conn, month, sheet, prefix="dr")
                if not rows:
                    continue
                df = pd.DataFrame(rows, columns=columns)
                self._write_sheet(
                    wb, sheet, df,
                    title=title_dt if sheet in titled else None,
                )
        finally:
            conn.close()

        target = Path(out_path) if out_path else output_path(f"交付月报_{month}.xlsx")
        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)
        return target

    @staticmethod
    def _write_sheet(wb: Workbook, sheet_name: str, df: pd.DataFrame,
                     title=None) -> None:
        """写入单个 Sheet（带表头样式 + 冻结首行 + 自动列宽）。

        title 不为空时先在 r1 写入日期标题，表头下移到 r2
        （对齐手工交付月报的版式）。
        """
        ws = wb.create_sheet(sheet_name[:31])  # Excel sheet 名上限 31 字符
        header_row = 2 if title is not None else 1

        if title is not None:
            ws.cell(row=1, column=1, value=title)

        # 表头
        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=str(col_name))
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGN
            cell.border = BORDER

        # 数据
        for row_idx, record in enumerate(df.itertuples(index=False),
                                        start=header_row + 1):
            for col_idx, value in enumerate(record, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = DATA_FONT
                cell.alignment = DATA_ALIGN

        # 冻结表头行
        ws.freeze_panes = f"A{header_row + 1}"

        # 自动列宽（有上限）
        for col_idx, col_name in enumerate(df.columns, start=1):
            max_len = len(str(col_name))
            for value in df.iloc[:200, col_idx - 1]:  # 采样前 200 行
                max_len = max(max_len, len(str(value)))
            ws.column_dimensions[ws.cell(row=header_row, column=col_idx).column_letter].width = min(max_len + 2, 40)

        # 自动筛选
        if len(df) > 0:
            ws.auto_filter.ref = (
                f"A{header_row}:{ws.cell(row=header_row, column=len(df.columns)).coordinate}"
                f"{ws.max_row}"
            )


def _month_end_date(month: str):
    """'202606' → datetime(2026, 6, 30)，用于 sheet r1 的日期标题。"""
    import calendar
    from datetime import date
    y, m = int(month[:4]), int(month[4:6])
    return date(y, m, calendar.monthrange(y, m)[1])
