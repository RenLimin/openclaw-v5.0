"""交付月报 Excel 导出。

从 DB 读数据 → 渲染为格式化 Excel。复用 delivery-center 的格式化配置。
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

# Sheet 顺序（对齐业务报表）
SHEET_ORDER = ["签约", "POC&提前实施", "异常项目", "确收交接", "验收交接"]


class DeliveryReportExporter:
    """交付月报 Excel 导出器。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.engine = DeliveryReportEngine(db_path)
        self.db_path = db_path

    def export(self, month: str, out_path: Optional[Path] = None) -> Path:
        """导出某月数据为 Excel。

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
            ordered = [s for s in SHEET_ORDER if s in sheets]
            ordered += [s for s in sheets if s not in SHEET_ORDER]

            for sheet in ordered:
                columns, rows = _db.load_sheet_rows(conn, month, sheet, prefix="dr")
                if not rows:
                    continue
                df = pd.DataFrame(rows, columns=columns)
                self._write_sheet(wb, sheet, df)
        finally:
            conn.close()

        target = Path(out_path) if out_path else output_path(f"交付月报_{month}.xlsx")
        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)
        return target

    @staticmethod
    def _write_sheet(wb: Workbook, sheet_name: str, df: pd.DataFrame) -> None:
        """写入单个 Sheet（带表头样式 + 冻结首行 + 自动列宽）。"""
        ws = wb.create_sheet(sheet_name[:31])  # Excel sheet 名上限 31 字符

        # 表头
        for col_idx, col_name in enumerate(df.columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=str(col_name))
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGN
            cell.border = BORDER

        # 数据
        for row_idx, record in enumerate(df.itertuples(index=False), start=2):
            for col_idx, value in enumerate(record, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = DATA_FONT
                cell.alignment = DATA_ALIGN

        # 冻结首行
        ws.freeze_panes = "A2"

        # 自动列宽（有上限）
        for col_idx, col_name in enumerate(df.columns, start=1):
            max_len = len(str(col_name))
            for value in df.iloc[:200, col_idx - 1]:  # 采样前 200 行
                max_len = max(max_len, len(str(value)))
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 40)

        # 自动筛选
        if len(df) > 0:
            ws.auto_filter.ref = ws.dimensions
