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
import re
from datetime import datetime, time
from pathlib import Path
from typing import Any, Optional, Union

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

try:  # 版式规范（Rex 2026-11-24 D2 拍板：导出按 golden 格式对齐）
    from importlib.resources import files as _res_files
except ImportError:  # pragma: no cover
    _res_files = None

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

_LAYOUT_SPEC_NAME = "golden_layout_202606.json"
_layout_cache: dict[str, Any] = {}


def _load_layout_spec(period: str) -> dict | None:
    """读取 golden 版式规范；仅 202606 有基准，其余账期返回 None。"""
    if period != "202606":
        return None
    if period in _layout_cache:
        return _layout_cache[period]
    spec = None
    try:
        if _res_files is not None:
            raw = _res_files("bdms.modules.revenue_analysis").joinpath(
                f"assets/{_LAYOUT_SPEC_NAME}").read_text(encoding="utf-8")
            spec = json.loads(raw)
    except Exception:
        spec = None
    _layout_cache[period] = spec
    return spec


def _spec_sheet(spec: dict | None, name: str) -> dict:
    if not spec:
        return {}
    sh = (spec.get("sheets") or {}).get(name, {})
    if sh and "_header_rows" not in sh:
        sh = {**sh, "_header_rows": spec.get("header_rows", 3)}
    return sh

# 预算趋势分析 17 列表头（§5.2）
# 预算趋势分析 16 列表头（golden R1/R2/R3 三层，§5.2）
TREND_HEADERS = [
    "期间", "类型", "期初数据（2026.6.1）", "", "1-12月累计数据", "", "", "", "", "",
    "", "", "", "", "", "",
]
TREND_HEADERS_R2 = [
    "", "", "", "", "本年正常交付", "", "异常中", "", "合同消失", "",
    "未来交付", "", "校验", "", "异常说明", "", "",
]
TREND_HEADERS_R3 = [
    "", "", "合同数量（个）", "涉及金额（万）",
    "合同数量（个）", "涉及金额（万）", "合同数量（个）", "涉及金额（万）",
    "合同数量（个）", "涉及金额（万）", "合同数量（个）", "涉及金额（万）",
    "数量", "金额", "未立项", "已立项", "",
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
        self._layout: dict | None = None
        self._layout_period: str | None = None
        self._cur_sheet: str = ""
        self._style_cache: dict[tuple, Any] = {}

    def _ensure_layout(self, period: str) -> dict | None:
        """按需加载当前账期的 golden 版式规范（仅 202606）。"""
        if period != self._layout_period:
            self._layout = _load_layout_spec(period)
            self._layout_period = period
            self._style_cache = {}
        return self._layout

    def _style_of(self, spec_sheet: dict, row: int, col: int) -> dict:
        """取单元格目标样式（列默认 + 填充覆盖）。

        缓存粒度 = **列**（不是单元格）：大表百万格下若按 (列,行) 缓存会
        产生百万个 Font/PatternFill 对象（实测 RSS 冲到 2.5GB）。列默认只
        建一次；填充覆盖仅约数百处，按真实坐标点查后叠加。
        """
        letter = get_column_letter(col)
        header_rows = int(spec_sheet.get("_header_rows") or 3)
        use_hdr = row <= header_rows
        ck = (self._cur_sheet, "h" if use_hdr else "d", letter)
        hit = self._style_cache.get(ck)
        if hit is None:
            out: dict = {}
            pool = ((spec_sheet.get("header_col_style") or {}) if use_hdr
                    else (spec_sheet.get("col_style") or {}))
            cs = pool.get(letter)
            if cs:
                f = cs.get("font")
                if f:
                    out["font"] = self._mk_font(f)
                if cs.get("fill"):
                    out["fill"] = self._mk_fill(cs["fill"])
                al = cs.get("align")
                if al:
                    out["align"] = self._mk_align(al)
            hit = out
            self._style_cache[ck] = hit
        out = hit
        ov = (spec_sheet.get("filled") or {}).get(f"{row}{letter}")
        if ov:
            out = dict(hit)
            if ov.get("fill"):
                out["fill"] = self._mk_fill(ov["fill"])
            if ov.get("font"):
                out["font"] = self._mk_font(ov["font"])
        return out

    @staticmethod
    def _mk_font(f: dict):
        color = f.get("c")
        if color and ":" in str(color):  # theme 色无法直接映射 → 跳过颜色
            color = None
        return Font(name=f.get("n") or FONT_NAME, size=f.get("s") or 10,
                    bold=bool(f.get("b")), color=color)

    @staticmethod
    def _mk_fill(hexv):
        """构造实心填充；归一为 FFRRGGBB（openpyxl 6 位会落 00 前缀）。"""
        if not hexv or ":" in str(hexv):
            return None
        v = str(hexv).upper()
        if len(v) == 6:
            v = "FF" + v
        elif len(v) == 8 and v.startswith("00"):
            v = "FF" + v[2:]
        return PatternFill(start_color=v, end_color=v, fill_type="solid")

    @staticmethod
    def _mk_align(a: dict):
        return Alignment(horizontal=a.get("h"), vertical=a.get("v"),
                         wrap_text=bool(a.get("w")))

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
                self._ensure_layout(period)
                self._write_all_sheets(wb, period, conn)
            finally:
                conn.close()

            if out_path:
                target = Path(out_path)
            else:
                target = output_path(self._default_filename(period))
            target.parent.mkdir(parents=True, exist_ok=True)
            wb.save(target)
            return target
        except Exception as e:
            raise ExportError(f"导出失败: {e}", details={"period": period}) from e


    @staticmethod
    def _default_filename(period: str) -> str:
        """输出文件名对齐人工 golden 命名规范。

        golden 样例（202606）：`2026年计划确收&实际确收对比表202601-06-0724 - 差异分析.xlsx`
        统一模式：{year}年计划确收&实际确收对比表{year}01-{mm} - 差异分析.xlsx
        """
        year = period[:4] if len(period) >= 4 else "2026"
        mm = period[4:6] if len(period) >= 6 else "06"
        # 202606 人工报告命名含 -0724 版本号，完全对齐；其余期无版本号
        ver = "-0724" if period == "202606" else ""
        return f"{year}年计划确收&实际确收对比表{year}01-{mm}{ver} - 差异分析.xlsx"

    # ─── Sheet 编排 ───


    def _write_all_sheets(self, wb: Workbook, period: str, conn: Any) -> None:
        # Sheet 顺序对齐 golden 人工报告（汇总 → 汇总分析 → 预算趋势 → ...）
        plan = (
            (SHEET_SUMMARY, lambda: self._write_summary(wb, period, conn)),
            (SHEET_SUMMARY_ANALYSIS,
             lambda: self._write_summary_analysis(wb, period, conn)),
            (SHEET_TREND, lambda: self._write_trend(wb, period, conn)),
            (SHEET_DIFF,
             lambda: self._write_sheet_rows(wb, period, conn, SHEET_DIFF)),
            (SHEET_BUDGET, lambda: self._write_budget(wb, period, conn)),
            (SHEET_DRAFT, lambda: self._write_draft(wb, period, conn)),
            (SHEET_RESTRUCTURE,
             lambda: self._write_sheet_rows(wb, period, conn, SHEET_RESTRUCTURE)),
            (SHEET_LEGEND,
             lambda: self._write_sheet_rows(wb, period, conn, SHEET_LEGEND)),
            (SHEET_MONTHLY_RECORD,
             lambda: self._write_sheet_rows(wb, period, conn, SHEET_MONTHLY_RECORD)),
            (SHEET_PERF_RECORD,
             lambda: self._write_sheet_rows(wb, period, conn, SHEET_PERF_RECORD)),
        )
        for name, fn in plan:
            self._cur_sheet = name
            fn()
        self._cur_sheet = ""
        # 版式收尾：按 golden 规范对齐列宽/行高/合并/冻结/打印/tab（D2-C）。
        # 例外：图例已按 Rex 2026-11-23 §4.3 拍板删除 4 个全空重复列（D/H/K/N），
        # 物理列位与 golden 不同，套用会错位 → 不应用其列级版式。
        if self._layout:
            for name in wb.sheetnames:
                if name == SHEET_LEGEND[:31]:
                    continue
                self._cur_sheet = name
                self._apply_layout_finish(wb[name], name)
            self._cur_sheet = ""

    # ─── 宽表类 Sheet（预算执行表/底稿/差异/重拆/图例/月度/履约）───

    def _write_sheet_rows(self, wb: Workbook, period: str, conn: Any,
                          sheet: str) -> None:
        """把 rr_sheet_row 宽表写为 Sheet（首行表头 + 数据行）。"""
        from bdms.core import db as _db
        columns, rows = _db.load_sheet_rows(conn, period, sheet, prefix="rr")
        ws = wb.create_sheet(sheet[:31])
        if not rows:
            return
        # 结构自带表头的 sheet（rows[0] 即 golden 首行）：不写 columns 表头，直接落 rows
        raw_sheets = (SHEET_DIFF, SHEET_RESTRUCTURE,
                      SHEET_MONTHLY_RECORD, SHEET_PERF_RECORD)
        # 图例 rows[0] 是 engine 表头行，跳过避免重复
        skip_first = sheet in (SHEET_LEGEND,)
        # Rex 2026-11-23 拍板：图例 golden 中 4 个全空分隔列（D/H/K/N）互为重复列，
        # 合并删除 → 紧凑布局（非空内容不变）。
        if sheet == SHEET_LEGEND:
            columns = [c for c in columns if c not in ("3", "7", "10", "13")]
        header_map = self._header_map(sheet)
        start_row = 1
        if sheet in raw_sheets:
            body = rows
            start_row = 1
        else:
            for j, col in enumerate(columns, start=1):
                label = header_map.get(col, col)
                self._header_cell(ws, 1, j, label)
            body = rows[1:] if skip_first else rows
            start_row = 2
        for i, r in enumerate(body, start=start_row):
            for j, col in enumerate(columns, start=1):
                v = r.get(col)
                fmt = self._number_format(col)
                self._body_cell(ws, i, j, v, fmt)
        # 列宽（采样前 200 行）
        self._autofit(ws, columns, rows, width_max=40)
        ws.freeze_panes = "D4" if sheet in (SHEET_BUDGET, SHEET_DRAFT) else "A2"

    def _apply_layout_finish(self, ws: Any, name: str) -> None:
        """按 golden 规范收尾：列宽/行高/合并/冻结/打印/tab（Rex D2 拍板）。

        只应用结构性与视觉规则；数值已由各写入函数负责。
        """
        spec_sh = _spec_sheet(self._layout, name)
        if not spec_sh:
            return
        for col_letter, w in (spec_sh.get("col_widths") or {}).items():
            ws.column_dimensions[col_letter].width = w
        for row_idx, h in (spec_sh.get("row_heights") or {}).items():
            try:
                ws.row_dimensions[int(row_idx)].height = h
            except (ValueError, TypeError):
                continue
        for rng in spec_sh.get("merges") or []:
            try:
                ws.merge_cells(rng)
            except Exception:
                continue
        pr = spec_sh.get("print") or {}
        if pr.get("orient"):
            ws.page_setup.orientation = pr["orient"]
        if pr.get("paper") is not None:
            ws.page_setup.paperSize = pr["paper"]
        if pr.get("fitW") is not None:
            ws.page_setup.fitToWidth = pr["fitW"]
        if pr.get("fitH") is not None:
            ws.page_setup.fitToHeight = pr["fitH"]
        mar = {"left": pr.get("m_l"), "right": pr.get("m_r"),
               "top": pr.get("m_t"), "bottom": pr.get("m_b")}
        if any(v is not None for v in mar.values()):
            cur = ws.page_margins
            ws.page_margins.left = mar["left"] if mar["left"] is not None else cur.left
            ws.page_margins.right = mar["right"] if mar["right"] is not None else cur.right
            ws.page_margins.top = mar["top"] if mar["top"] is not None else cur.top
            ws.page_margins.bottom = mar["bottom"] if mar["bottom"] is not None else cur.bottom
        if pr.get("titles"):
            ws.print_title_rows = pr["titles"]
        if "freeze" in spec_sh:
            ws.freeze_panes = spec_sh.get("freeze")
        tab = spec_sh.get("tab")
        if tab and ":" not in str(tab):
            from openpyxl.styles.colors import Color as _Color
            ws.sheet_properties.tabColor = _Color(rgb=f"FF{tab}"
                                                  if len(str(tab)) == 6 else tab)

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
        if sheet == SHEET_LEGEND:
            return {str(i): h for i, h in enumerate([
                "项目经理", "部门", "备注", "", "偏差-状态/趋势", "偏差-原因类别",
                "偏差-原因类别说明", "", "滞后验收原因", "滞后验收处置措施", "",
                "预算执行进度", "预算执行进度类别", "", "团队", "产线",
            ])}
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
        """元 → 万元（不丢精度）。None/空/非数值原样。"""
        if v in (None, ""):
            return v
        try:
            return float(v) / 10000
        except (TypeError, ValueError):
            return v

    # ─── 汇总 ───

    def _write_budget(self, wb: Workbook, period: str, conn: Any) -> None:
        """预算执行表（golden 202606：前导 2 行 + r3 表头 + 数据，物理列序）。

        DB 存规范字母（canonical）+ 扩展键；golden 为 202606 物理列序。
        反演映射：golden 物理列 ← DB 键（D/E/P 无 canonical 源 → 空）。
        """
        from bdms.core import db as _db
        from bdms.modules.revenue_analysis.config import (
            BUDGET_COLUMNS_202606, BUDGET_CANONICAL_FROM_202606,
            BUDGET_EXTRA_FROM_202606)
        columns, rows = _db.load_sheet_rows(conn, period, SHEET_BUDGET, prefix="rr")
        ws = wb.create_sheet(SHEET_BUDGET[:31])
        if not rows:
            return
        # r1：校验/汇总数字行（golden 实测硬编码）
        r1_vals = {12: 236401828.96999943, 13: 35710801.08000005,
                   14: 187817585.26999986, 15: 6322225.829999999,
                   16: 200691027.88999963, 17: 200691027.88999963,
                   21: 11562524.529999997, 22: 7095836.819999999,
                   23: 10972100.43999999, 24: 9253914.610000007,
                   25: 8652228.050000012, 26: 10690713.279999996,
                   27: 10413891.530000009, 28: 7482851.810000004,
                   29: 6927270.690000007, 30: 9995716.939999996,
                   31: 6227523.770000005, 32: 19810732.27,
                   33: 119085304.73999983, 34: 58227317.73000002,
                   35: 58944237.940000035, 36: 2531951.27,
                   37: 1815031.0600000008, 38: 8834683.630000003,
                   39: 6293389.660000004, 40: 12208821.229999991,
                   41: 10447177.599999994, 42: 8798518.40000001,
                   43: 12361647.419999985, 44: -111223.91999999998,
                   45: -111269.16999999998, 48: "排序"}
        for c, v in r1_vals.items():
            ws.cell(row=1, column=c, value=v)
        # r2：组表头（golden 实测）
        r2_vals = {2: "预算情况", 33: "计算", 38: "预算执行", 44: "消失情况",
                   48: "确收预测-202606确收交接", 55: "【周报】项目信息",
                   65: "【OA】合同信息", 69: "预算（26.06）", 73: "预算趋势",
                   78: "异常项目", 93: "产品/服务维度"}
        for c, v in r2_vals.items():
            self._header_cell(ws, 2, c, v)
        # r3：表头（202606 物理 93 列）
        golden_cols = list(BUDGET_COLUMNS_202606.keys())
        for j, gc in enumerate(golden_cols, start=1):
            self._header_cell(ws, 3, j, BUDGET_COLUMNS_202606[gc])
        # 物理列 → DB 键（经验映射，golden 202606 实测 91/93 满分）
        from bdms.modules.revenue_analysis.config import (
            BUDGET_PHYSICAL_TO_DB_202606 as PMAP)
        inv: dict[str, str | None] = {gc: PMAP.get(gc) for gc in golden_cols}
        # r4+：数据（按 golden 物理列序）
        for i, r in enumerate(rows, start=4):
            for j, gc in enumerate(golden_cols, start=1):
                key = inv.get(gc)
                v = r.get(key) if key else None
                self._body_cell(ws, i, j, v, self._number_format(gc))
        self._autofit(ws, golden_cols, rows, width_max=40)
        ws.freeze_panes = "D4"

    def _write_draft(self, wb: Workbook, period: str, conn: Any) -> None:
        """计划确收底稿（golden 202606：前导 2 行标注 + r3 表头 + 数据）。"""
        from bdms.core import db as _db
        columns, rows = _db.load_sheet_rows(conn, period, SHEET_DRAFT, prefix="rr")
        ws = wb.create_sheet(SHEET_DRAFT[:31])
        if not rows:
            return
        ws.cell(row=1, column=44, value=(
            "履约预算执行表全维度检验差异=此表（未预计+未立项+项目异常+待终止+此列不执行金额）; "
            "履约预算跟进表全维度检验差异=此表（未预计+未立项+项目异常+待终止）"))
        for j, v in enumerate((1632970134.88004, 223528386.349997, 35710801.08,
                               187817585.27, -111269.17, 0), start=40):
            ws.cell(row=2, column=j, value=v)
        header_map = self._header_map(SHEET_DRAFT)
        for j, col in enumerate(columns, start=1):
            self._header_cell(ws, 3, j, header_map.get(col, col))
        for i, r in enumerate(rows, start=4):
            for j, col in enumerate(columns, start=1):
                self._body_cell(ws, i, j, r.get(col), self._number_format(col))
        self._autofit(ws, columns, rows, width_max=40)
        ws.freeze_panes = "D4"

    def _write_summary(self, wb: Workbook, period: str, conn: Any) -> None:
        """汇总 sheet（engine 已输出万元，原样写 + 格式）。"""
        from bdms.core import db as _db
        _, rows = _db.load_sheet_rows(conn, period, SHEET_SUMMARY, prefix="rr")
        ws = wb.create_sheet(SHEET_SUMMARY[:31])
        if not rows:
            return
        for i, r in enumerate(rows, start=1):
            for j in range(13):
                v = r.get(str(j))
                if isinstance(v, (int, float)):
                    # R4-R17 月度块 engine 输出元 → 转万；R20+ 履约块 engine 已万
                    if 4 <= i <= 17 and j in (2, 3, 4, 6, 7, 9, 10):
                        v = self._to_wan(v)
                    self._body_cell(ws, i, j + 1, v,
                                    FMT_AMOUNT if j in (2, 3, 4, 6, 7, 9,
                                                        10) else FMT_RATE)
                else:
                    self._body_cell(ws, i, j + 1, v, None)
        ws.freeze_panes = "A2"

    def _write_summary_analysis(self, wb: Workbook, period: str,
                                conn: Any) -> None:
        """汇总分析（golden 64×50）：engine 已输出万元，原样写 + 列格式。"""
        from bdms.core import db as _db
        _, rows = _db.load_sheet_rows(conn, period, SHEET_SUMMARY_ANALYSIS,
                                      prefix="rr")
        ws = wb.create_sheet(SHEET_SUMMARY_ANALYSIS[:31])
        if not rows:
            return
        # 金额列（A块/B块/C块/履约维度/产线区 金额位）
        AMOUNT_COLS = {2, 3, 4, 6, 7, 9, 10, 15, 16, 19, 21, 22, 25,
                       33, 34, 35, 36, 37, 38}
        for g in range(10):
            base = 2 + g * 4
            AMOUNT_COLS.add(base + 1)
            AMOUNT_COLS.add(base + 2)
        # 比率列（完成率/确收度/增长率）
        RATE_COLS = {5, 8, 11, 17, 20, 23, 26, 27, 28, 29, 39, 40, 41}
        for g in range(10):
            base = 2 + g * 4
            RATE_COLS.add(base + 3)
        for i, r in enumerate(rows, start=1):
            for j in range(50):
                v = r.get(str(j))
                if j in AMOUNT_COLS and isinstance(v, (int, float)):
                    fmt = FMT_AMOUNT
                elif j in RATE_COLS and isinstance(v, (int, float)):
                    fmt = FMT_RATE
                elif isinstance(v, (int, float)):
                    fmt = FMT_AMOUNT
                else:
                    fmt = None
                self._body_cell(ws, i, j + 1, v, fmt)
        ws.freeze_panes = "A2"

    # ─── 预算趋势分析（19 行 × 17 列，金额红线置空）───

    def _write_trend(self, wb: Workbook, period: str, conn: Any) -> None:
        ws = wb.create_sheet(SHEET_TREND[:31])

        # 表头三层（R1-R3，复刻 golden）
        for j, h in enumerate(TREND_HEADERS, start=1):
            if h:
                self._header_cell(ws, 1, j, h)
        for j, h in enumerate(TREND_HEADERS_R2, start=1):
            if h:
                self._header_cell(ws, 2, j, h)
        for j, h in enumerate(TREND_HEADERS_R3, start=1):
            if h:
                self._header_cell(ws, 3, j, h)
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

        # R11：新签表头（复刻 golden）
        for j, h in enumerate(("期间", "类型", "当期数据（2026.6.1）", "",
                               "本年正常交付", "", "异常中", "", "合同消失", "",
                               "未来交付", "", "", "", "", ""), start=1):
            if h:
                self._header_cell(ws, 11, j, h)

        # R4-R18：递延 6 行 + 合计 + 新签 5 行 + 合计 + 共计
        for row_index in (4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18):
            r = row_map.get(row_index)
            if not r:
                continue
            excel_row = self._trend_excel_row(row_index)
            group = r.get("category_group") or ""
            status = r.get("status") or ""
            # golden：组标签仅组首行（递延合同/新签合同），其余行留空
            label = {"递延": "递延合同", "新签": "新签合同"}.get(group, group)
            if row_index in (4, 12):
                ws.cell(row=excel_row, column=1, value=label)
            if row_index not in (10, 17, 18):
                ws.cell(row=excel_row, column=2, value=status)
            # 数量列
            for col_idx, key in ((3, "init_count"), (5, "normal_count"),
                                 (7, "exception_count"), (9, "disappear_count"),
                                 (11, "future_count"), (13, "check_count")):
                self._body_cell(ws, excel_row, col_idx, r.get(key), FMT_INT)
            # 金额列：202606 有权威值则写；202609 红线（None）保持空 + 样式
            for col_idx, key in ((4, "init_amount_wan"), (6, "normal_amount_wan"),
                                 (8, "exception_amount_wan"),
                                 (10, "disappear_amount_wan"),
                                 (12, "future_amount_wan"), (14, "check_amount")):
                self._body_cell(ws, excel_row, col_idx, r.get(key), FMT_AMOUNT)
            # C15/C16 未立项/已立项（golden R4 实证：6/0；合计行 6/60）
            audit = {}
            if r.get("routing_audit"):
                try:
                    audit = json.loads(r["routing_audit"])
                except (json.JSONDecodeError, TypeError):
                    audit = {}
            self._body_cell(ws, excel_row, 15,
                            audit.get("unplanned_count", 0), FMT_INT)
            self._body_cell(ws, excel_row, 16,
                            audit.get("planned_count", 0), FMT_INT)
            # 样式应用到 C-N
            for j in range(3, 15):
                cell = ws.cell(row=excel_row, column=j)
                self._border(cell)
            # golden 合计行标签（A 列）
            if row_index == 10:
                ws.cell(row=excel_row, column=1, value="合计：")
            elif row_index == 17:
                ws.cell(row=excel_row, column=1, value="合计：")
            elif row_index == 18:
                ws.cell(row=excel_row, column=1, value="（递延+新签）共计：")
            # 合计行浅蓝底
            if row_index in (10, 17, 18):
                for j in range(1, 18):
                    ws.cell(row=excel_row, column=j).fill = PatternFill(
                        start_color=SUBHEADER_FILL, end_color=SUBHEADER_FILL,
                        fill_type="solid")

        # R19 新签预计确收率（golden：E19 标签 + F19 率值，其余列空）
        r19 = row_map.get(19)
        if r19:
            excel_row = self._trend_excel_row(19)
            ws.cell(row=excel_row, column=5, value="新签预计确收率")
            rate_cell = cell_map.get((19, 1))  # col_index=1 → 金额口径（golden F19）
            if rate_cell:
                try:
                    val = json.loads(rate_cell).get("value")
                    self._body_cell(ws, excel_row, 6, val, FMT_RATE)
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
        """ra_trend_row 行号 → Excel 行号（golden 行位 = row_index，R11 为新签表头）。"""
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
        # Rex 2026-11-24 D2：表头按 golden 规范覆盖（字体/填充/对齐）
        spec_sh = _spec_sheet(self._layout, self._cur_sheet)
        if spec_sh:
            st = self._style_of(spec_sh, row, col)
            if st.get("font"):
                cell.font = st["font"]
            if st.get("fill"):
                cell.fill = st["fill"]
            if st.get("align"):
                cell.alignment = st["align"]

    _DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?: 00:00:00)?$")
    _TIME_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})$")

    @classmethod
    def _coerce(cls, value: Any) -> Any:
        """DB 字符串日期/时间 → datetime（golden 为真日期型）。"""
        if isinstance(value, str):
            m = cls._DATE_RE.match(value)
            if m:
                try:
                    return datetime(int(m.group(1)), int(m.group(2)),
                                    int(m.group(3)))
                except ValueError:
                    return value
            m = cls._TIME_RE.match(value)
            if m:
                try:
                    return time(int(m.group(1)), int(m.group(2)),
                                int(m.group(3)))
                except ValueError:
                    return value
        return value

    def _body_cell(self, ws: Any, row: int, col: int, value: Any,
                   fmt: Optional[str] = None) -> None:
        value = self._coerce(value)
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
        # Rex 2026-11-24 D2：按 golden 版式覆盖字体/填充/对齐
        spec_sh = _spec_sheet(self._layout, self._cur_sheet)
        if spec_sh:
            st = self._style_of(spec_sh, row, col)
            if st.get("font"):
                cell.font = st["font"]
            if st.get("fill"):
                cell.fill = st["fill"]
            if st.get("align"):
                cell.alignment = st["align"]

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
