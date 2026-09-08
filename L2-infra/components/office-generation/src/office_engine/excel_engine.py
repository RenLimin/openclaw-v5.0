"""Excel SDK — 基于 openpyxl + xlsxwriter 的双引擎实现

引擎选择策略：
- 读/改已有文件 → openpyxl
- 全新写入 + 性能 → xlsxwriter（自动选择，对外透明）
- 快速 DataFrame 导出 → pandas（可选入口）
"""

from __future__ import annotations

import os
from typing import Optional, Union

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, DataBarRule

from .exceptions import OfficeEngineError, OfficeParseError


class WorksheetProxy:
    """Sheet 代理对象，屏蔽底层引擎差异"""

    def __init__(self, engine: str, ws):
        self.engine = engine  # "openpyxl" | "xlsxwriter"
        self._ws = ws

    @property
    def name(self) -> str:
        if self.engine == "openpyxl":
            return self._ws.title
        return self._ws.name

    # 供内部使用
    @property
    def raw(self):
        return self._ws


class ExcelDocument:
    """Excel 文档引擎

    统一接口：生命周期 + 元数据 + 解析 + 程序化构建
    """

    format = "xlsx"

    def __init__(self, path: Optional[str] = None):
        self._path = path
        self._engine = "openpyxl"  # 默认
        self._doc = None  # workbook
        self._closed = False
        self._sheets: dict[str, WorksheetProxy] = {}
        self._read_only = False  # xlsxwriter 模式标记

        if path and os.path.exists(path):
            # 读已有文件 → 必须 openpyxl
            self._engine = "openpyxl"
            self._doc = load_workbook(path)
            for name in self._doc.sheetnames:
                self._sheets[name] = WorksheetProxy("openpyxl", self._doc[name])
        else:
            # 全新创建，默认用 openpyxl（支持后续读写）
            self._engine = "openpyxl"
            from openpyxl import Workbook
            self._doc = Workbook()
            # 默认 sheet
            default_ws = self._doc.active
            default_ws.title = "Sheet1"
            self._sheets["Sheet1"] = WorksheetProxy("openpyxl", default_ws)

    # ── 生命周期 ──────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        if self._closed:
            raise OfficeEngineError("document already closed")
        out = path or self._path
        if not out:
            raise OfficeEngineError("no save path specified")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

        if self._engine == "openpyxl":
            self._doc.save(out)
        else:  # xlsxwriter
            import shutil
            # xlsxwriter 的 Workbook 绑定到临时文件，close 后复制到目标路径
            self._doc.close()
            tmp_path = getattr(self, "_tmp_path", None)
            if tmp_path and os.path.exists(tmp_path):
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                shutil.copy2(tmp_path, out)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        self._path = out
        return out

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._engine == "xlsxwriter" and self._doc:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None
        self._sheets = {}

    # ── 引擎切换 ──────────────────────────────────────────────

    def switch_to_xlsxwriter(self):
        """切换到 xlsxwriter 引擎（性能模式，仅全新写入）

        调用后当前 openpyxl 中的数据会丢失。
        建议在 add_sheet 前调用。
        """
        if self._path and os.path.exists(self._path):
            raise OfficeEngineError("xlsxwriter cannot edit existing files")
        import tempfile
        import xlsxwriter
        self._engine = "xlsxwriter"
        self._doc = None
        # 用临时文件作为 xlsxwriter 输出，save 时再复制到目标路径
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        self._tmp_path = tmp.name
        self._doc = xlsxwriter.Workbook(tmp.name)
        self._sheets = {}

    # ── 元数据 ────────────────────────────────────────────────

    @property
    def metadata(self) -> dict:
        if self._engine == "openpyxl":
            props = self._doc.properties
            return {
                "author": props.creator,
                "title": props.title,
                "subject": props.subject,
                "keywords": props.keywords,
                "created": props.created.isoformat() if props.created else None,
                "modified": props.modified.isoformat() if props.modified else None,
                "last_modified_by": props.lastModifiedBy,
            }
        else:  # xlsxwriter
            return {
                "engine": "xlsxwriter",
                "note": "xlsxwriter 不支持读取元数据",
            }

    # ── Sheet 管理 ────────────────────────────────────────────

    def add_sheet(self, name: str) -> WorksheetProxy:
        if name in self._sheets:
            raise OfficeEngineError(f"sheet '{name}' already exists")
        if self._engine == "openpyxl":
            ws = self._doc.create_sheet(title=name)
            proxy = WorksheetProxy("openpyxl", ws)
        else:
            ws = self._doc.add_worksheet(name)
            proxy = WorksheetProxy("xlsxwriter", ws)
        self._sheets[name] = proxy
        return proxy

    def get_sheet(self, name_or_index: Union[str, int]) -> WorksheetProxy:
        if isinstance(name_or_index, int):
            if self._engine == "openpyxl":
                if name_or_index >= len(self._doc.sheetnames):
                    raise OfficeEngineError(f"sheet index {name_or_index} out of range")
                name = self._doc.sheetnames[name_or_index]
                return self._sheets[name]
            else:
                raise OfficeEngineError("xlsxwriter does not support index access")
        if name_or_index not in self._sheets:
            raise OfficeEngineError(f"sheet '{name_or_index}' not found")
        return self._sheets[name_or_index]

    # ── 单元格写入 ────────────────────────────────────────────

    def set_cell(
        self,
        sheet: Union[str, WorksheetProxy],
        cell: str,
        value,
        font: Optional[dict] = None,
        fill: Optional[dict] = None,
        border: Optional[dict] = None,
        align: Optional[dict] = None,
        number_format: Optional[str] = None,
    ):
        """写单元格

        font: {"name": "Microsoft YaHei", "size": 11, "bold": True, "italic": False, "color": "FF0000"}
        fill: {"color": "FFFF00", "type": "solid"}
        border: {"style": "thin", "color": "000000"}
        align: {"horizontal": "center", "vertical": "center", "wrap_text": True}
        """
        proxy = self._resolve_sheet(sheet)

        if proxy.engine == "openpyxl":
            ws = proxy.raw
            c = ws[cell]
            c.value = value
            if font:
                c.font = Font(
                    name=font.get("name", "Microsoft YaHei"),
                    size=font.get("size"),
                    bold=font.get("bold", False),
                    italic=font.get("italic", False),
                    color=font.get("color"),
                )
            if fill:
                c.fill = PatternFill(start_color=fill.get("color", "FFFFFF"),
                                     end_color=fill.get("color", "FFFFFF"),
                                     fill_type=fill.get("type", "solid"))
            if border:
                side = Side(style=border.get("style", "thin"),
                            color=border.get("color", "000000"))
                c.border = Border(left=side, right=side, top=side, bottom=side)
            if align:
                c.alignment = Alignment(
                    horizontal=align.get("horizontal"),
                    vertical=align.get("vertical"),
                    wrap_text=align.get("wrap_text", False),
                )
            if number_format:
                # 坑：number_format 必须单独赋值，不能在 Font 等里传
                c.number_format = number_format
        else:  # xlsxwriter
            ws = proxy.raw
            fmt = self._doc.add_format()
            if font:
                fmt.set_font_name(font.get("name", "Microsoft YaHei"))
                if font.get("size"):
                    fmt.set_font_size(font["size"])
                if font.get("bold"):
                    fmt.set_bold()
                if font.get("italic"):
                    fmt.set_italic()
                if font.get("color"):
                    fmt.set_font_color("#" + font["color"])
            if fill:
                fmt.set_bg_color("#" + fill.get("color", "FFFFFF"))
            if border:
                fmt.set_border(1)
                fmt.set_border_color("#" + border.get("color", "000000"))
            if align:
                if align.get("horizontal"):
                    fmt.set_align(align["horizontal"])
                if align.get("vertical"):
                    fmt.set_align("v" + align["vertical"])
                if align.get("wrap_text"):
                    fmt.set_text_wrap()
            if number_format:
                fmt.set_num_format(number_format)
            # xlsxwriter 用 A1 引用
            ws.write(cell, value, fmt)

    def set_row(
        self,
        sheet: Union[str, WorksheetProxy],
        row: int,
        values: list,
        start_col: int = 1,
        header: bool = False,
    ):
        """写一行数据"""
        proxy = self._resolve_sheet(sheet)
        font_opts = {"bold": True, "name": "Microsoft YaHei"} if header else {"name": "Microsoft YaHei"}
        for i, val in enumerate(values):
            col_letter = get_column_letter(start_col + i)
            cell_ref = f"{col_letter}{row}"
            self.set_cell(proxy, cell_ref, val, font=font_opts)

    def set_column_width(self, sheet: Union[str, WorksheetProxy], col: Union[str, int], width: float):
        proxy = self._resolve_sheet(sheet)
        col_letter = col if isinstance(col, str) else get_column_letter(col)
        if proxy.engine == "openpyxl":
            proxy.raw.column_dimensions[col_letter].width = width
        else:
            proxy.raw.set_column(f"{col_letter}:{col_letter}", width)

    # ── 表格 ──────────────────────────────────────────────────

    def add_table(
        self,
        sheet: Union[str, WorksheetProxy],
        range_str: str,
        data: list[list],
        header_style: Optional[dict] = None,
    ):
        """添加表格（写数据 + 可选样式）"""
        proxy = self._resolve_sheet(sheet)
        # 解析范围
        min_col, min_row, max_col, max_row = range_boundaries(range_str)

        # 写表头
        if data:
            header_data = data[0]
            for j, val in enumerate(header_data):
                if min_col + j > max_col:
                    break
                col_letter = get_column_letter(min_col + j)
                cell_ref = f"{col_letter}{min_row}"
                style = header_style or {"bold": True, "name": "Microsoft YaHei"}
                self.set_cell(proxy, cell_ref, val, font=style)

            # 写数据行
            for i, row_data in enumerate(data[1:], start=1):
                if min_row + i > max_row:
                    break
                for j, val in enumerate(row_data):
                    if min_col + j > max_col:
                        break
                    col_letter = get_column_letter(min_col + j)
                    cell_ref = f"{col_letter}{min_row + i}"
                    self.set_cell(proxy, cell_ref, val, font={"name": "Microsoft YaHei"})

        # openpyxl 的 Table 对象
        if proxy.engine == "openpyxl":
            from openpyxl.worksheet.table import Table, TableStyleInfo
            table = Table(displayName=f"Table_{range_str.replace(':','_')}", ref=range_str)
            style = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
            table.tableStyleInfo = style
            proxy.raw.add_table(table)

    # ── 图表 ──────────────────────────────────────────────────

    def add_chart(
        self,
        sheet: Union[str, WorksheetProxy],
        chart_type: str,  # "bar" | "column" | "pie" | "line" | "scatter"
        title: str,
        data_range: str,
        cat_range: str,
        anchor: Optional[str] = None,
    ):
        """添加图表"""
        proxy = self._resolve_sheet(sheet)

        if proxy.engine == "openpyxl":
            from openpyxl.chart import (
                BarChart, LineChart, PieChart, ScatterChart, Reference,
            )
            type_map = {
                "bar": BarChart, "column": BarChart,
                "pie": PieChart, "line": LineChart, "scatter": ScatterChart,
            }
            if chart_type not in type_map:
                raise OfficeEngineError(f"unsupported chart type: {chart_type}")
            chart = type_map[chart_type]()
            if chart_type == "bar":
                chart.type = "bar"
            elif chart_type == "column":
                chart.type = "col"
            chart.title = title

            # 数据引用
            min_col, min_row, max_col, max_row = range_boundaries(data_range)
            data = Reference(proxy.raw, min_col=min_col, min_row=min_row,
                             max_col=max_col, max_row=max_row)
            chart.add_data(data, titles_from_data=True)

            # 分类引用
            c_min_col, c_min_row, c_max_col, c_max_row = range_boundaries(cat_range)
            cats = Reference(proxy.raw, min_col=c_min_col, min_row=c_min_row,
                             max_col=c_max_col, max_row=c_max_row)
            chart.set_categories(cats)

            anchor_cell = anchor or f"{get_column_letter(max_col + 2)}{min_row}"
            proxy.raw.add_chart(chart, anchor_cell)
        else:  # xlsxwriter
            ws = proxy.raw
            type_map = {
                "bar": "bar", "column": "column", "pie": "pie",
                "line": "line", "scatter": "scatter",
            }
            if chart_type not in type_map:
                raise OfficeEngineError(f"unsupported chart type: {chart_type}")
            chart = self._doc.add_chart({"type": type_map[chart_type]})
            chart.set_title({"name": title})
            chart.add_series({
                "name": f"={cat_range.split(':')[0]}1",
                "categories": f"={proxy.name}!{cat_range}",
                "values": f"={proxy.name}!{data_range}",
            })
            ws.insert_chart(anchor or "E2", chart)

    # ── 条件格式 ──────────────────────────────────────────────

    def add_conditional_format(
        self,
        sheet: Union[str, WorksheetProxy],
        range_str: str,
        rule_type: str,  # "cell_is" | "color_scale" | "data_bar"
        options: dict,
    ):
        """添加条件格式"""
        proxy = self._resolve_sheet(sheet)

        if proxy.engine == "openpyxl":
            ws = proxy.raw
            if rule_type == "cell_is":
                # options: {"operator": "greaterThan", "formula": [100], "fill": "FF0000"}
                fill = PatternFill(start_color=options.get("fill_color", "FFC7CE"),
                                   end_color=options.get("fill_color", "FFC7CE"),
                                   fill_type="solid") if options.get("fill_color") else None
                font = Font(color=options.get("font_color")) if options.get("font_color") else None
                rule = CellIsRule(
                    operator=options.get("operator", "greaterThan"),
                    formula=options.get("formula", []),
                    fill=fill,
                    font=font,
                )
                ws.conditional_formatting.add(range_str, rule)
            elif rule_type == "color_scale":
                # options: {"start_color": "63BE7B", "end_color": "F8696B"}
                rule = ColorScaleRule(
                    start_type="min", start_color=options.get("start_color", "63BE7B"),
                    end_type="max", end_color=options.get("end_color", "F8696B"),
                )
                ws.conditional_formatting.add(range_str, rule)
            elif rule_type == "data_bar":
                # options: {"color": "638EC6"}
                rule = DataBarRule(
                    start_type="min", end_type="max",
                    color=options.get("color", "638EC6"),
                )
                ws.conditional_formatting.add(range_str, rule)
            else:
                raise OfficeEngineError(f"unsupported rule_type: {rule_type}")
        else:  # xlsxwriter
            ws = proxy.raw
            if rule_type == "cell_is":
                ws.conditional_format(range_str, {
                    "type": "cell",
                    "criteria": options.get("operator", "greater than"),
                    "value": options.get("value", 0),
                    "format": self._doc.add_format({
                        "bg_color": options.get("fill_color", "#FFC7CE"),
                        "font_color": options.get("font_color", "#9C0006"),
                    }),
                })
            elif rule_type == "color_scale":
                ws.conditional_format(range_str, {
                    "type": "3_color_scale",
                    "min_color": options.get("start_color", "#63BE7B"),
                    "max_color": options.get("end_color", "#F8696B"),
                })
            elif rule_type == "data_bar":
                ws.conditional_format(range_str, {
                    "type": "data_bar",
                    "bar_color": "#" + options.get("color", "638EC6"),
                })
            else:
                raise OfficeEngineError(f"unsupported rule_type: {rule_type}")

    # ── 公式 / 冻结 / 合并 ───────────────────────────────────

    def set_formula(self, sheet: Union[str, WorksheetProxy], cell: str, formula: str):
        proxy = self._resolve_sheet(sheet)
        if proxy.engine == "openpyxl":
            proxy.raw[cell].value = formula
        else:
            proxy.raw.write_formula(cell, formula)

    def freeze_panes(self, sheet: Union[str, WorksheetProxy], cell: str):
        proxy = self._resolve_sheet(sheet)
        if proxy.engine == "openpyxl":
            proxy.raw.freeze_panes = cell
        else:
            proxy.raw.freeze_panes(cell)

    def merge_cells(self, sheet: Union[str, WorksheetProxy], range_str: str):
        proxy = self._resolve_sheet(sheet)
        if proxy.engine == "openpyxl":
            proxy.raw.merge_cells(range_str)
        else:
            proxy.raw.merge_range(range_str, "")

    # ── 解析 API ──────────────────────────────────────────────

    def parse(self) -> dict:
        """解析文档结构"""
        if self._engine == "xlsxwriter":
            raise OfficeParseError("xlsxwriter does not support reading")

        result = {
            "format": "xlsx",
            "metadata": self.metadata,
            "sheets": [],
        }

        for name in self._doc.sheetnames:
            ws = self._doc[name]
            sheet_info = {
                "name": name,
                "max_row": ws.max_row,
                "max_col": ws.max_column,
                "cell_values": [],
                "tables": [],
                "charts": [],
                "merged_cells": [],
            }

            # 单元格值（只存非空）
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row,
                                     min_col=1, max_col=ws.max_column, values_only=False):
                for cell in row:
                    if cell.value is not None:
                        sheet_info["cell_values"].append({
                            "cell": cell.coordinate,
                            "value": str(cell.value),
                            "row": cell.row,
                            "col": cell.column,
                        })

            # 表格（openpyxl 新版 ws.tables 返回 dict，value 可能是 str 或 Table 对象）
            for t_name, table in ws.tables.items():
                if hasattr(table, "ref"):
                    ref = table.ref
                else:
                    # 新版 openpyxl: table 是 str (ref 字符串)
                    ref = str(table)
                sheet_info["tables"].append({
                    "name": t_name,
                    "ref": ref,
                })

            # 图表
            sheet_info["charts"] = [
                {"title": c.title.tx.rich.p[0].r[0].t if c.title and c.title.tx else None,
                 "type": type(c).__name__}
                for c in ws._charts
            ] if hasattr(ws, "_charts") else []

            # 合并单元格
            sheet_info["merged_cells"] = [str(m) for m in ws.merged_cells.ranges]

            result["sheets"].append(sheet_info)

        return result

    def to_markdown(self, sheet: Union[str, int, None] = None) -> str:
        """转 Markdown（指定 sheet 或全部）"""
        if self._engine == "xlsxwriter":
            raise OfficeParseError("xlsxwriter does not support reading")

        sheets_to_export = []
        if sheet is None:
            sheets_to_export = list(self._sheets.keys())
        elif isinstance(sheet, int):
            sheets_to_export = [list(self._sheets.keys())[sheet]]
        else:
            sheets_to_export = [sheet]

        lines = []
        for sheet_name in sheets_to_export:
            ws = self._doc[sheet_name]
            lines.append(f"## {sheet_name}")
            lines.append("")

            if ws.max_row == 0 or ws.max_column == 0:
                lines.append("_(empty)_")
                lines.append("")
                continue

            # 逐行输出为 markdown table
            for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=ws.max_row,
                                                        max_col=ws.max_column, values_only=True), start=1):
                values = [str(v) if v is not None else "" for v in row]
                lines.append("| " + " | ".join(values) + " |")
                if row_idx == 1:
                    lines.append("| " + " | ".join(["---"] * len(values)) + " |")

            lines.append("")

        return "\n".join(lines)

    def get_used_range(self, sheet: Union[str, WorksheetProxy]) -> dict:
        """获取已用区域"""
        proxy = self._resolve_sheet(sheet)
        if proxy.engine == "xlsxwriter":
            raise OfficeParseError("xlsxwriter does not support reading")
        ws = proxy.raw
        return {
            "sheet": ws.title,
            "min_row": 1,
            "max_row": ws.max_row,
            "min_col": 1,
            "max_col": ws.max_column,
            "range": f"A1:{get_column_letter(ws.max_column)}{ws.max_row}",
            "cell_count": ws.max_row * ws.max_column,
        }

    # ── DataFrame 快速导出（可选入口）───────────────────────────

    @classmethod
    def from_dataframe(cls, df, output_path: str, sheet_name: str = "Sheet1") -> str:
        """DataFrame → Excel 快速导出（pandas 引擎）"""
        import pandas as pd
        df.to_excel(output_path, sheet_name=sheet_name, index=False, engine="openpyxl")
        return output_path

    # ── 内部工具 ──────────────────────────────────────────────

    def _resolve_sheet(self, sheet: Union[str, int, WorksheetProxy]) -> WorksheetProxy:
        if isinstance(sheet, WorksheetProxy):
            return sheet
        return self.get_sheet(sheet)
