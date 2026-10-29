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
from openpyxl.comments import Comment
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
    "产品-授权&维保统计", "POC&提前实施统计", "提前实施分事业部统计",
    "异常统计", "交付异常分事业部统计",
}

# SUBTOTAL 公式列（对齐黄金基准 202606 人工 r1：c53/c54/c57-66）
# 0-based: c53→52, c54→53, c57→56 ... c66→65
SUBTOTAL_FORMULA_COLS = {
    "签约": [52, 53, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65],
    "POC&提前实施": [52, 53, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65],
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
                        self._write_stats_sheet(wb, sheet, df)
                    continue

                # 核心数据 Sheet：原始 → effective（校准覆盖层唯一口径）
                columns, rows = _db.load_sheet_rows(conn, month, sheet, prefix="dr")
                if not rows:
                    continue
                df = pd.DataFrame(rows, columns=columns)
                from .calibration import CalibrationService
                _cs = CalibrationService(self.db_path)
                _active_map = _cs.get_active_map(month)
                if _active_map:
                    _eff_all = _cs.apply_overlays(month, {sheet: df})
                    df = _eff_all.get(sheet, df)
                # 去重列名（解决 pandas _dedupe_columns 产生的 .1 后缀）
                seen = {}
                clean_cols = []
                for c in df.columns:
                    s = str(c)
                    if s in seen:
                        seen[s] += 1
                        clean_cols.append(f"{s}_{seen[s]}")
                    else:
                        seen[s] = 0
                        clean_cols.append(s)
                df.columns = clean_cols
                
                # SUBTOTAL 公式列配置
                subtotal_cols = SUBTOTAL_FORMULA_COLS.get(sheet)
                active_map = _cs.get_active_map(month) if _active_map else {}
                self._write_sheet(
                    wb, sheet, df,
                    title=title_dt if sheet in titled else None,
                    subtotal_cols=subtotal_cols,
                    active_map=active_map,
                )
        finally:
            conn.close()

        # 校准台账 Sheet（对齐 DESIGN-DETAIL §4.7：有记录才追加）
        try:
            from .calibration import CalibrationService
            ledger_rows = CalibrationService(self.db_path).ledger_rows(month)
            if ledger_rows:
                ws = wb.create_sheet("校准台账")
                headers = ["月份", "Sheet", "行号", "列名", "原始值", "校准值",
                           "操作人", "校准时间", "校准原因", "状态"]
                for ci, h in enumerate(headers, start=1):
                    cell = ws.cell(row=1, column=ci, value=h)
                    cell.font = HEADER_FONT
                    cell.fill = HEADER_FILL
                    cell.alignment = HEADER_ALIGN
                    cell.border = BORDER
                for ri, row in enumerate(ledger_rows, start=2):
                    for ci, v in enumerate(row, start=1):
                        cell = ws.cell(row=ri, column=ci, value=v)
                        cell.font = DATA_FONT
                        cell.alignment = DATA_ALIGN
                ws.freeze_panes = "A2"
                for ci in range(1, len(headers) + 1):
                    ws.column_dimensions[
                        ws.cell(row=1, column=ci).column_letter].width = 14
        except Exception as _e:  # 台账 Sheet 失败不影响主导出（旧库无表时优雅跳过）
            import logging
            if "no such table" not in str(_e):
                logging.getLogger(__name__).warning("校准台账导出失败: %s", _e)

        target = Path(out_path) if out_path else output_path(f"交付月报_{month}.xlsx")
        target.parent.mkdir(parents=True, exist_ok=True)
        wb.save(target)
        return target

    @staticmethod
    def _write_stats_sheet(wb: Workbook, sheet_name: str, df: pd.DataFrame) -> None:
        """写入统计 Sheet（第一行是表头，不是列名）。"""
        ws = wb.create_sheet(sheet_name[:31])
        
        # DataFrame 的第一行是实际表头内容
        header_row = df.iloc[0].tolist() if len(df) > 0 else df.columns.tolist()
        
        # 写表头
        for col_idx, col_name in enumerate(header_row, start=1):
            cell = ws.cell(row=1, column=col_idx, value=str(col_name) if col_name else '')
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGN
            cell.border = BORDER
        
        # 写数据（从第二行开始）
        for row_idx, record in enumerate(df.iloc[1:].itertuples(index=False), start=2):
            for col_idx, value in enumerate(record, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = DATA_FONT
                cell.alignment = DATA_ALIGN
        
        # 冻结首行
        ws.freeze_panes = "A2"
        
        # 自动列宽
        for col_idx, col_name in enumerate(header_row, start=1):
            max_len = len(str(col_name)) if col_name else 0
            for row_idx in range(2, min(len(df) + 2, 202)):
                val = ws.cell(row=row_idx, column=col_idx).value
                if val:
                    max_len = max(max_len, len(str(val)))
            from openpyxl.utils import get_column_letter
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 40)

    @staticmethod
    def _write_sheet(wb: Workbook, sheet_name: str, df: pd.DataFrame,
                     title=None, subtotal_cols=None,
                     active_map: Optional[dict] = None) -> None:
        """写入单个 Sheet（带表头样式 + 冻结首行 + 自动列宽）。

        title 不为空时先在 r1 写入日期标题，表头下移到 r2
        （对齐手工交付月报的版式）。
        subtotal_cols: 需要写入 SUBTOTAL 公式的列索引列表（0-based）。
        """
        ws = wb.create_sheet(sheet_name[:31])  # Excel sheet 名上限 31 字符
        header_row = 2 if title is not None else 1

        if title is not None:
            ws.cell(row=1, column=1, value=title)

        # 列名原样保留（人工基准允许重复列名，如验收交接的两个「截至目前全部/部分验收」）
        # 唯一名后缀 __2 还原为原名，保持与人工基准一致的重复列名
        clean_cols = []
        for c in df.columns:
            s = str(c)
            if s.endswith("__2"):
                s = s[:-3]
            clean_cols.append(s)

        if title is not None:
            # 人工基准：签约/POC 的 r1c41 = "排序"（0-based 40）
            if len(clean_cols) >= 41:
                ws.cell(row=1, column=41, value="排序")

        # 表头
        for col_idx, col_name in enumerate(clean_cols, start=1):
            cell = ws.cell(row=header_row, column=col_idx, value=col_name)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = HEADER_ALIGN
            cell.border = BORDER

        # 数据（含校准批注）
        n_data_rows = len(df)
        import datetime as _dt
        active_map = active_map or {}
        # (row_index → {column_name: cal}) 快速索引
        cal_by_row = {}
        for (sh, ri, col), cal in active_map.items():
            if sh != sheet_name:
                continue
            cal_by_row.setdefault(ri, {})[col] = cal
        for row_idx, record in enumerate(df.itertuples(index=False),
                                        start=header_row + 1):
            data_row_index = row_idx - header_row - 1  # 0-based 原始行号
            row_cals = cal_by_row.get(data_row_index, {})
            for col_idx, value in enumerate(record, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.font = DATA_FONT
                cell.alignment = DATA_ALIGN
                col_name = str(df.columns[col_idx - 1])
                cal = row_cals.get(col_name)
                if cal:
                    orig = cal.get("original_value") or "-"
                    newv = cal.get("corrected_value", "")
                    op = cal.get("operator") or "-"
                    ts = cal.get("updated_at") or "-"
                    cell.comment = Comment(
                        f"校准: {orig} → {newv}\n操作人: {op}\n时间: {ts}",
                        "BDMS", height=90, width=240)

        # 日期归一化：DB 落盘经 json.dumps(default=str) 后 datetime 变字符串
        # "YYYY-MM-DD 00:00:00" → 原生 datetime（对齐人工基准）
        for row_idx in range(header_row + 1, header_row + 1 + n_data_rows):
            for col_idx in range(1, len(clean_cols) + 1):
                v = ws.cell(row=row_idx, column=col_idx).value
                if isinstance(v, str) and len(v) == 19 and v.endswith(' 00:00:00'):
                    try:
                        ws.cell(row=row_idx, column=col_idx).value = _dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass

        # SUBTOTAL 公式列（对齐黄金基准）
        if subtotal_cols and n_data_rows > 0:
            from openpyxl.utils import get_column_letter
            for col_idx_0based in subtotal_cols:
                col_idx_1based = col_idx_0based + 1
                col_letter = get_column_letter(col_idx_1based)
                col_name = df.columns[col_idx_0based]
                # 设计文档：公式结果以值写入（非 Excel 公式）。
                # 签约：人工 r1 为全列 SUBTOTAL → 写列总和
                # POC：人工 r1 为单行 SUBTOTAL(BA3:BA3) → 写首行值
                if sheet_name == "POC&提前实施":
                    try:
                        total = df[col_name].iloc[0]
                    except Exception:
                        total = 0
                else:
                    try:
                        total = df[col_name].sum()
                    except Exception:
                        total = 0
                cell_ref = f"{col_letter}1"
                ws[cell_ref] = total
                ws[cell_ref].font = Font(bold=True)

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
