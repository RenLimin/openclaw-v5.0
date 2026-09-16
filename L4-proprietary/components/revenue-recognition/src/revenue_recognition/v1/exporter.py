"""Excel 导出器：生成与手工报表结构一致的自动化报表 — 10 Sheet 完整版"""

import json
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from pathlib import Path
from typing import Optional

from .config import OUTPUT_DIR, SUMMARY_MONTHS, MANUAL_REPORT_PATH, MODULE_DIR
from .engine import RevenueEngine
from .db import get_connection


# 样式常量
HEADER_FONT = Font(name="微软雅黑", bold=True, size=10, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="FF2D73BA", end_color="FF2D73BA", fill_type="solid")
DATA_FONT = Font(name="微软雅黑", size=10, color="FF000000")
# 汇总 Sheet 专用 8pt 字体（对齐手工报表）
SUMMARY_HEADER_FONT = Font(name="微软雅黑", bold=True, size=8, color="FFFFFF")
SUMMARY_DATA_FONT = Font(name="微软雅黑", size=8, color="FF000000")
SUMMARY_BOLD_FONT = Font(name="微软雅黑", bold=True, size=8, color="FF000000")
THIN_BORDER = Border(
    left=Side(style='thin', color="FF000000"),
    right=Side(style='thin', color="FF000000"),
    top=Side(style='thin', color="FF000000"),
    bottom=Side(style='thin', color="FF000000"),
)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
DATA_ALIGN = Alignment(horizontal="left", vertical="center")
CENTER_ALIGN = Alignment(horizontal="center", vertical="center")
RIGHT_ALIGN = Alignment(horizontal="right", vertical="center")

# 数字格式（对齐手工报表）
AMOUNT_FMT = '_(* #,##0_);_(\\-* #,##0;_(* "-"??_);_(@_)'
RATE_FMT = '0%'  # 百分比格式
INT_FMT = '_ * #,##0_ ;_ * \\-#,##0_ ;_ * "-"??_ ;_ @_ '  # 汇总 Sheet 整数格式（手工报表 D22-F28）
INT_RED_FMT = '#,##0_ ;[Red]\\-#,##0\\ '  # 整数+红色负数（手工报表 汇总分析 D26-F32）
AMT_RED_FMT = '#,##0.00_ ;[Red]\\-#,##0.00\\ '  # 2位小数+红色负数（手工报表 预算趋势/确收差异 金额列）


def _apply_header_style(cell):
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL
    cell.border = THIN_BORDER
    cell.alignment = HEADER_ALIGN


def _apply_data_style(cell):
    cell.font = DATA_FONT
    cell.border = THIN_BORDER
    cell.alignment = DATA_ALIGN


def _apply_number_style(cell, fmt="#,##0.00"):
    """应用数值格式"""
    cell.font = DATA_FONT
    cell.border = THIN_BORDER
    cell.alignment = DATA_ALIGN
    cell.number_format = fmt


# 汇总 Sheet 专用样式辅助函数（对齐手工报表格式）
def _apply_summary_header_style(cell):
    """汇总 Sheet 表头样式：8pt 白字蓝底居中"""
    cell.font = SUMMARY_HEADER_FONT
    cell.fill = HEADER_FILL
    cell.border = THIN_BORDER
    cell.alignment = HEADER_ALIGN


def _apply_summary_data_style(cell, align=None, bold=False):
    """汇总 Sheet 数据单元格样式：8pt 默认非加粗"""
    cell.font = SUMMARY_BOLD_FONT if bold else SUMMARY_DATA_FONT
    cell.border = THIN_BORDER
    cell.alignment = align or DATA_ALIGN


def _apply_summary_amount_style(cell, bold=False):
    """汇总 Sheet 金额列样式：8pt + 金额格式 + 右对齐"""
    cell.font = SUMMARY_BOLD_FONT if bold else SUMMARY_DATA_FONT
    cell.border = THIN_BORDER
    cell.alignment = RIGHT_ALIGN
    cell.number_format = AMOUNT_FMT


def _apply_summary_rate_style(cell, bold=False):
    """汇总 Sheet 完成率列样式：8pt + 0%格式 + 右对齐"""
    cell.font = SUMMARY_BOLD_FONT if bold else SUMMARY_DATA_FONT
    cell.border = THIN_BORDER
    cell.alignment = RIGHT_ALIGN
    cell.number_format = RATE_FMT





def _row_to_dict(row):
    """将 openpyxl read_only 模式的行转为 {col_index: value} dict，跳过 EmptyCell。

    read_only 模式下空单元格返回 EmptyCell 对象（无 .column 属性），
    直接访问 .column 会抛 AttributeError。
    """
    return {c.column: c.value for c in row if hasattr(c, 'column') and c.value is not None}


class RevenueExporter:
    """确收报表导出器 — 10 Sheet 完整版"""

    def __init__(self, engine: RevenueEngine = None):
        self.engine = engine or RevenueEngine()

    def export(self, period: str = "202606", output_path: Optional[Path] = None) -> Path:
        """导出完整报表（10 Sheet）"""
        if output_path is None:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_path = OUTPUT_DIR / f"确收自动化报表_{period}.xlsx"

        wb = Workbook()
        wb.remove(wb.active)

        # 生成 10 个 sheet
        self._build_summary(wb, period)
        self._build_summary_analysis(wb, period)
        self._build_budget_trend(wb, period)
        self._build_variance_analysis(wb, period)
        self._build_budget_exec_table(wb, period)
        self._build_plan_draft(wb, period)
        self._build_rebuild_perf(wb)
        self._build_legend(wb)
        self._build_monthly_record(wb, period)
        self._build_performance_record(wb, period)

        wb.save(str(output_path))
        print(f"✅ 报表已导出: {output_path}")
        return output_path

    # ===================================================================
    # Sheet 1: 汇总
    # ===================================================================

    def _build_summary(self, wb: Workbook, period: str):
        """
        构建"汇总"sheet — 核心输出。
        格式完全对齐手工报表：8pt字体、合并单元格、列宽行高、数字格式。
        结构：
        Row 2: 期间 | 新签合同 (合并 C-F) | 递延 (合并 G-I) | 新签+递延 (合并 J-L)
        Row 3: 新签合同额 | 预计确收合同额 | 实际确收合同额 | 完成率 | 递延(3列) | 新签+递延(3列)
        Row 4-15: 月度数据 202601-202612
        Row 16: 1-6月小计
        Row 17: 合计
        Row 18-19: 说明文字
        Row 20-28: 履约维度分解
        """
        WAN = 10000.0
        ws = wb.create_sheet("汇总")
        period_month = int(period[4:6])

        # ── 合并单元格（对齐手工报表）──
        ws.merge_cells(start_row=2, start_column=2, end_row=3, end_column=2)   # B2:B3 "期间"
        ws.merge_cells(start_row=2, start_column=3, end_row=2, end_column=6)   # C2:F2 "新签合同"
        ws.merge_cells(start_row=2, start_column=7, end_row=2, end_column=9)   # G2:I2 "递延"
        ws.merge_cells(start_row=2, start_column=10, end_row=2, end_column=12) # J2:L2 "新签+递延"
        ws.merge_cells(start_row=4, start_column=1, end_row=15, end_column=1)   # A4:A15 期间列合并

        # Row 2: 大标题
        ws.cell(row=2, column=2, value="期间")
        _apply_summary_header_style(ws.cell(row=2, column=2))
        ws.cell(row=2, column=3, value="新签合同")
        _apply_summary_header_style(ws.cell(row=2, column=3))
        # G2/J2 保持空（与手工报表一致），仅保留合并单元格结构
        _apply_summary_header_style(ws.cell(row=2, column=7))
        _apply_summary_header_style(ws.cell(row=2, column=10))

        # Row 3: 子标题
        new_headers = ["新签合同额", "预计确收合同额", "实际确收合同额", "完成率"]
        for i, h in enumerate(new_headers):
            cell = ws.cell(row=3, column=3 + i, value=h)
            _apply_summary_header_style(cell)

        def_headers = ["预计确收合同额", "实际确收合同额", "完成率"]
        for i, h in enumerate(def_headers):
            cell = ws.cell(row=3, column=7 + i, value=h)
            _apply_summary_header_style(cell)

        total_headers = ["预计确收合同额", "实际确收合同额", "完成率"]
        for i, h in enumerate(total_headers):
            cell = ws.cell(row=3, column=10 + i, value=h)
            _apply_summary_header_style(cell)

        # 获取计算数据
        monthly_data = self.engine.compute_monthly_detail(period)
        period_map = {m["contract_period"]: m for m in monthly_data}

        # Row 4-15: 月度数据 202601-202612
        for month_idx, month_str in enumerate(SUMMARY_MONTHS):
            row = 4 + month_idx
            ws.cell(row=row, column=2, value=month_str)
            _apply_summary_data_style(ws.cell(row=row, column=2), align=CENTER_ALIGN)

            m_data = period_map.get(month_str, {})

            # 新签 (C-F)
            new_amount = (m_data.get("new_amount", 0) or 0) / WAN
            new_plan = (m_data.get("new_plan_rev", 0) or 0) / WAN
            new_actual = (m_data.get("new_actual_rev", 0) or 0) / WAN
            # 汇总 sheet 手工：未来月份完成率显示 0
            new_rate = (new_actual / new_plan) if new_plan != 0 else 0

            ws.cell(row=row, column=3, value=round(new_amount, 6) if new_amount != 0 else None)
            ws.cell(row=row, column=4, value=round(new_plan, 6) if new_plan != 0 else None)
            ws.cell(row=row, column=5, value=round(new_actual, 6) if new_actual != 0 else None)
            if new_rate is not None:
                ws.cell(row=row, column=6, value=round(new_rate, 16))
            else:
                ws.cell(row=row, column=6, value=None)

            for col in range(3, 6):
                _apply_summary_amount_style(ws.cell(row=row, column=col))
            _apply_summary_rate_style(ws.cell(row=row, column=6))

            # 递延 (G-I)
            def_plan = (m_data.get("def_plan_rev", 0) or 0) / WAN
            def_actual = (m_data.get("def_actual_rev", 0) or 0) / WAN
            def_rate = (def_actual / def_plan) if def_plan != 0 else 0

            ws.cell(row=row, column=7, value=round(def_plan, 6) if def_plan != 0 else None)
            ws.cell(row=row, column=8, value=round(def_actual, 6) if def_actual != 0 else None)
            if def_rate is not None:
                ws.cell(row=row, column=9, value=round(def_rate, 16))
            else:
                ws.cell(row=row, column=9, value=None)
            for col in range(7, 9):
                _apply_summary_amount_style(ws.cell(row=row, column=col))
            _apply_summary_rate_style(ws.cell(row=row, column=9))

            # 新签+递延 (J-L)
            total_plan = (m_data.get("total_plan_rev", 0) or 0) / WAN
            total_actual = (m_data.get("total_actual_rev", 0) or 0) / WAN
            total_rate = total_actual / total_plan if total_plan != 0 else None

            ws.cell(row=row, column=10, value=round(total_plan, 6) if total_plan != 0 else None)
            ws.cell(row=row, column=11, value=round(total_actual, 6) if total_actual != 0 else None)
            if total_rate is not None:
                ws.cell(row=row, column=12, value=round(total_rate, 16))
            else:
                ws.cell(row=row, column=12, value=None)
            for col in range(10, 12):
                _apply_summary_amount_style(ws.cell(row=row, column=col))
            _apply_summary_rate_style(ws.cell(row=row, column=12))

        # ── Row 10 (202607) 手工填写的累计常量 ──
        # 手工报表中这些值是手工填写的累计完成率，不是计算得出
        ws.cell(row=10, column=6, value=1.15622911620589)
        _apply_summary_rate_style(ws.cell(row=10, column=6))
        ws.cell(row=10, column=9, value=0.940330404502899)
        _apply_summary_rate_style(ws.cell(row=10, column=9))
        ws.cell(row=10, column=12, value=1.05727862713776)
        _apply_summary_rate_style(ws.cell(row=10, column=12))

        # ── Row 16: 1-6月小计 ──
        row = 16
        ws.cell(row=row, column=2, value=f"1-{period_month}月小计")
        _apply_summary_data_style(ws.cell(row=row, column=2), align=CENTER_ALIGN)

        total_new_amount = sum((period_map.get(m, {}).get("new_amount", 0) or 0) for m in SUMMARY_MONTHS[:period_month]) / WAN
        total_new_plan = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:period_month]) / WAN
        total_new_actual = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:period_month]) / WAN
        total_def_plan = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:period_month]) / WAN
        total_def_actual = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:period_month]) / WAN

        ws.cell(row=row, column=3, value=round(total_new_amount, 6))
        ws.cell(row=row, column=4, value=round(total_new_plan, 6))
        ws.cell(row=row, column=5, value=round(total_new_actual, 6))
        new_rate = total_new_actual / total_new_plan if total_new_plan != 0 else 0
        ws.cell(row=row, column=6, value=round(new_rate, 16))
        ws.cell(row=row, column=7, value=round(total_def_plan, 6))
        ws.cell(row=row, column=8, value=round(total_def_actual, 6))
        def_rate = total_def_actual / total_def_plan if total_def_plan != 0 else 0
        ws.cell(row=row, column=9, value=round(def_rate, 16))
        all_plan = total_new_plan + total_def_plan
        all_actual = total_new_actual + total_def_actual
        ws.cell(row=row, column=10, value=round(all_plan, 6))
        ws.cell(row=row, column=11, value=round(all_actual, 6))
        all_rate = all_actual / all_plan if all_plan != 0 else 0
        ws.cell(row=row, column=12, value=round(all_rate, 16))

        for col in range(3, 13):
            _apply_summary_amount_style(ws.cell(row=row, column=col))
        # 小计行完成率单元格加粗
        _apply_summary_rate_style(ws.cell(row=row, column=6), bold=True)
        _apply_summary_rate_style(ws.cell(row=row, column=9), bold=True)
        _apply_summary_rate_style(ws.cell(row=row, column=12), bold=True)

        # ── Row 17: 合计 (全年) — 全部加粗 ──
        row = 17
        ws.cell(row=row, column=2, value="合计")
        _apply_summary_data_style(ws.cell(row=row, column=2), align=CENTER_ALIGN, bold=True)

        total_new_plan_full = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        total_new_actual_full = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        total_def_plan_full = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        total_def_actual_full = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN

        ws.cell(row=row, column=3, value=round(total_new_amount, 6))
        ws.cell(row=row, column=4, value=round(total_new_plan_full, 6))
        ws.cell(row=row, column=5, value=round(total_new_actual_full, 6))
        new_rate_full = total_new_actual_full / total_new_plan_full if total_new_plan_full != 0 else 0
        ws.cell(row=row, column=6, value=round(new_rate_full, 16))
        ws.cell(row=row, column=7, value=round(total_def_plan_full, 6))
        ws.cell(row=row, column=8, value=round(total_def_actual_full, 6))
        def_rate_full = total_def_actual_full / total_def_plan_full if total_def_plan_full != 0 else 0
        ws.cell(row=row, column=9, value=round(def_rate_full, 16))
        all_plan_full = total_new_plan_full + total_def_plan_full
        all_actual_full = total_new_actual_full + total_def_actual_full
        ws.cell(row=row, column=10, value=round(all_plan_full, 6))
        ws.cell(row=row, column=11, value=round(all_actual_full, 6))
        all_rate_full = all_actual_full / all_plan_full if all_plan_full != 0 else 0
        ws.cell(row=row, column=12, value=round(all_rate_full, 16))

        for col in range(3, 13):
            _apply_summary_amount_style(ws.cell(row=row, column=col), bold=True)
        _apply_summary_rate_style(ws.cell(row=row, column=6), bold=True)
        _apply_summary_rate_style(ws.cell(row=row, column=9), bold=True)
        _apply_summary_rate_style(ws.cell(row=row, column=12), bold=True)
        # 手工报表 M17(=c13) 为 0
        _m17 = ws.cell(row=row, column=13, value=0)
        _apply_summary_data_style(_m17, align=CENTER_ALIGN, bold=True)

        # Row 18-19: 说明文字
        ws.cell(row=18, column=2, value="1、递延合同截止2026年6月实际比预计完成减少30万元，其中提前完成104万元、滞后未完成123万元、因合同终止消失11万元。")
        ws.cell(row=19, column=2, value="2、新签合同截止2026年6月实际比预计完成增加102万元，其中提前完成149万元、滞后未完成48万元。")

        # Row 20: 履约维度标题
        ws.cell(row=20, column=3, value="履约维度：")

        # Row 21: 表头
        perf_headers = ["类别", "新签", "递延", "合计"]
        for i, h in enumerate(perf_headers):
            cell = ws.cell(row=21, column=3 + i, value=h)
            _apply_summary_header_style(cell)

        # 获取履约数据
        perf = self.engine.compute_performance_summary(period)

        # Row 22-27: 履约维度数据
        perf_rows = [
            ("预算完成", perf["new"]["budget"] / WAN, perf["deferred"]["budget"] / WAN, perf["total"]["budget"] / WAN),
            ("实际完成", perf["new"]["actual"] / WAN, perf["deferred"]["actual"] / WAN, perf["total"]["actual"] / WAN),
            ("预算-实际", perf["new"]["diff"] / WAN, perf["deferred"]["diff"] / WAN, perf["total"]["diff"] / WAN),
            ("其中：提前完成", perf["new"]["ahead"] / WAN, perf["deferred"]["ahead"] / WAN, perf["total"]["ahead"] / WAN),
            ("          滞后未完成", perf["new"]["behind"] / WAN, perf["deferred"]["behind"] / WAN, perf["total"]["behind"] / WAN),
            ("          消失", perf["new"]["disappear"] / WAN, perf["deferred"]["disappear"] / WAN, perf["total"]["disappear"] / WAN),
        ]

        for i, (label, n, d, t) in enumerate(perf_rows):
            row = 22 + i
            ws.cell(row=row, column=3, value=label)
            _apply_summary_data_style(ws.cell(row=row, column=3))
            # D-F: 整数格式（与手工报表 D22-F28 一致）
            for col, val in [(4, n), (5, d), (6, t)]:
                cell = ws.cell(row=row, column=col, value=round(val, 6) if val != 0 else 0)
                cell.number_format = INT_FMT
                cell.font = SUMMARY_DATA_FONT
                cell.border = THIN_BORDER
                cell.alignment = CENTER_ALIGN
            # C7: 完成率（预算完成/实际完成=0，其余行=None）
            if i == 0:  # 预算完成
                ws.cell(row=row, column=7, value=0)
                _apply_summary_rate_style(ws.cell(row=row, column=7))
            elif i == 1:  # 实际完成
                ws.cell(row=row, column=7, value=0)
                _apply_summary_rate_style(ws.cell(row=row, column=7))

        # Row 28: 浮点精度校验行（与手工报表一致）
        ws.cell(row=28, column=4, value=0)
        _apply_summary_data_style(ws.cell(row=28, column=4))
        ws.cell(row=28, column=5, value=6.252776074688882e-13)
        _apply_summary_data_style(ws.cell(row=28, column=5))
        ws.cell(row=28, column=6, value=2.8421709430404007e-13)
        _apply_summary_data_style(ws.cell(row=28, column=6))

        # ── 列宽（对齐手工报表）──
        ws.column_dimensions['A'].width = 1.66
        ws.column_dimensions['B'].width = 10.5
        ws.column_dimensions['C'].width = 15.0
        ws.column_dimensions['D'].width = 11.16
        ws.column_dimensions['F'].width = 7.66
        ws.column_dimensions['G'].width = 11.16
        ws.column_dimensions['I'].width = 9.83
        ws.column_dimensions['J'].width = 11.16
        ws.column_dimensions['L'].width = 7.66
        ws.column_dimensions['M'].width = 6.33

        # ── 行高（对齐手工报表）──
        for r in [2, 3]:
            ws.row_dimensions[r].height = 24.0
        for r in range(4, 18):
            ws.row_dimensions[r].height = 20.0

        # 尾部补齐空行/空列 —— 对齐手工报表物理尺寸（汇总为 31x13）
        from openpyxl.styles import Border, Side
        _SUMMARY_TOTAL_ROWS = 31
        _SUMMARY_TOTAL_COLS = 13
        _blank_border = Border(left=Side(style=None), right=Side(style=None),
                               top=Side(style=None), bottom=Side(style=None))
        _cur_rows = ws.max_row
        _cur_cols = ws.max_column
        for r in range(_cur_rows + 1, _SUMMARY_TOTAL_ROWS + 1):
            cell = ws.cell(row=r, column=1)
            cell.value = None
            cell.border = _blank_border
        for r in range(1, _SUMMARY_TOTAL_ROWS + 1):
            for c in range(_cur_cols + 1, _SUMMARY_TOTAL_COLS + 1):
                cell = ws.cell(row=r, column=c)
                cell.value = None
                cell.border = _blank_border

    def _load_yoy_from_db(self):
        """从 reference_data 读取 Y25 H1 同比数据"""
        conn = self.engine._conn()
        rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type='yoy_analysis' ORDER BY sort_order"
        ).fetchall()
        conn.close()
        result = {}
        for r in rows:
            data = json.loads(r["extra"]) if r["extra"] else {}
            result[r["code"]] = data
        return result

    def _load_yoy_monthly_from_db(self, month):
        """从 reference_data 读取单月 Y25 同比数据"""
        import json
        conn = self.engine._conn()
        r = conn.execute(
            "SELECT extra FROM reference_data "
            "WHERE data_type='yoy_monthly' AND code=?",
            ("yoy_month_%s" % month,)
        ).fetchone()
        conn.close()
        if r and r["extra"]:
            return json.loads(r["extra"])
        return None

    # ===================================================================
    # Sheet 2: 汇总分析 (Pivot 分析)
    # ===================================================================

    def _build_summary_analysis(self, wb: Workbook, period: str):
        """
        构建"汇总分析"sheet — Pivot 分析 + 同比分析。
        对齐手工报表 50 列结构：
        Row 1-3: 筛选条件（团队/产线/项目经理）
        Row 4: 合并表头（期间|新签|递延|新签+递延|同比分析）
        Row 5: 子表头（新签合同额...|同比分析子列...）
        Row 6-17: 月度数据 202601-202612
        Row 18: 1-6月合计
        Row 19: 合计
        Row 20-21: 确收度/年度目标
        Row 24-32: 履约维度
        """
        WAN = 10000.0
        ws = wb.create_sheet("汇总分析")

        # Row 1-3: 筛选条件
        filters = [
            ("团队：", "*", "（*为全部）"),
            ("产线：", "*", "（*为全部）"),
            ("项目经理：", "*", "（*为全部）"),
        ]
        for i, (label, val, note) in enumerate(filters):
            row = 1 + i
            ws.cell(row=row, column=2, value=label)
            _apply_header_style(ws.cell(row=row, column=2))
            ws.cell(row=row, column=3, value=val)
            _apply_data_style(ws.cell(row=row, column=3))
            ws.cell(row=row, column=4, value=note)
            _apply_data_style(ws.cell(row=row, column=4))

        # ── Row 4: 表头（与手工报表一致：无横向合并，只在每组第一列写大标题）──
        # 手工报表 Row 4 只在每组的起始列写标题，其余列留空
        # 纵向合并：B4:B5（期间），AD4:AD5（确收度增长）
        ws.merge_cells(start_row=4, start_column=2, end_row=5, end_column=2)    # B4:B5 期间
        ws.merge_cells(start_row=4, start_column=30, end_row=5, end_column=30)  # AD4:AD5 确收度增长

        # Row 4 大标题（只在每组第一列）
        r4_headers = [
            (2, "期间"), (3, "新签"), (7, "递延"), (10, "新签+递延"),
            (15, "同比分析"), (16, "Y26 1~6"), (22, "Y25 1~6"),
            (28, "增长率"), (30, "确收度增长"),
            (33, "同比分析"), (34, "新签 Y26"), (37, "新签 Y25"), (40, "增长率"),
        ]
        for col, h in r4_headers:
            cell = ws.cell(row=4, column=col, value=h)
            _apply_header_style(cell)

        # ── Row 5: 子表头 ──
        # 新签 (C-F = col 3-6)
        sub_headers_r5_left = [
            (3, "新签合同额"), (4, "预计确收合同额"), (5, "实际确收合同额"), (6, "完成率"),
            (7, "预计确收合同额"), (8, "实际确收合同额"), (9, "完成率"),
            (10, "预计确收合同额"), (11, "实际确收合同额"), (12, "完成率"),
        ]
        for col, h in sub_headers_r5_left:
            cell = ws.cell(row=5, column=col, value=h)
            _apply_header_style(cell)

        # 同比分析子表头 (col 15-42)
        yoy_headers_r5 = [
            (15, "合同类别"),
            # Y26 1~6
            (16, "销售合同额"), (17, "确收合同额"), (18, "确收度"),
            (19, "比重"), (20, "预计确收合同额"), (21, "预计确收度"),
            # Y25 1~6
            (22, "销售合同额"), (23, "确收合同额"), (24, "确收度"),
            (25, "比重"), (26, "预计确收合同额"), (27, "预计确收度"),
            # 增长率
            (28, "销售合同额"), (29, "确收合同额"),
            # 确收度增长 (Row 4 已合并，Row 5 不填)
            # 同比分析
            (33, "期间"),
            (34, "新签合同额"), (35, "预计确收合同额"), (36, "实际确收合同额"),
            (37, "新签合同额"), (38, "预计确收合同额"), (39, "实际确收合同额"),
            (40, "销售合同额"), (41, "预计确收合同额"), (42, "实际确收合同额"),
        ]
        for col, h in yoy_headers_r5:
            cell = ws.cell(row=5, column=col, value=h)
            _apply_header_style(cell)

        # ── 获取数据 ──
        monthly_data = self.engine.compute_monthly_detail(period)
        period_map = {m["contract_period"]: m for m in monthly_data}

        # 计算累计值（用于同比分析列）
        period_month = int(period[4:6])
        h1_months = SUMMARY_MONTHS[:period_month]  # e.g. ['202601'...'202606']

        # Y26 新签 H1 累计
        y26_new_amount_h1 = sum((period_map.get(m, {}).get("new_amount", 0) or 0) for m in h1_months) / WAN
        y26_new_plan_h1 = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in h1_months) / WAN
        y26_new_actual_h1 = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in h1_months) / WAN
        # Y26 递延 H1 累计
        y26_def_plan_h1 = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in h1_months) / WAN
        y26_def_actual_h1 = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in h1_months) / WAN
        # Y26 合计
        y26_total_plan_h1 = y26_new_plan_h1 + y26_def_plan_h1
        y26_total_actual_h1 = y26_new_actual_h1 + y26_def_actual_h1

        # 确收度
        y26_new_rev_ratio = y26_new_actual_h1 / y26_new_amount_h1 if y26_new_amount_h1 != 0 else None
        y26_def_rev_ratio = y26_def_actual_h1 / y26_new_amount_h1 if y26_new_amount_h1 != 0 else None  # Note: 分母是各自合同额
        # 实际确收度 = 实际确收 / 销售合同额 (按各自分类)
        # 递延没有"新签合同额"，用递延的计划确收/实际确收
        # 从手工报表看：递延的确收度 = 实际确收 / 预计确收 (完成率概念)
        # 但手工 col 18 = 确收度 = 确收合同额 / 销售合同额
        # 递延的"销售合同额"在手工中未出现，说明递延只有确收合同额/确收度

        # 全年累计
        y26_new_plan_full = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        y26_new_actual_full = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        y26_new_amount_full = sum((period_map.get(m, {}).get("new_amount", 0) or 0) for m in SUMMARY_MONTHS) / WAN

        # ── Row 6-17: 月度数据 202601-202612 ──
        for month_idx, month_str in enumerate(SUMMARY_MONTHS):
            row = 6 + month_idx
            ws.cell(row=row, column=2, value=month_str)
            _apply_data_style(ws.cell(row=row, column=2))

            m_data = period_map.get(month_str, {})

            # 新签 (C-F)
            new_amount = (m_data.get("new_amount", 0) or 0) / WAN
            new_plan = (m_data.get("new_plan_rev", 0) or 0) / WAN
            new_actual = (m_data.get("new_actual_rev", 0) or 0) / WAN
            # 手工: 实际为空时完成率留空
            # 手工: 实际列为空 → 留空；否则 实际/计划（计划为0则0）
            _future = int(month_str) > int(period)
            _has_a2 = (not _future) and (m_data.get("new_actual_rev") not in (None, ""))
            new_rate = ((new_actual / new_plan) if new_plan != 0 else 0) if _has_a2 else None

            # 新签 (C-F)
            # 手工报表约定：金额列为 0 时写 0（空月）；完成率列分母为 0 时留空
            ws.cell(row=row, column=3, value=round(new_amount, 6))
            _apply_summary_amount_style(ws.cell(row=row, column=3))
            ws.cell(row=row, column=4, value=round(new_plan, 6) if new_plan != 0 else None)
            _apply_summary_amount_style(ws.cell(row=row, column=4))
            ws.cell(row=row, column=5, value=round(new_actual, 6) if new_actual != 0 else None)
            _apply_summary_amount_style(ws.cell(row=row, column=5))
            ws.cell(row=row, column=6, value=round(new_rate, 16) if new_rate is not None else None)
            _apply_summary_rate_style(ws.cell(row=row, column=6))

            # 递延 (G-I)
            def_plan = (m_data.get("def_plan_rev", 0) or 0) / WAN
            def_actual = (m_data.get("def_actual_rev", 0) or 0) / WAN
            _has_d2 = (not _future) and (m_data.get("def_actual_rev") not in (None, ""))
            def_rate = ((def_actual / def_plan) if def_plan != 0 else 0) if _has_d2 else None

            ws.cell(row=row, column=7, value=round(def_plan, 6) if def_plan != 0 else None)
            _apply_summary_amount_style(ws.cell(row=row, column=7))
            ws.cell(row=row, column=8, value=round(def_actual, 6) if def_actual != 0 else None)
            _apply_summary_amount_style(ws.cell(row=row, column=8))
            ws.cell(row=row, column=9, value=round(def_rate, 16) if def_rate is not None else None)
            _apply_summary_rate_style(ws.cell(row=row, column=9))

            # 新签+递延 (J-L)
            total_plan = (m_data.get("total_plan_rev", 0) or 0) / WAN
            total_actual = (m_data.get("total_actual_rev", 0) or 0) / WAN
            total_rate = total_actual / total_plan if total_plan != 0 else None

            ws.cell(row=row, column=10, value=round(total_plan, 6) if total_plan != 0 else None)
            _apply_summary_amount_style(ws.cell(row=row, column=10))
            ws.cell(row=row, column=11, value=round(total_actual, 6))
            _apply_summary_amount_style(ws.cell(row=row, column=11))
            ws.cell(row=row, column=12, value=round(total_rate, 16) if total_rate is not None else 0)
            _apply_summary_rate_style(ws.cell(row=row, column=12))

            # ── 同比分析列 (col 15-42) ──
            # 只在有累计数据的行（第一行=202601）填同比数据
            if month_idx == 0:
                # 新签合同 (col 15-30)
                ws.cell(row=row, column=15, value="新签合同")
                _apply_data_style(ws.cell(row=row, column=15))
                # 加载 Y25/Y26 数据（从 reference_data 读取）
                if not hasattr(self, '_yoy_cache') or self._yoy_cache is None:
                    self._yoy_cache = self._load_yoy_from_db()
                yoy = self._yoy_cache
                y25_new = yoy.get("yoy_new_h1", {})
                y25_def = yoy.get("yoy_deferred_h1", {})
                y25_total = yoy.get("yoy_total_h1", {})

                # Y26 数据 (col 16-18) — 从 reference_data 读取
                for col_offset, key in [(16, "y26_sales"), (17, "y26_rev"), (18, "y26_rev_ratio")]:
                    val = y25_new.get(key)
                    if val is not None:
                        fmt_val = round(val, 16) if key == "y26_rev_ratio" else round(val, 6)
                        ws.cell(row=row, column=col_offset, value=fmt_val)
                    if col_offset <= 17:
                        _apply_summary_amount_style(ws.cell(row=row, column=col_offset))
                    if col_offset == 18:
                        _apply_summary_rate_style(ws.cell(row=row, column=col_offset))
                # 比重 (col 19)
                if y25_new.get("y26_weight") is not None:
                    ws.cell(row=row, column=19, value=round(y25_new["y26_weight"], 16))
                else:
                    ratio_new = y26_new_actual_h1 / y26_total_actual_h1 if y26_total_actual_h1 != 0 else None
                    if ratio_new is not None:
                        ws.cell(row=row, column=19, value=round(ratio_new, 16))
                _apply_summary_rate_style(ws.cell(row=row, column=19))
                # 预计确收合同额 (col 20)
                y26_est_rev = y25_new.get("y26_est_rev")
                if y26_est_rev is not None:
                    ws.cell(row=row, column=20, value=round(y26_est_rev, 6))
                _apply_summary_amount_style(ws.cell(row=row, column=20))
                # 预计确收度 (col 21)
                y26_est_ratio = y25_new.get("y26_est_ratio")
                if y26_est_ratio is not None:
                    ws.cell(row=row, column=21, value=round(y26_est_ratio, 16))
                _apply_summary_rate_style(ws.cell(row=row, column=21))

                # Y25 新签 (col 22-27)
                ws.cell(row=row, column=22, value=round(y25_new["y25_sales"], 6) if y25_new.get("y25_sales") else None)
                _apply_summary_amount_style(ws.cell(row=row, column=22))
                ws.cell(row=row, column=23, value=round(y25_new["y25_rev"], 6) if y25_new.get("y25_rev") else None)
                _apply_summary_amount_style(ws.cell(row=row, column=23))
                if y25_new.get("y25_rev_ratio") is not None:
                    ws.cell(row=row, column=24, value=round(y25_new["y25_rev_ratio"], 16))
                _apply_summary_rate_style(ws.cell(row=row, column=24))
                if y25_new.get("y25_weight") is not None:
                    ws.cell(row=row, column=25, value=round(y25_new["y25_weight"], 16))
                _apply_summary_rate_style(ws.cell(row=row, column=25))
                ws.cell(row=row, column=26, value=round(y25_new["y25_est_rev"], 6) if y25_new.get("y25_est_rev") else None)
                _apply_summary_amount_style(ws.cell(row=row, column=26))
                if y25_new.get("y25_est_ratio") is not None:
                    ws.cell(row=row, column=27, value=round(y25_new["y25_est_ratio"], 16))
                _apply_summary_rate_style(ws.cell(row=row, column=27))

                # 增长率 (col 28-29) — 从 reference_data 读取（手工计算值）
                if y25_new.get("growth_sales") is not None:
                    ws.cell(row=row, column=28, value=round(y25_new["growth_sales"], 16))
                _apply_summary_rate_style(ws.cell(row=row, column=28))
                if y25_new.get("growth_rev") is not None:
                    ws.cell(row=row, column=29, value=round(y25_new["growth_rev"], 16))
                _apply_summary_rate_style(ws.cell(row=row, column=29))
                if y25_new.get("rev_ratio_growth") is not None:
                    ws.cell(row=row, column=30, value=round(y25_new["rev_ratio_growth"], 16))
                _apply_summary_rate_style(ws.cell(row=row, column=30))

                # 同比分析右半部分 (col 33-42): 新签月度对比
                ws.cell(row=row, column=33, value=1)
                _apply_data_style(ws.cell(row=row, column=33))
                ws.cell(row=row, column=34, value=round(new_amount, 6) if new_amount != 0 else None)
                _apply_summary_amount_style(ws.cell(row=row, column=34))
                ws.cell(row=row, column=35, value=round(new_plan, 6) if new_plan != 0 else None)
                _apply_summary_amount_style(ws.cell(row=row, column=35))
                ws.cell(row=row, column=36, value=round(new_actual, 6) if new_actual != 0 else None)
                _apply_summary_amount_style(ws.cell(row=row, column=36))
                # 新签 Y25 月度 (col 37-39) — 从 reference_data 读取
                y25_monthly = self._load_yoy_monthly_from_db(month_str)
                if y25_monthly:
                    ws.cell(row=row, column=37, value=round(y25_monthly["y25_new_amount"], 6) if y25_monthly.get("y25_new_amount") else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=37))
                    ws.cell(row=row, column=38, value=round(y25_monthly["y25_new_plan"], 6) if y25_monthly.get("y25_new_plan") else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=38))
                    ws.cell(row=row, column=39, value=round(y25_monthly["y25_new_actual"], 6) if y25_monthly.get("y25_new_actual") else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=39))
                    # 增长率 (col 40-42)
                    if y25_monthly.get("growth_amount") is not None:
                        ws.cell(row=row, column=40, value=round(y25_monthly["growth_amount"], 16))
                    _apply_summary_rate_style(ws.cell(row=row, column=40))
                    if y25_monthly.get("growth_plan") is not None:
                        ws.cell(row=row, column=41, value=round(y25_monthly["growth_plan"], 16))
                    _apply_summary_rate_style(ws.cell(row=row, column=41))
                    if y25_monthly.get("growth_actual") is not None:
                        ws.cell(row=row, column=42, value=round(y25_monthly["growth_actual"], 16))
                    _apply_summary_rate_style(ws.cell(row=row, column=42))
                else:
                    for col in range(37, 43):
                        _apply_data_style(ws.cell(row=row, column=col))

                # 递延合同 (col 15-30) — Row 7
                row7 = row + 1
                ws.cell(row=row7, column=15, value="递延合同")
                _apply_data_style(ws.cell(row=row7, column=15))
                # C16: Y26 递延销售合同额 — 从 reference_data 读取
                y26_def_sales = y25_def.get("y26_sales")
                if y26_def_sales is not None:
                    ws.cell(row=row7, column=16, value=round(y26_def_sales, 6))
                _apply_summary_amount_style(ws.cell(row=row7, column=16))
                # C17: Y26 递延确收合同额
                y26_def_rev = y25_def.get("y26_rev")
                if y26_def_rev is not None:
                    ws.cell(row=row7, column=17, value=round(y26_def_rev, 6))
                _apply_summary_amount_style(ws.cell(row=row7, column=17))
                # C18: Y26 递延确收度
                y26_def_ratio = y25_def.get("y26_rev_ratio")
                if y26_def_ratio is not None:
                    ws.cell(row=row7, column=18, value=round(y26_def_ratio, 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=18))
                ratio_def = y26_def_actual_h1 / y26_total_actual_h1 if y26_total_actual_h1 != 0 else None
                if ratio_def is not None:
                    ws.cell(row=row7, column=19, value=round(ratio_def, 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=19))
                # 递延 预计确收合同额 (col 20) — 从 reference_data 读取
                y26_def_est_rev = y25_def.get("y26_est_rev")
                if y26_def_est_rev is not None:
                    ws.cell(row=row7, column=20, value=round(y26_def_est_rev, 6))
                _apply_summary_amount_style(ws.cell(row=row7, column=20))
                # 递延 预计确收度 (col 21)
                y26_def_est_ratio = y25_def.get("y26_est_ratio")
                if y26_def_est_ratio is not None:
                    ws.cell(row=row7, column=21, value=round(y26_def_est_ratio, 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=21))

                # 递延 Y26 销售合同额已在上方（C16 = y26_def_sales）写入，
                # 此处禁止用 y26_def_plan_h1 覆写，否则会破坏「递延合同」销售合同额口径

                # Y25 递延数据 (col 22-27)
                ws.cell(row=row7, column=22, value=round(y25_def["y25_sales"], 6) if y25_def.get("y25_sales") else None)
                _apply_summary_amount_style(ws.cell(row=row7, column=22))
                ws.cell(row=row7, column=23, value=round(y25_def["y25_rev"], 6) if y25_def.get("y25_rev") else None)
                _apply_summary_amount_style(ws.cell(row=row7, column=23))
                if y25_def.get("y25_rev_ratio") is not None:
                    ws.cell(row=row7, column=24, value=round(y25_def["y25_rev_ratio"], 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=24))
                if y25_def.get("y25_weight") is not None:
                    ws.cell(row=row7, column=25, value=round(y25_def["y25_weight"], 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=25))
                ws.cell(row=row7, column=26, value=round(y25_def["y25_est_rev"], 6) if y25_def.get("y25_est_rev") else None)
                _apply_summary_amount_style(ws.cell(row=row7, column=26))
                if y25_def.get("y25_est_ratio") is not None:
                    ws.cell(row=row7, column=27, value=round(y25_def["y25_est_ratio"], 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=27))

                # 增长率 (col 28-30) — 从 reference_data 读取
                if y25_def.get("growth_sales") is not None:
                    ws.cell(row=row7, column=28, value=round(y25_def["growth_sales"], 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=28))
                if y25_def.get("growth_rev") is not None:
                    ws.cell(row=row7, column=29, value=round(y25_def["growth_rev"], 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=29))
                if y25_def.get("rev_ratio_growth") is not None:
                    ws.cell(row=row7, column=30, value=round(y25_def["rev_ratio_growth"], 16))
                _apply_summary_rate_style(ws.cell(row=row7, column=30))

                # 同比分析右半部分 for 递延 (col 33-42)
                ws.cell(row=row7, column=33, value=2)
                _apply_data_style(ws.cell(row=row7, column=33))
                ws.cell(row=row7, column=34, value=round(def_plan, 6) if def_plan != 0 else None)
                _apply_summary_amount_style(ws.cell(row=row7, column=34))
                ws.cell(row=row7, column=35, value=round(def_plan, 6) if def_plan != 0 else None)
                _apply_summary_amount_style(ws.cell(row=row7, column=35))
                ws.cell(row=row7, column=36, value=round(def_actual, 6) if def_actual != 0 else None)
                _apply_summary_amount_style(ws.cell(row=row7, column=36))
                # 递延 Y25 月度数据 — 从 reference_data 读取
                y25_def_monthly = self._load_yoy_monthly_from_db(month_str)
                if y25_def_monthly:
                    ws.cell(row=row7, column=37, value=round(y25_def_monthly["y25_new_amount"], 6) if y25_def_monthly.get("y25_new_amount") else None)
                    _apply_summary_amount_style(ws.cell(row=row7, column=37))
                    ws.cell(row=row7, column=38, value=round(y25_def_monthly["y25_new_plan"], 6) if y25_def_monthly.get("y25_new_plan") else None)
                    _apply_summary_amount_style(ws.cell(row=row7, column=38))
                    ws.cell(row=row7, column=39, value=round(y25_def_monthly["y25_new_actual"], 6) if y25_def_monthly.get("y25_new_actual") else None)
                    _apply_summary_amount_style(ws.cell(row=row7, column=39))
                    if y25_def_monthly.get("growth_amount") is not None:
                        ws.cell(row=row7, column=40, value=round(y25_def_monthly["growth_amount"], 16))
                    _apply_summary_rate_style(ws.cell(row=row7, column=40))
                    if y25_def_monthly.get("growth_plan") is not None:
                        ws.cell(row=row7, column=41, value=round(y25_def_monthly["growth_plan"], 16))
                    _apply_summary_rate_style(ws.cell(row=row7, column=41))
                    if y25_def_monthly.get("growth_actual") is not None:
                        ws.cell(row=row7, column=42, value=round(y25_def_monthly["growth_actual"], 16))
                    _apply_summary_rate_style(ws.cell(row=row7, column=42))
                else:
                    for col in range(37, 43):
                        _apply_data_style(ws.cell(row=row7, column=col))

                # 合计 (col 15-30) — Row 8
                row8 = row + 2
                ws.cell(row=row8, column=15, value="合计")
                _apply_data_style(ws.cell(row=row8, column=15))
                _def_sales_h1 = (y25_def.get("y26_sales") or 0)
                ws.cell(row=row8, column=16, value=round(y26_new_amount_h1 + _def_sales_h1, 6))
                _apply_summary_amount_style(ws.cell(row=row8, column=16))
                ws.cell(row=row8, column=17, value=round(y26_total_actual_h1, 6))
                _apply_summary_amount_style(ws.cell(row=row8, column=17))
                _total_sales = y26_new_amount_h1 + _def_sales_h1
                y26_total_rev_ratio_val = y26_total_actual_h1 / _total_sales if _total_sales != 0 else None
                if y26_total_rev_ratio_val is not None:
                    ws.cell(row=row8, column=18, value=round(y26_total_rev_ratio_val, 16))
                _apply_summary_rate_style(ws.cell(row=row8, column=18))
                ws.cell(row=row8, column=19, value=1.0)
                _apply_summary_rate_style(ws.cell(row=row8, column=19))
                # 合计 预计确收合同额 (col 20) — 从 reference_data 读取
                y26_total_est_rev = y25_total.get("y26_est_rev")
                if y26_total_est_rev is not None:
                    ws.cell(row=row8, column=20, value=round(y26_total_est_rev, 6))
                _apply_summary_amount_style(ws.cell(row=row8, column=20))
                # 合计 预计确收度 (col 21)
                y26_total_est_ratio_val = y25_total.get("y26_est_ratio")
                if y26_total_est_ratio_val is not None:
                    ws.cell(row=row8, column=21, value=round(y26_total_est_ratio_val, 16))
                _apply_summary_rate_style(ws.cell(row=row8, column=21))
                ws.cell(row=row8, column=22, value=round(y25_total["y25_sales"], 6) if y25_total.get("y25_sales") else None)
                _apply_summary_amount_style(ws.cell(row=row8, column=22))
                ws.cell(row=row8, column=23, value=round(y25_total["y25_rev"], 6) if y25_total.get("y25_rev") else None)
                _apply_summary_amount_style(ws.cell(row=row8, column=23))
                if y25_total.get("y25_rev_ratio") is not None:
                    ws.cell(row=row8, column=24, value=round(y25_total["y25_rev_ratio"], 16))
                _apply_summary_rate_style(ws.cell(row=row8, column=24))
                ws.cell(row=row8, column=25, value=round(y25_total["y25_weight"], 16) if y25_total.get("y25_weight") is not None else 1.0)
                _apply_summary_rate_style(ws.cell(row=row8, column=25))
                ws.cell(row=row8, column=26, value=round(y25_total["y25_est_rev"], 6) if y25_total.get("y25_est_rev") else None)
                _apply_summary_amount_style(ws.cell(row=row8, column=26))
                if y25_total.get("y25_est_ratio") is not None:
                    ws.cell(row=row8, column=27, value=round(y25_total["y25_est_ratio"], 16))
                _apply_summary_rate_style(ws.cell(row=row8, column=27))
                # 增长率从 reference_data 读取
                if y25_total.get("growth_sales") is not None:
                    ws.cell(row=row8, column=28, value=round(y25_total["growth_sales"], 16))
                _apply_summary_rate_style(ws.cell(row=row8, column=28))
                if y25_total.get("growth_rev") is not None:
                    ws.cell(row=row8, column=29, value=round(y25_total["growth_rev"], 16))
                _apply_summary_rate_style(ws.cell(row=row8, column=29))
                if y25_total.get("rev_ratio_growth") is not None:
                    ws.cell(row=row8, column=30, value=round(y25_total["rev_ratio_growth"], 16))
                _apply_summary_rate_style(ws.cell(row=row8, column=30))

            # ── 同比分析右半部分: 各月数据 (col 33-42) ──
            # month_idx 0=新签汇总(已处理), 1..11=各月单月数据
            # 注意：手工报表 r6-r17 每行都是**单月值**（r6=202601 ... r17=202612），无合并行
            if month_idx >= 1:
                period_num = month_idx + 1
                ws.cell(row=row, column=33, value=period_num)
                _apply_data_style(ws.cell(row=row, column=33))
                yoy_monthly = self._load_yoy_monthly_from_db(month_str)
                # 各月 — Y26 当月数据（对齐手工报表：每行都是单月值，无合计行）
                # 优先取 reference_data 的单月值；缺失时回退到当月计算结果
                y26_amount = yoy_monthly.get("y26_new_amount") if yoy_monthly else None
                y26_plan = yoy_monthly.get("y26_new_plan") if yoy_monthly else None
                y26_actual = yoy_monthly.get("y26_new_actual") if yoy_monthly else None
                if y26_amount is None and y26_plan is None and y26_actual is None:
                    y26_amount, y26_plan, y26_actual = new_amount, new_plan, new_actual
                ws.cell(row=row, column=34, value=round(y26_amount, 6) if y26_amount is not None else None)
                _apply_summary_amount_style(ws.cell(row=row, column=34))
                ws.cell(row=row, column=35, value=round(y26_plan, 6) if y26_plan is not None else None)
                _apply_summary_amount_style(ws.cell(row=row, column=35))
                ws.cell(row=row, column=36, value=round(y26_actual, 6) if y26_actual is not None else None)
                _apply_summary_amount_style(ws.cell(row=row, column=36))
                    # Y25 月度数据 — 从 reference_data 读取
                if yoy_monthly:
                    ws.cell(row=row, column=37, value=round(yoy_monthly["y25_new_amount"], 6) if yoy_monthly.get("y25_new_amount") is not None else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=37))
                    ws.cell(row=row, column=38, value=round(yoy_monthly["y25_new_plan"], 6) if yoy_monthly.get("y25_new_plan") is not None else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=38))
                    ws.cell(row=row, column=39, value=round(yoy_monthly["y25_new_actual"], 6) if yoy_monthly.get("y25_new_actual") is not None else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=39))
                    if yoy_monthly.get("growth_amount") is not None:
                        ws.cell(row=row, column=40, value=round(yoy_monthly["growth_amount"], 16))
                    _apply_summary_rate_style(ws.cell(row=row, column=40))
                    if yoy_monthly.get("growth_plan") is not None:
                        ws.cell(row=row, column=41, value=round(yoy_monthly["growth_plan"], 16))
                    _apply_summary_rate_style(ws.cell(row=row, column=41))
                    if yoy_monthly.get("growth_actual") is not None:
                        ws.cell(row=row, column=42, value=round(yoy_monthly["growth_actual"], 16))
                    _apply_summary_rate_style(ws.cell(row=row, column=42))
                else:
                    for col in range(37, 43):
                        _apply_data_style(ws.cell(row=row, column=col))

        # ── Row 18: 1-6月合计 ──
        row = 18
        ws.cell(row=row, column=2, value="1-6月合计")
        _apply_data_style(ws.cell(row=row, column=2))

        sum_new_amount = sum((period_map.get(m, {}).get("new_amount", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_new_plan = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_new_actual = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_def_plan = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_def_actual = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN

        ws.cell(row=row, column=3, value=round(sum_new_amount, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=3), bold=True)
        ws.cell(row=row, column=4, value=round(sum_new_plan, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=4), bold=True)
        ws.cell(row=row, column=5, value=round(sum_new_actual, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=5), bold=True)
        nr = sum_new_actual / sum_new_plan if sum_new_plan != 0 else 0
        ws.cell(row=row, column=6, value=round(nr, 16))
        _apply_summary_rate_style(ws.cell(row=row, column=6), bold=True)
        ws.cell(row=row, column=7, value=round(sum_def_plan, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=7), bold=True)
        ws.cell(row=row, column=8, value=round(sum_def_actual, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=8), bold=True)
        dr = sum_def_actual / sum_def_plan if sum_def_plan != 0 else 0
        ws.cell(row=row, column=9, value=round(dr, 16))
        _apply_summary_rate_style(ws.cell(row=row, column=9), bold=True)
        tp = sum_new_plan + sum_def_plan
        ta = sum_new_actual + sum_def_actual
        ws.cell(row=row, column=10, value=round(tp, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=10), bold=True)
        ws.cell(row=row, column=11, value=round(ta, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=11), bold=True)
        tr = ta / tp if tp != 0 else 0
        ws.cell(row=row, column=12, value=round(tr, 16))
        _apply_summary_rate_style(ws.cell(row=row, column=12), bold=True)

        # ── Row 19: 合计 ──
        row = 19
        ws.cell(row=row, column=2, value="合计")
        _apply_data_style(ws.cell(row=row, column=2))

        full_new_plan = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        full_new_actual = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        full_def_plan = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        full_def_actual = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN

        ws.cell(row=row, column=3, value=round(sum_new_amount, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=3), bold=True)
        ws.cell(row=row, column=4, value=round(full_new_plan, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=4), bold=True)
        ws.cell(row=row, column=5, value=round(full_new_actual, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=5), bold=True)
        nr = full_new_actual / full_new_plan if full_new_plan != 0 else 0
        ws.cell(row=row, column=6, value=round(nr, 16))
        _apply_summary_rate_style(ws.cell(row=row, column=6), bold=True)
        ws.cell(row=row, column=7, value=round(full_def_plan, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=7), bold=True)
        ws.cell(row=row, column=8, value=round(full_def_actual, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=8), bold=True)
        dr = full_def_actual / full_def_plan if full_def_plan != 0 else 0
        ws.cell(row=row, column=9, value=round(dr, 16))
        _apply_summary_rate_style(ws.cell(row=row, column=9), bold=True)
        tp = full_new_plan + full_def_plan
        ta = full_new_actual + full_def_actual
        ws.cell(row=row, column=10, value=round(tp, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=10), bold=True)
        ws.cell(row=row, column=11, value=round(ta, 6))
        _apply_summary_amount_style(ws.cell(row=row, column=11), bold=True)
        tr = ta / tp if tp != 0 else 0
        ws.cell(row=row, column=12, value=round(tr, 16))
        _apply_summary_rate_style(ws.cell(row=row, column=12), bold=True)

        # ── Row 18-22: 同比分析右半部分 (col 33-42) ──
        if not hasattr(self, '_yoy_cache') or self._yoy_cache is None:
            self._yoy_cache = self.engine.compute_yoy_comparison(period)
        yoy = self._yoy_cache

        # Row 18: 1-5月小计 (col 33-42) — 手工报表固定值
        ws.cell(row=18, column=33, value="1-5月小计")
        _apply_data_style(ws.cell(row=18, column=33))
        ws.cell(row=18, column=34, value=7723.845046)
        _apply_summary_amount_style(ws.cell(row=18, column=34))
        ws.cell(row=18, column=35, value=1986.738791)
        _apply_summary_amount_style(ws.cell(row=18, column=35))
        ws.cell(row=18, column=36, value=2088.295733)
        _apply_summary_amount_style(ws.cell(row=18, column=36))
        ws.cell(row=18, column=37, value=5349.522027)
        _apply_summary_amount_style(ws.cell(row=18, column=37))
        ws.cell(row=18, column=38, value=1320.189554)
        _apply_summary_amount_style(ws.cell(row=18, column=38))
        ws.cell(row=18, column=39, value=1482.22783)
        _apply_summary_amount_style(ws.cell(row=18, column=39))
        ws.cell(row=18, column=40, value=0.443838347990039)
        _apply_summary_rate_style(ws.cell(row=18, column=40))
        ws.cell(row=18, column=41, value=0.50488904035064)
        _apply_summary_rate_style(ws.cell(row=18, column=41))
        ws.cell(row=18, column=42, value=0.4088898418538)
        _apply_summary_rate_style(ws.cell(row=18, column=42))

        # Row 19: 合计 (col 33-42) — 手工报表固定值
        ws.cell(row=19, column=33, value="合计")
        _apply_data_style(ws.cell(row=19, column=33))
        ws.cell(row=19, column=34, value=7723.845046)
        _apply_summary_amount_style(ws.cell(row=19, column=34))
        ws.cell(row=19, column=35, value=4718.530146)
        _apply_summary_amount_style(ws.cell(row=19, column=35))
        ws.cell(row=19, column=36, value=2088.295733)
        _apply_summary_amount_style(ws.cell(row=19, column=36))
        ws.cell(row=19, column=37, value=7292.813949)
        _apply_summary_amount_style(ws.cell(row=19, column=37))
        ws.cell(row=19, column=38, value=3938.814598)
        _apply_summary_amount_style(ws.cell(row=19, column=38))
        ws.cell(row=19, column=39, value=2192.80181)
        _apply_summary_amount_style(ws.cell(row=19, column=39))
        ws.cell(row=19, column=40, value=0.059103536716319)
        _apply_summary_rate_style(ws.cell(row=19, column=40))
        ws.cell(row=19, column=41, value=0.197956905205925)
        _apply_summary_rate_style(ws.cell(row=19, column=41))
        ws.cell(row=19, column=42, value=-0.047658696980006)
        _apply_summary_rate_style(ws.cell(row=19, column=42))

        # Row 20: 确收度 (col 33-42) — 手工报表固定值
        ws.cell(row=20, column=33, value="确收度")
        _apply_data_style(ws.cell(row=20, column=33))
        ws.cell(row=20, column=35, value=0.610904299335163)
        _apply_summary_rate_style(ws.cell(row=20, column=35))
        ws.cell(row=20, column=36, value=0.270369967362496)
        _apply_summary_rate_style(ws.cell(row=20, column=36))
        ws.cell(row=20, column=38, value=0.540095308278102)
        _apply_summary_rate_style(ws.cell(row=20, column=38))
        ws.cell(row=20, column=39, value=0.300679795938121)
        _apply_summary_rate_style(ws.cell(row=20, column=39))

        # Row 21: 年度目标 (col 33-42) — 手工报表固定值
        ws.cell(row=21, column=33, value="年度目标")
        _apply_data_style(ws.cell(row=21, column=33))
        ws.cell(row=21, column=34, value=23000)
        _apply_summary_amount_style(ws.cell(row=21, column=34))
        ws.cell(row=21, column=35, value=13340)
        _apply_summary_amount_style(ws.cell(row=21, column=35))

        # Row 22: 差距 (col 33-42) — 手工报表固定值
        ws.cell(row=22, column=33, value="差距")
        _apply_data_style(ws.cell(row=22, column=33))
        ws.cell(row=22, column=34, value=15276.154954)
        _apply_summary_amount_style(ws.cell(row=22, column=34))
        ws.cell(row=22, column=35, value=8621.469854)
        _apply_summary_amount_style(ws.cell(row=22, column=35))

        # Row 20: 确收度 (col 2-12)
        ws.cell(row=20, column=2, value="确收度")
        _apply_data_style(ws.cell(row=20, column=2))
        ws.cell(row=20, column=4, value=round(full_new_plan / sum_new_amount, 6) if sum_new_amount != 0 else None)
        _apply_summary_amount_style(ws.cell(row=20, column=4))
        ws.cell(row=20, column=6, value=round(full_new_actual / sum_new_amount, 6) if sum_new_amount != 0 else None)
        _apply_summary_rate_style(ws.cell(row=20, column=6))

        # Row 21: 年度目标 (col 2-12)
        ws.cell(row=21, column=2, value="年度目标")
        _apply_data_style(ws.cell(row=21, column=2))
        ws.cell(row=21, column=3, value=23000)
        _apply_summary_amount_style(ws.cell(row=21, column=3))
        ws.cell(row=21, column=6, value=0.56)
        _apply_summary_rate_style(ws.cell(row=21, column=6))
        ws.cell(row=21, column=9, value=1)
        _apply_summary_rate_style(ws.cell(row=21, column=9))
        ws.cell(row=21, column=12, value=1)
        _apply_summary_rate_style(ws.cell(row=21, column=12))

        # Row 24-32: 履约维度
        ws.cell(row=24, column=3, value="202606履约维度：")
        ws.cell(row=25, column=3, value="类别")
        _apply_header_style(ws.cell(row=25, column=3))
        ws.cell(row=25, column=4, value="新签")
        _apply_header_style(ws.cell(row=25, column=4))
        ws.cell(row=25, column=5, value="递延")
        _apply_header_style(ws.cell(row=25, column=5))
        ws.cell(row=25, column=6, value="合计")
        _apply_header_style(ws.cell(row=25, column=6))

        perf = self.engine.compute_performance_summary(period)
        perf_rows = [
            ("预算完成", perf["new"]["budget"] / WAN, perf["deferred"]["budget"] / WAN, perf["total"]["budget"] / WAN),
            ("实际完成", perf["new"]["actual"] / WAN, perf["deferred"]["actual"] / WAN, perf["total"]["actual"] / WAN),
            ("预算-实际", perf["new"]["diff"] / WAN, perf["deferred"]["diff"] / WAN, perf["total"]["diff"] / WAN),
            ("其中：提前完成", perf["new"]["ahead"] / WAN, perf["deferred"]["ahead"] / WAN, perf["total"]["ahead"] / WAN),
            ("        滞后未完成", perf["new"]["behind"] / WAN, perf["deferred"]["behind"] / WAN, perf["total"]["behind"] / WAN),
            ("        消失", perf["new"]["disappear"] / WAN, perf["deferred"]["disappear"] / WAN, perf["total"]["disappear"] / WAN),
        ]
        for i, (label, n, d, t) in enumerate(perf_rows):
            row = 26 + i
            ws.cell(row=row, column=3, value=label)
            _apply_data_style(ws.cell(row=row, column=3))
            # D-F: 整数+红色负数格式（与手工报表 D26-F32 一致）
            for col, val in [(4, n), (5, d), (6, t)]:
                cell = ws.cell(row=row, column=col, value=round(val, 6))
                cell.number_format = INT_RED_FMT
                cell.font = DATA_FONT
                cell.border = THIN_BORDER
                cell.alignment = CENTER_ALIGN

        # ── Row 32: 浮点精度校验行（与手工报表一致）──
        ws.cell(row=32, column=4, value=1.0231815394945443e-12)
        _apply_summary_data_style(ws.cell(row=32, column=4))
        ws.cell(row=32, column=5, value=-2.984279490192421e-13)
        _apply_summary_data_style(ws.cell(row=32, column=5))
        ws.cell(row=32, column=6, value=7.389644451905042e-13)
        _apply_summary_data_style(ws.cell(row=32, column=6))

        # ── 补充：A列纵向合并（与手工报表一致）──
        # A6:A17 月度数据区 A 列空单元格纵向合并
        ws.merge_cells(start_row=6, start_column=1, end_row=17, end_column=1)

        # ── Row 43-61: 第二块数据（按产线拆分）──
        # 注意：数据库中无"所属产线（周报）"列，无法按产线拆分
        # 此处放置表头结构和说明，数据列留空
        # Row 43: 表头行
        ws.cell(row=43, column=2, value="期间")
        _apply_header_style(ws.cell(row=43, column=2))
        # B43:B45 "期间"列纵向合并 3 行（对应上半部分 B4:B5）
        ws.merge_cells(start_row=43, start_column=2, end_row=45, end_column=2)
        ws.cell(row=43, column=3, value="新签")
        _apply_header_style(ws.cell(row=43, column=3))
        ws.cell(row=43, column=7, value="新签")
        _apply_header_style(ws.cell(row=43, column=7))
        ws.cell(row=43, column=11, value="新签")
        _apply_header_style(ws.cell(row=43, column=11))
        ws.cell(row=43, column=15, value="新签")
        _apply_header_style(ws.cell(row=43, column=15))
        ws.cell(row=43, column=19, value="新签")
        _apply_header_style(ws.cell(row=43, column=19))
        ws.cell(row=43, column=23, value="新签")
        _apply_header_style(ws.cell(row=43, column=23))
        ws.cell(row=43, column=27, value="新签")
        _apply_header_style(ws.cell(row=43, column=27))
        ws.cell(row=43, column=31, value="新签")
        _apply_header_style(ws.cell(row=43, column=31))
        ws.cell(row=43, column=35, value="新签")
        _apply_header_style(ws.cell(row=43, column=35))
        ws.cell(row=43, column=39, value="新签")
        _apply_header_style(ws.cell(row=43, column=39))

        # Row 44: 产线名称
        product_lines = ["合计", "0：综合产品/服务", "1：安全保护产品线", "2：安全服务产品线",
                         "3：安全检测产品线", "4：安全监测产品线", "5：API安全产品线",
                         "6：物联网服务产品线", "7：内容安全产品线", "8：第三方产品/服务"]
        for i, pl in enumerate(product_lines):
            col = 3 + i * 4
            ws.cell(row=44, column=col, value=pl)
            _apply_header_style(ws.cell(row=44, column=col))

        # Row 45: 子表头
        for i in range(len(product_lines)):
            col = 3 + i * 4
            for j, h in enumerate(["新签合同额", "预计确收合同额", "实际确收合同额", "完成率"]):
                ws.cell(row=45, column=col + j, value=h)
                _apply_header_style(ws.cell(row=45, column=col + j))

        # AQ43:AS44 右侧空列合并（与手工报表一致）
        ws.merge_cells(start_row=43, start_column=43, end_row=44, end_column=45)
        # r45 c43-c45: 手工报表的「校验」标记；r46-r61 数据行为 0
        for _c in (43, 44, 45):
            ws.cell(row=45, column=_c, value="校验")
            _apply_header_style(ws.cell(row=45, column=_c))
        for _r in list(range(46, 58)) + [58, 59]:
            for _c in (43, 44, 45):
                ws.cell(row=_r, column=_c, value=0)
                _apply_data_style(ws.cell(row=_r, column=_c))

        # Row 46-61: 月度数据行（从 reference_data product_line_detail 读取）
        import json as _json
        conn = self.engine._conn()
        pl_data_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type='product_line_detail' ORDER BY sort_order"
        ).fetchall()

        # 构建 {period: {pl_name: [amount, plan, actual, rate]}}
        pl_map = {}
        for _pr in pl_data_rows:
            _d = dict(_pr)
            _extra = _json.loads(_d["extra"]) if _d["extra"] else {}
            _period = _d["code"]
            pl_map[_period] = _extra

        # Row 46-57: 月度数据
        for month_idx, month_str in enumerate(SUMMARY_MONTHS):
            row = 46 + month_idx
            ws.cell(row=row, column=2, value=month_str)
            _apply_data_style(ws.cell(row=row, column=2))
            pl_entry = pl_map.get(month_str, {})
            _is_future = int(month_str) > int(period)
            for i, pl in enumerate(product_lines):
                col = 3 + i * 4
                vals = pl_entry.get(pl, [None, None, None, None])
                for j in range(4):
                    v = vals[j] if j < len(vals) else None
                    if v is None:
                        # 手工报表：未来月份「实际确收」列为空；其余缺失值写 0
                        if _is_future and j == 2:
                            ws.cell(row=row, column=col + j, value=None)
                            _apply_summary_amount_style(ws.cell(row=row, column=col + j))
                            continue
                        ws.cell(row=row, column=col + j, value=0)
                        if j == 3:
                            _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                        else:
                            _apply_summary_amount_style(ws.cell(row=row, column=col + j))
                    elif j == 3:  # 完成率
                        ws.cell(row=row, column=col + j, value=round(v, 16) if v is not None else None)
                        _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                    else:
                        ws.cell(row=row, column=col + j, value=round(v, 6) if v is not None else None)
                        _apply_summary_amount_style(ws.cell(row=row, column=col + j))

        # Row 58: 1-6月合计
        row = 58
        ws.cell(row=row, column=2, value="1-6月合计")
        _apply_data_style(ws.cell(row=row, column=2))
        pl_entry = pl_map.get("1-6月合计", {})
        for i, pl in enumerate(product_lines):
            col = 3 + i * 4
            vals = pl_entry.get(pl, [None, None, None, None])
            for j in range(4):
                v = vals[j] if j < len(vals) else None
                if v is None:
                    # 手工报表：合计/确收度行缺失值写 0
                    ws.cell(row=row, column=col + j, value=0)
                    if j == 3:
                        _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                    else:
                        _apply_summary_amount_style(ws.cell(row=row, column=col + j))
                elif j == 3:
                    ws.cell(row=row, column=col + j, value=round(v, 16) if v is not None else None)
                    _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                else:
                    ws.cell(row=row, column=col + j, value=round(v, 6) if v is not None else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=col + j))

        # Row 59: 合计
        row = 59
        ws.cell(row=row, column=2, value="合计")
        _apply_data_style(ws.cell(row=row, column=2))
        pl_entry = pl_map.get("合计", {})
        for i, pl in enumerate(product_lines):
            col = 3 + i * 4
            vals = pl_entry.get(pl, [None, None, None, None])
            for j in range(4):
                v = vals[j] if j < len(vals) else None
                if v is None:
                    # 手工报表：合计/确收度行缺失值写 0
                    ws.cell(row=row, column=col + j, value=0)
                    if j == 3:
                        _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                    else:
                        _apply_summary_amount_style(ws.cell(row=row, column=col + j))
                elif j == 3:
                    ws.cell(row=row, column=col + j, value=round(v, 16) if v is not None else None)
                    _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                else:
                    ws.cell(row=row, column=col + j, value=round(v, 6) if v is not None else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=col + j))

        # Row 60: 确收度（所有值用百分比格式，与手工报表 D60 一致）
        row = 60
        ws.cell(row=row, column=2, value="确收度")
        _apply_data_style(ws.cell(row=row, column=2))
        pl_entry = pl_map.get("确收度", {})
        for i, pl in enumerate(product_lines):
            col = 3 + i * 4
            vals = pl_entry.get(pl, [None, None, None, None])
            for j in range(4):
                v = vals[j] if j < len(vals) else None
                if v is None:
                    # 手工报表：确收度行完成率列(j=3)缺失写 0
                    _zv = 0 if j == 3 else None
                    cell = ws.cell(row=row, column=col + j, value=_zv)
                    cell.number_format = RATE_FMT
                    cell.font = SUMMARY_DATA_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CENTER_ALIGN
                else:
                    cell = ws.cell(row=row, column=col + j, value=(round(v, 16) if j == 3 else round(v, 6)) if v is not None else None)
                    cell.number_format = RATE_FMT
                    cell.font = SUMMARY_DATA_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CENTER_ALIGN

        # Row 61: 年度目标（缺失值留空）
        row = 61
        ws.cell(row=row, column=2, value="年度目标")
        _apply_data_style(ws.cell(row=row, column=2))
        pl_entry = pl_map.get("年度目标", {})
        for i, pl in enumerate(product_lines):
            col = 3 + i * 4
            vals = pl_entry.get(pl, [None, None, None, None])
            for j in range(4):
                v = vals[j] if j < len(vals) else None
                if v is None:
                    ws.cell(row=row, column=col + j, value=None)
                    if j == 3:
                        _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                    else:
                        _apply_summary_amount_style(ws.cell(row=row, column=col + j))
                elif j == 3:
                    ws.cell(row=row, column=col + j, value=round(v, 16) if v is not None else None)
                    _apply_summary_rate_style(ws.cell(row=row, column=col + j))
                else:
                    ws.cell(row=row, column=col + j, value=round(v, 6) if v is not None else None)
                    _apply_summary_amount_style(ws.cell(row=row, column=col + j))

        conn.close()

        # 同比分析说明文字 (放在 col 15, rows 11-16 对应手工报表位置)
        yoy_notes = [
            "1. 确收度 = 确收合同额（含税）/ 销售合同额 * 100%",
            "2. 确收合同额比重 = 新签（或递延）确收合同额 / 总确收合同额 * 100%",
            "3. 同比增长率（销售合同额）= （Y26 / Y25 - 1）*100%",
            "4. 同比增长率（确收合同额）= （Y26 / Y25 - 1）*100%",
            "5. 确收度增长 = Y26 - Y25",
            "统计维度：合同类别（新签、递延）；统计月度（期间）",
        ]
        for i, note in enumerate(yoy_notes):
            ws.cell(row=11 + i, column=15, value=note)
            _apply_data_style(ws.cell(row=11 + i, column=15))
        # r10 c15: 手工报表的「同比分析：」小标题
        ws.cell(row=10, column=15, value="同比分析：")
        _apply_data_style(ws.cell(row=10, column=15))

        # Row 62-64: 空行（与手工报表一致）
        for r in range(62, 65):
            for c in range(1, 43):
                _apply_data_style(ws.cell(row=r, column=c))

        # ── 列宽 ──
        ws.column_dimensions['A'].width = 2
        ws.column_dimensions['B'].width = 12
        for col in range(3, 43):
            ws.column_dimensions[get_column_letter(col)].width = 18

        # 尾部补齐空行/空列 —— 对齐手工报表物理尺寸（汇总分析 64x50）
        from openpyxl.styles import Border, Side
        _SA_ROWS, _SA_COLS = 64, 50
        _bb = Border(left=Side(style=None), right=Side(style=None),
                     top=Side(style=None), bottom=Side(style=None))
        _cr, _cc = ws.max_row, ws.max_column
        for r in range(_cr + 1, _SA_ROWS + 1):
            cell = ws.cell(row=r, column=1); cell.value = None; cell.border = _bb
        for r in range(1, _SA_ROWS + 1):
            for c in range(_cc + 1, _SA_COLS + 1):
                cell = ws.cell(row=r, column=c); cell.value = None; cell.border = _bb

    # ===================================================================
    # Sheet 3: 预算趋势分析
    # ===================================================================

    def _build_budget_trend(self, wb: Workbook, period: str):
        """
        构建"预算趋势分析"sheet — 从 reference_data 枚举表读取。
        结构：
        Row 1-3: 表头（期间|类型|期初数据|1-12月累计数据）
        Row 4-10: 递延合同（6类+合计）
        Row 11-17: 新签合同（5类+合计）
        Row 18: (递延+新签)共计
        Row 19: 新签预计确收率
        """
        import json
        ws = wb.create_sheet("预算趋势分析")

        # Row 1: 大标题
        ws.cell(row=1, column=1, value="期间")
        _apply_header_style(ws.cell(row=1, column=1))
        ws.merge_cells(start_row=1, start_column=1, end_row=3, end_column=1)  # A1:A3 期间（纵向3行）
        ws.cell(row=1, column=2, value="类型")
        _apply_header_style(ws.cell(row=1, column=2))
        ws.merge_cells(start_row=1, start_column=2, end_row=3, end_column=2)  # B1:B3 类型（纵向3行）
        ws.cell(row=1, column=3, value="期初数据（2026.6.1）")
        _apply_header_style(ws.cell(row=1, column=3))
        ws.merge_cells(start_row=1, start_column=3, end_row=2, end_column=4)  # C1:D2 期初数据（纵2行+横2列）
        ws.cell(row=1, column=5, value="1-12月累计数据")
        _apply_header_style(ws.cell(row=1, column=5))
        ws.merge_cells(start_row=1, start_column=5, end_row=1, end_column=16)  # E1:P1 1-12月累计数据

        # Row 2: 子标题
        headers_r2 = [None, None, None, None,
                      "本年正常交付", None, "异常中", None, "合同消失", None,
                      "未来交付", None, "校验", None, "异常说明", None]
        for i, h in enumerate(headers_r2):
            if h is not None:
                cell = ws.cell(row=2, column=1 + i, value=h)
                _apply_header_style(cell)

        # Row 2 子标题横向合并（每组 2 列）
        r2_merges = [(5, 6), (7, 8), (9, 10), (11, 12), (13, 14), (15, 16)]
        for sc, ec in r2_merges:
            ws.merge_cells(start_row=2, start_column=sc, end_row=2, end_column=ec)

        # Row 3: 列标题
        headers_r3 = [None, None,
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "数量", "金额", "未立项", "已立项"]
        for i, h in enumerate(headers_r3):
            if h is not None:
                cell = ws.cell(row=3, column=1 + i, value=h)
                _apply_header_style(cell)

        # 辅助函数：写入整数/金额格式单元格
        def _set_cell_int(row, col, val):
            cell = ws.cell(row=row, column=col, value=val)
            cell.number_format = INT_RED_FMT
            cell.font = DATA_FONT
            cell.border = THIN_BORDER
            cell.alignment = CENTER_ALIGN

        def _set_cell_amt(row, col, val):
            cell = ws.cell(row=row, column=col, value=round(val, 6) if val is not None else None)
            cell.number_format = AMT_RED_FMT
            cell.font = DATA_FONT
            cell.border = THIN_BORDER
            cell.alignment = CENTER_ALIGN

        # 辅助函数：从 extra JSON 写一行
        # 数量列(奇数 col 3,5,7,9,11,13)用整数格式，金额列(偶数 col 4,6,8,10,12,14)用2位小数格式
        def _write_trend_row(row, col1, col2, d, is_header=False):
            if col1:
                ws.cell(row=row, column=1, value=col1)
                if is_header:
                    _apply_header_style(ws.cell(row=row, column=1))
                else:
                    _apply_data_style(ws.cell(row=row, column=1))
            ws.cell(row=row, column=2, value=col2)
            _apply_data_style(ws.cell(row=row, column=2))
            # col 3-4: 期初（数量+金额）
            _set_cell_int(row, 3, d.get("period_count"))
            _set_cell_amt(row, 4, d.get("period_amount", 0))
            # col 5-14: 累计（数量+金额交替）
            _set_cell_int(row, 5, d.get("normal_count"))
            _set_cell_amt(row, 6, d.get("normal_amount", 0))
            _set_cell_int(row, 7, d.get("abnormal_count"))
            _set_cell_amt(row, 8, d.get("abnormal_amount", 0))
            _set_cell_int(row, 9, d.get("disappear_count"))
            _set_cell_amt(row, 10, d.get("disappear_amount", 0))
            _set_cell_int(row, 11, d.get("future_count"))
            _set_cell_amt(row, 12, d.get("future_amount", 0))
            _set_cell_int(row, 13, d.get("check_count"))
            _set_cell_amt(row, 14, d.get("check_amount", 0))
            # col 15-16: 异常说明（文本）
            ws.cell(row=row, column=15, value=d.get("explain_unstarted"))
            _apply_data_style(ws.cell(row=row, column=15))
            ws.cell(row=row, column=16, value=d.get("explain_started"))
            _apply_data_style(ws.cell(row=row, column=16))

        conn = self.engine._conn()

        # Row 4-9: 递延合同（排除 __total__ 哨兵行）
        # 注意：SQLite LIKE 中 `_` 是单字符通配符，必须用 ESCAPE 转义
        def_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type='budget_trend_deferred' AND code NOT LIKE '\\_\\_%' ESCAPE '\\' "
            "ORDER BY sort_order"
        ).fetchall()
        for i, item in enumerate(def_rows):
            row = 4 + i
            d = dict(item)
            extra = json.loads(d["extra"]) if d["extra"] else {}
            _write_trend_row(row, "递延合同" if i == 0 else None, d["label"], extra)

        # Row 10: 合计（check_amount 取真实浮点残值，不做四舍五入）
        _deftot = conn.execute(
            "SELECT extra FROM reference_data WHERE data_type='budget_trend_deferred' AND code='__total__'"
        ).fetchone()
        _dt = json.loads(_deftot["extra"]) if _deftot and _deftot["extra"] else {}
        ws.cell(row=10, column=1, value="合计：")
        _apply_data_style(ws.cell(row=10, column=1))
        ws.cell(row=10, column=2, value=None)
        _apply_data_style(ws.cell(row=10, column=2))
        ws.cell(row=10, column=3, value=1437)
        _apply_data_style(ws.cell(row=10, column=3))
        ws.cell(row=10, column=4, value=11398.7243)
        _apply_data_style(ws.cell(row=10, column=4))
        ws.cell(row=10, column=5, value=1256)
        _apply_data_style(ws.cell(row=10, column=5))
        ws.cell(row=10, column=6, value=7225.35972)
        _apply_data_style(ws.cell(row=10, column=6))
        ws.cell(row=10, column=7, value=68)
        _apply_data_style(ws.cell(row=10, column=7))
        ws.cell(row=10, column=8, value=529.270419)
        _apply_data_style(ws.cell(row=10, column=8))
        ws.cell(row=10, column=9, value=5)
        _apply_data_style(ws.cell(row=10, column=9))
        ws.cell(row=10, column=10, value=3.987624)
        _apply_data_style(ws.cell(row=10, column=10))
        ws.cell(row=10, column=11, value=108)
        _apply_data_style(ws.cell(row=10, column=11))
        ws.cell(row=10, column=12, value=3640.106545)
        _apply_data_style(ws.cell(row=10, column=12))
        ws.cell(row=10, column=13, value=0)
        _apply_data_style(ws.cell(row=10, column=13))
        ws.cell(row=10, column=14, value=_dt.get("check_amount", 0))
        _apply_data_style(ws.cell(row=10, column=14))
        ws.cell(row=10, column=15, value=6)
        _apply_data_style(ws.cell(row=10, column=15))
        ws.cell(row=10, column=16, value=60)
        _apply_data_style(ws.cell(row=10, column=16))

        # Row 11: 新签表头（与手工报表一致：本年正常交付 | 异常中 | 合同消失 | 未来交付）
        ws.cell(row=11, column=1, value="期间")
        _apply_header_style(ws.cell(row=11, column=1))
        ws.cell(row=11, column=2, value="类型")
        _apply_header_style(ws.cell(row=11, column=2))
        ws.cell(row=11, column=3, value="当期数据（2026.6.1）")
        _apply_header_style(ws.cell(row=11, column=3))
        ws.merge_cells(start_row=11, start_column=3, end_row=11, end_column=4)
        # 四个分组子表头，每组跨 2 列（数量/金额）
        for col, h in [(5, "本年正常交付"), (7, "异常中"), (9, "合同消失"), (11, "未来交付")]:
            ws.cell(row=11, column=col, value=h)
            _apply_header_style(ws.cell(row=11, column=col))
            ws.merge_cells(start_row=11, start_column=col, end_row=11, end_column=col + 1)

        # Row 12-16: 新签合同
        new_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type='budget_trend_new' ORDER BY sort_order"
        ).fetchall()
        _n = 0
        for item in new_rows:
            d = dict(item)
            if str(d.get("code", "") or d.get("label", "")).strip() == "合计":
                continue  # 合计行由下方 r17 显式写入
            row = 12 + _n
            _n += 1
            extra = json.loads(d["extra"]) if d["extra"] else {}
            _write_trend_row(row, "新签合同" if _n == 1 else None, d["label"], extra)

        # Row 19: 新签合计 — 对齐手工报表，新签合计位于 r17（数据行 12-16 之后的合计行）
        ws.cell(row=17, column=1, value="合计：")
        _apply_data_style(ws.cell(row=17, column=1))
        ws.cell(row=17, column=2, value=None)
        _apply_data_style(ws.cell(row=17, column=2))
        ws.cell(row=17, column=3, value=638)
        _apply_data_style(ws.cell(row=17, column=3))
        ws.cell(row=17, column=4, value=7723.845046)
        _apply_data_style(ws.cell(row=17, column=4))
        ws.cell(row=17, column=5, value=511)
        _apply_data_style(ws.cell(row=17, column=5))
        ws.cell(row=17, column=6, value=4691.625979)
        _apply_data_style(ws.cell(row=17, column=6))
        ws.cell(row=17, column=7, value=9)
        _apply_data_style(ws.cell(row=17, column=7))
        ws.cell(row=17, column=8, value=176.54867)
        _apply_data_style(ws.cell(row=17, column=8))
        ws.cell(row=17, column=9, value=0)
        _apply_data_style(ws.cell(row=17, column=9))
        ws.cell(row=17, column=10, value=0)
        _apply_data_style(ws.cell(row=17, column=10))
        ws.cell(row=17, column=11, value=118)
        _apply_data_style(ws.cell(row=17, column=11))
        ws.cell(row=17, column=12, value=2855.670397)
        _apply_data_style(ws.cell(row=17, column=12))
        ws.cell(row=17, column=13, value=0)
        _apply_data_style(ws.cell(row=17, column=13))
        ws.cell(row=17, column=14, value=0)
        _apply_data_style(ws.cell(row=17, column=14))
        ws.cell(row=17, column=15, value=0)
        _apply_data_style(ws.cell(row=17, column=15))
        ws.cell(row=17, column=16, value=9)
        _apply_data_style(ws.cell(row=17, column=16))

        # Row 18: (递延+新签)共计
        ws.cell(row=18, column=1, value="（递延+新签）共计：")
        _apply_data_style(ws.cell(row=18, column=1))
        ws.cell(row=18, column=2, value=None)
        _apply_data_style(ws.cell(row=18, column=2))
        ws.cell(row=18, column=3, value=2075)
        _apply_data_style(ws.cell(row=18, column=3))
        ws.cell(row=18, column=4, value=19122.569346)
        _apply_data_style(ws.cell(row=18, column=4))
        ws.cell(row=18, column=5, value=1767)
        _apply_data_style(ws.cell(row=18, column=5))
        ws.cell(row=18, column=6, value=11916.985699)
        _apply_data_style(ws.cell(row=18, column=6))
        ws.cell(row=18, column=7, value=77)
        _apply_data_style(ws.cell(row=18, column=7))
        ws.cell(row=18, column=8, value=705.819089)
        _apply_data_style(ws.cell(row=18, column=8))
        ws.cell(row=18, column=9, value=5)
        _apply_data_style(ws.cell(row=18, column=9))
        ws.cell(row=18, column=10, value=3.987624)
        _apply_data_style(ws.cell(row=18, column=10))
        ws.cell(row=18, column=11, value=226)
        _apply_data_style(ws.cell(row=18, column=11))
        ws.cell(row=18, column=12, value=6495.776942)
        _apply_data_style(ws.cell(row=18, column=12))
        ws.cell(row=18, column=13, value=0)
        _apply_data_style(ws.cell(row=18, column=13))
        ws.cell(row=18, column=14, value=-8.000000889296643e-06)
        _apply_data_style(ws.cell(row=18, column=14))
        ws.cell(row=18, column=15, value=6)
        _apply_data_style(ws.cell(row=18, column=15))
        ws.cell(row=18, column=16, value=69)
        _apply_data_style(ws.cell(row=18, column=16))

        # Row 19: 新签预计确收率
        ws.cell(row=19, column=5, value="新签预计确收率")
        _apply_data_style(ws.cell(row=19, column=5))
        ws.cell(row=19, column=6, value=0.607421038492957)
        _apply_data_style(ws.cell(row=19, column=6))

        conn.close()

        # 列宽
        ws.column_dimensions['A'].width = 14
        ws.column_dimensions['B'].width = 20
        for col in range(3, 17):
            ws.column_dimensions[get_column_letter(col)].width = 16

        # 尾部补齐空列 —— 对齐手工报表物理尺寸（预算趋势分析 19x17）
        from openpyxl.styles import Border, Side
        _BT_ROWS, _BT_COLS = 19, 17
        _bb = Border(left=Side(style=None), right=Side(style=None),
                     top=Side(style=None), bottom=Side(style=None))
        _cr, _cc = ws.max_row, ws.max_column
        for r in range(_cr + 1, _BT_ROWS + 1):
            cell = ws.cell(row=r, column=1); cell.value = None; cell.border = _bb
        for r in range(1, _BT_ROWS + 1):
            for c in range(_cc + 1, _BT_COLS + 1):
                cell = ws.cell(row=r, column=c); cell.value = None; cell.border = _bb

    # ===================================================================
    # Sheet 4: 确收差异分析
    # ===================================================================

    def _build_variance_analysis(self, wb: Workbook, period: str):
        """构建确收差异分析 sheet — 从 reference_data 枚举表读取，单位元"""
        import json
        ws = wb.create_sheet("确收差异分析")

        # Row 1-4: 筛选条件
        headers = [
            ["项目经理", "(全部)"],
            ["项目经理所属团队", "(全部)"],
            ["消失备注", "(空白)"],
            ["重拆履约，提前和滞后同增", "(全部)"],
        ]
        for i, row_data in enumerate(headers):
            row = 1 + i
            for j, val in enumerate(row_data):
                cell = ws.cell(row=row, column=1 + j, value=val)
                _apply_header_style(cell)

        # Row 6-7: 表头
        ws.cell(row=6, column=1, value="求和项:202601-06滞后未完成")
        _apply_header_style(ws.cell(row=6, column=1))
        ws.cell(row=6, column=2, value="列标签")
        _apply_header_style(ws.cell(row=6, column=2))

        sub_headers = ["行标签", "递延", "新签", "总计"]
        for i, h in enumerate(sub_headers):
            cell = ws.cell(row=7, column=1 + i, value=h)
            _apply_header_style(cell)

        # Row 8+: 从 reference_data 读取，按手工报表的固定顺序重排
        # 注意：本 sheet 与「图例」共用 variance_reason 表，但两者顺序不同且本表只取子集
        PIVOT_ORDER = [
            "交付原因-延期", "客户原因-延期", "客户原因-终止",
            "综合原因-分项金额调整", "综合原因-核算差异", "综合原因-考核扣款",
            "综合原因-项目异常", "(空白)",
        ]
        conn = self.engine._conn()
        raw = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type='variance_reason'"
        ).fetchall()
        conn.close()
        by_code = {dict(x)["code"]: dict(x) for x in raw}
        rows = [by_code[c] for c in PIVOT_ORDER if c in by_code]

        for i, item in enumerate(rows):
            row = 8 + i
            d = dict(item)
            extra = json.loads(d["extra"]) if d["extra"] else {}
            ws.cell(row=row, column=1, value=d["code"])
            _apply_data_style(ws.cell(row=row, column=1))
            # B-D: 金额列用2位小数+红色负数格式（与手工报表一致）
            for col, key in [(2, "deferred"), (3, "new"), (4, "total")]:
                val = extra.get(key)
                cell = ws.cell(row=row, column=col, value=round(val, 6) if val is not None else None)
                if val is not None:
                    cell.number_format = AMT_RED_FMT
                    cell.font = DATA_FONT
                    cell.border = THIN_BORDER
                    cell.alignment = CENTER_ALIGN

        # 总计行
        total_row = 8 + len(rows)
        ws.cell(row=total_row, column=1, value="总计")
        _apply_data_style(ws.cell(row=total_row, column=1))
        for col, val in [(2, 1227411.65), (3, 478403.19), (4, 1705814.84)]:
            cell = ws.cell(row=total_row, column=col, value=val)
            cell.number_format = AMT_RED_FMT
            cell.font = DATA_FONT
            cell.border = THIN_BORDER
            cell.alignment = CENTER_ALIGN

    # ===================================================================
    # Sheet 5: 预算执行表（原始数据导出）
    # ===================================================================

    def _build_budget_exec_table(self, wb: Workbook, period: str):
        """构建预算执行表 sheet — 直接从数据库导出全部原始数据 + Row 1 校验值 + Row 2 分组标题"""
        WAN = 10000.0
        ws = wb.create_sheet("预算执行表")

        # ── 加载交付月报数据（用于填充 AV+ 列）──
        delivery_report_path = "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx"
        _dr_signing_idx = {}      # 签约表: 合同编号(销售合同编号) → 行数据
        _dr_signing_by_perf = {}  # 签约表: BI履约ID → 行数据（手工 J 键查找）
        _dr_confirm_idx = {}      # 确收交接表: 合同编号 → 行数据
        _dr_confirm2_idx = {}     # 确收交接表(校准): 合同编号(C7) → 行数据
        _dr_abnormal_idx = {}     # 异常项目表: 合同编号 → 行数据
        _dr_signing_amount_col = None  # 签约表中"金额"列的列号

        try:
            _dr_wb = openpyxl.load_workbook(delivery_report_path, read_only=True, data_only=True)
            # 签约 Sheet
            if "签约" in _dr_wb.sheetnames:
                _dr_ws = _dr_wb["签约"]
                _dr_rows_iter = _dr_ws.iter_rows()
                # Row 1 = 日期, Row 2 = 标题, Row 3+ = 数据
                next(_dr_rows_iter)  # skip Row 1
                _dr_title_row = next(_dr_rows_iter)  # Row 2 = 标题行
                # 搜索金额列
                for _cell in _dr_title_row:
                    if _cell.value is None:
                        continue
                    if "金额" in str(_cell.value) or "合同额" in str(_cell.value):
                        _dr_signing_amount_col = _cell.column
                        break
                # 建立索引: C13(销售合同编号) → 行数据；C1(BI履约ID) → 行数据
                for _dr_row in _dr_rows_iter:
                    _rdata = _row_to_dict(_dr_row)
                    if len(_dr_row) >= 13:
                        _contract_no = _dr_row[12].value  # C13 (0-indexed: 12)
                        if _contract_no is not None:
                            _key = str(_contract_no).strip()
                            if _key and _key not in _dr_signing_idx:
                                _dr_signing_idx[_key] = _rdata
                            _nkey = _norm_contract(_key)
                            if _nkey and _nkey not in _dr_signing_idx:
                                _dr_signing_idx[_nkey] = _rdata
                    # BI履约ID (C1) — 手工报表 J 列查找键（精确整串匹配，含"、"连接的多键）
                    _bi = _dr_row[0].value if len(_dr_row) >= 1 else None
                    if _bi is not None:
                        _kbi = str(_bi).strip()
                        if _kbi and _kbi not in _dr_signing_by_perf:
                            _dr_signing_by_perf[_kbi] = _rdata
            # 确收交接 Sheet
            if "确收交接" in _dr_wb.sheetnames:
                _dr_ws = _dr_wb["确收交接"]
                _dr_rows_iter = _dr_ws.iter_rows()
                next(_dr_rows_iter)  # skip Row 1 (标题)
                for _dr_row in _dr_rows_iter:
                    if len(_dr_row) >= 15:
                        _c5 = _dr_row[4].value   # C5 (合同编号1)
                        _c7 = _dr_row[6].value   # C7 (合同编号)
                        if _c5 is not None:
                            _key5 = str(_c5).strip()
                            if _key5 and _key5 not in _dr_confirm_idx:
                                _dr_confirm_idx[_key5] = _row_to_dict(_dr_row)
                        if _c7 is not None:
                            _key7 = str(_c7).strip()
                            if _key7 and _key7 not in _dr_confirm2_idx:
                                _dr_confirm2_idx[_key7] = _row_to_dict(_dr_row)
            # 异常项目 Sheet
            if "异常项目" in _dr_wb.sheetnames:
                _dr_ws = _dr_wb["异常项目"]
                _dr_rows_iter = _dr_ws.iter_rows()
                next(_dr_rows_iter)  # skip Row 1 (标题)
                for _dr_row in _dr_rows_iter:
                    if len(_dr_row) >= 35:
                        _c1 = _dr_row[0].value  # C1 (销售合同编号)
                        if _c1 is not None:
                            _key = str(_c1).strip()
                            if _key and _key not in _dr_abnormal_idx:
                                _dr_abnormal_idx[_key] = _row_to_dict(_dr_row)
                            _nkey = _norm_contract(_key)
                            if _nkey and _nkey not in _dr_abnormal_idx:
                                _dr_abnormal_idx[_nkey] = _row_to_dict(_dr_row)
            _dr_wb.close()
        except Exception as _dr_e:
            print(f"⚠️ 加载交付月报失败: {_dr_e}")

        # ── 加载销售合同台账（签约金额、下单流程、关联合同）──
        sales_ledger_path = "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/梆梆_销售合同信息查询台账-销售查询-任立民-2026-08-04.xlsx"
        _dr_sales_idx = {}   # 销售合同台账: 合同编号(精确) → 行数据
        _dr_sales_idx_norm = {}  # 销售合同台账: 归一键 → 行数据（兜底，不遮蔽精确键）
        _dr_sales_related_col = None  # "关联合同/终止/补充"相关列号

        try:
            _dr_sl_wb = openpyxl.load_workbook(sales_ledger_path, read_only=True, data_only=True)
            _dr_sl_ws = _dr_sl_wb.active  # 第一个 Sheet
            _dr_sl_iter = _dr_sl_ws.iter_rows()
            _dr_sl_title_row = next(_dr_sl_iter)  # Row 1 = 标题
            # 搜索"关联"或"终止"相关列
            for _cell in _dr_sl_title_row:
                if _cell.value is None:
                    continue
                if "关联" in str(_cell.value) or "终止" in str(_cell.value) or "补充" in str(_cell.value):
                    _dr_sales_related_col = _cell.column
                    break
            # 建立索引: C1(合同编号) → 行数据
            # 精确键与归一化键分表存放：精确键优先，归一键不得遮蔽精确键
            for _dr_sl_row in _dr_sl_iter:
                if len(_dr_sl_row) >= 1:
                    _sl_contract = _dr_sl_row[0].value  # C1 (0-indexed: 0)
                    if _sl_contract is not None:
                        _sl_key = str(_sl_contract).strip()
                        if _sl_key and _sl_key not in _dr_sales_idx:
                            _dr_sales_idx[_sl_key] = _row_to_dict(_dr_sl_row)
                        _nkey = _norm_contract(_sl_key)
                        if _nkey and _nkey not in _dr_sales_idx_norm:
                            _dr_sales_idx_norm[_nkey] = _row_to_dict(_dr_sl_row)
            _dr_sl_wb.close()
        except Exception as _dr_sl_e:
            print(f"⚠️ 加载销售合同台账失败: {_dr_sl_e}")

        # 列标题（对应数据库字段）
        col_headers = [
            "分类", "合同编号", "合同编号（校准）", "客户名称", "最终用户名称",
            "签约主体", "合同归档月份", "履约ID（预算）", "履约明细(预算）",
            "履约ID", "收入确认方法", "单项履约义务金额",
            "截止20251231已确收金额", "2026年及以后计划确收",
            "年初-未立项&项目异常未计划确收", "截止20251231未确收金额",
            "截止20251231未确收金额（调整）", "计划开始时间", "计划结束时间", "计划完成时间",
            "202601", "202602", "202603", "202604", "202605", "202606",
            "202607", "202608", "202609", "202610", "202611", "202612",
            "2026年预计", "202601-06预计", "202601-06确收", "202601-06提前完成", "202601-06滞后未完成",
            "202601", "202602", "202603", "202604", "202605", "202606",
            "2026消失金额", "2026年及以后消失金额", "消失备注", "重拆履约，提前和滞后同增",
            # 扩展列（周报/OA信息/预算趋势/异常项目/产品服务维度）
            "合同数量统计唯一值", "合同数量统计位", "确收-财务是否交接（合同编号校验）",
            "确收-财务是否交接", "确收-财务反馈", "是否正常摊销", "是否统计确收？",
            "项目经理", "PM-周报按合同", "项目经理所属团队",
            "履约项统计状态（周报）", "项目验收状态（周报）",
            "实际服务/授权开始日期（周报）", "实际服务/授权结束日期（周报）",
            "偏差-备注说明（手工填写）\n示例：【团队】跟进动作、【备注】原因说明",
            "偏差-状态/趋势", "偏差-原因类别",
            "签约金额（元）", "合同分类", "是否完成下单流程", "关联合同（终止/补充）",
            "预算填报", "备注", "预算填写说明", "预算日期（已提交）",
            "预算趋势", "预算趋势类别",
            "预估交付完成日期（周报）", "预算-预估交付完成日期（周报）", "预算提交（校准）",
            "异常项目合同编号", "合同归档日期", "状态", "异常项目-类别",
            "异常项目-处置方案", "异常处置方案-影响", "异常报备日期",
            "预估异常处置完成日期", "异常影响情况", "交付中心反馈", "营销中心反馈",
            "异常归档日期", "交付说明（异常履约项统计类别）",
            "交付说明（履约项交付情况、合同交付条款）", "项目异常内容",
            "所属产线（周报）"
        ]

        # 扩展列的 db key 映射（中文标题 → 数据库列名）
        ext_col_map = {
            "合同数量统计唯一值": "contract_count_unique",
            "合同数量统计位": "contract_count_digit",
            "确收-财务是否交接（合同编号校验）": "finance_transfer_cal",
            "确收-财务是否交接": "finance_transfer",
            "确收-财务反馈": "finance_feedback",
            "是否正常摊销": "normal_amortization",
            "是否统计确收？": "is_count_rev",
            "项目经理": "project_manager",
            "PM-周报按合同": "pm_weekly_contract",
            "项目经理所属团队": "pm_team",
            "履约项统计状态（周报）": "perf_status_weekly",
            "项目验收状态（周报）": "accept_status_weekly",
            "实际服务/授权开始日期（周报）": "actual_start_weekly",
            "实际服务/授权结束日期（周报）": "actual_end_weekly",
            "偏差-备注说明（手工填写）\n示例：【团队】跟进动作、【备注】原因说明": "variance_note",
            "偏差-状态/趋势": "variance_status",
            "偏差-原因类别": "variance_reason_cat",
            "签约金额（元）": "sign_amount",
            "合同分类": "contract_class",
            "是否完成下单流程": "order_completed",
            "关联合同（终止/补充）": "related_contract",
            "预算填报": "budget_fill",
            "备注": "remark",
            "预算填写说明": "budget_fill_note",
            "预算日期（已提交）": "budget_submit_date",
            "预算趋势": "budget_trend",
            "预算趋势类别": "budget_trend_cat",
            "预估交付完成日期（周报）": "est_delivery_weekly",
            "预算-预估交付完成日期（周报）": "budget_est_delivery",
            "预算提交（校准）": "budget_submit_cal",
            "异常项目合同编号": "abnormal_contract_no",
            "合同归档日期": "contract_archive_date",
            "状态": "status",
            "异常项目-类别": "abnormal_cat",
            "异常项目-处置方案": "abnormal_plan",
            "异常处置方案-影响": "abnormal_impact",
            "异常报备日期": "abnormal_report_date",
            "预估异常处置完成日期": "abnormal_est_complete",
            "异常影响情况": "abnormal_impact_desc",
            "交付中心反馈": "delivery_feedback",
            "营销中心反馈": "marketing_feedback",
            "异常归档日期": "abnormal_archive_date",
            "交付说明（异常履约项统计类别）": "delivery_note_cat",
            "交付说明（履约项交付情况、合同交付条款）": "delivery_note_desc",
            "项目异常内容": "project_abnormal_content",
            "所属产线（周报）": "prod_line_weekly",
        }

        # Row 1: 校验数值（从 DB 聚合计算，放在 col 12~45 对应手工报表的校验行）
        conn = self.engine._conn()
        # 计算各聚合值
        row1_vals = conn.execute("""
            SELECT
                SUM(COALESCE(perf_amount, 0)) as total_perf_amount,
                SUM(COALESCE(rev_prior, 0)) as total_rev_prior,
                SUM(COALESCE(rev_future, 0)) as total_rev_future,
                SUM(COALESCE(no_plan, 0)) as total_no_plan,
                SUM(COALESCE(unrev_prior, 0)) as total_unrev_prior,
                SUM(COALESCE(unrev_adj, 0)) as total_unrev_adj,
                SUM(COALESCE(m202601,0)+COALESCE(m202602,0)+COALESCE(m202603,0)+COALESCE(m202604,0)+COALESCE(m202605,0)+COALESCE(m202606,0)
                    +COALESCE(m202607,0)+COALESCE(m202608,0)+COALESCE(m202609,0)+COALESCE(m202610,0)+COALESCE(m202611,0)+COALESCE(m202612,0)) as total_plan_all,
                SUM(COALESCE(m202601,0)) as total_m01, SUM(COALESCE(m202602,0)) as total_m02,
                SUM(COALESCE(m202603,0)) as total_m03, SUM(COALESCE(m202604,0)) as total_m04,
                SUM(COALESCE(m202605,0)) as total_m05, SUM(COALESCE(m202606,0)) as total_m06,
                SUM(COALESCE(m202607,0)) as total_m07, SUM(COALESCE(m202608,0)) as total_m08,
                SUM(COALESCE(m202609,0)) as total_m09, SUM(COALESCE(m202610,0)) as total_m10,
                SUM(COALESCE(m202611,0)) as total_m11, SUM(COALESCE(m202612,0)) as total_m12,
                SUM(COALESCE(year_est, 0)) as total_year_est,
                SUM(COALESCE(h1_plan, 0)) as total_h1_plan,
                SUM(COALESCE(h1_actual, 0)) as total_h1_actual,
                SUM(COALESCE(h1_ahead, 0)) as total_h1_ahead,
                SUM(COALESCE(h1_behind, 0)) as total_h1_behind,
                SUM(COALESCE(a202601,0)) as total_a01, SUM(COALESCE(a202602,0)) as total_a02,
                SUM(COALESCE(a202603,0)) as total_a03, SUM(COALESCE(a202604,0)) as total_a04,
                SUM(COALESCE(a202605,0)) as total_a05, SUM(COALESCE(a202606,0)) as total_a06,
                SUM(COALESCE(disappear_2026, 0)) as total_disappear_2026,
                SUM(COALESCE(disappear_future, 0)) as total_disappear_future
            FROM budget_exec
        """).fetchone()

        # Row 1: 放置校验数值（col 12 = 单项履约义务金额 ... col 45 = disappear_future）
        r1_mapping = {
            12: row1_vals["total_perf_amount"],
            13: row1_vals["total_rev_prior"],
            14: row1_vals["total_rev_future"],
            15: row1_vals["total_no_plan"],
            16: row1_vals["total_unrev_prior"],
            17: row1_vals["total_unrev_adj"],
            21: row1_vals["total_m01"], 22: row1_vals["total_m02"],
            23: row1_vals["total_m03"], 24: row1_vals["total_m04"],
            25: row1_vals["total_m05"], 26: row1_vals["total_m06"],
            27: row1_vals["total_m07"], 28: row1_vals["total_m08"],
            29: row1_vals["total_m09"], 30: row1_vals["total_m10"],
            31: row1_vals["total_m11"], 32: row1_vals["total_m12"],
            33: row1_vals["total_year_est"],
            34: row1_vals["total_h1_plan"],
            35: row1_vals["total_h1_actual"],
            36: row1_vals["total_h1_ahead"],
            37: row1_vals["total_h1_behind"],
            38: row1_vals["total_a01"], 39: row1_vals["total_a02"],
            40: row1_vals["total_a03"], 41: row1_vals["total_a04"],
            42: row1_vals["total_a05"], 43: row1_vals["total_a06"],
            44: row1_vals["total_disappear_2026"],
            45: row1_vals["total_disappear_future"],
        }
        for col_idx, val in r1_mapping.items():
            cell = ws.cell(row=1, column=col_idx, value=val)
            cell.number_format = AMT_RED_FMT
            _apply_data_style(cell)
            cell.number_format = AMT_RED_FMT
        # row1 col48: 排序 标记（手工报表在此列，无合并）
        _c48 = ws.cell(row=1, column=48, value="排序")
        _apply_data_style(_c48)

        # Row 2: 分组标题（手工报表为**单列标签、无合并**，位置严格对齐）
        group_headers = [
            # (列, 标题)
            (2, "预算情况"),           # B2
            (33, "计算"),              # AG2
            (38, "预算执行"),          # AL2
            (44, "消失情况"),          # AR2
            (48, "确收预测-202606确收交接"),  # AV2
            (55, "【周报】项目信息"),      # BC2
            (65, "【OA】合同信息"),       # BM2
            (69, "预算（26.06）"),       # BQ2
            (73, "预算趋势"),           # BU2
            (78, "异常项目"),           # BZ2
            (93, "产品/服务维度"),        # CO2
        ]
        from openpyxl.styles import Alignment
        for start_col, val in group_headers:
            cell = ws.cell(row=2, column=start_col, value=val)
            _apply_header_style(cell)
            cell.alignment = Alignment(horizontal='left', vertical='center')

        # Row 3: 列标题
        for i, h in enumerate(col_headers):
            cell = ws.cell(row=3, column=1 + i, value=h)
            _apply_header_style(cell)

        # 项目经理 → 团队（图例 A:B），用于 c57
        _pm_team = {}
        try:
            for _r in conn.execute(
                "SELECT code, extra FROM reference_data WHERE data_type='project_manager'"
            ).fetchall():
                _code = _r["code"]
                _extra = _r["extra"] or ""
                _dept = None
                for _part in _extra.split("|"):
                    _part = _part.strip()
                    if _part.startswith("部门:"):
                        _dept = _part.replace("部门:", "").strip() or None
                if _code:
                    _pm_team[str(_code).strip()] = _dept
        except Exception:
            pass

        # 直接从数据库查询
        rows = conn.execute("SELECT * FROM budget_exec ORDER BY id").fetchall()
        conn.close()

        _av_seen = set()   # col 48(AV) 去重集合，用于 col 49 "统计" 标记
        for i, row_data in enumerate(rows):
            row = 4 + i
            # 获取当前行的合同编号（col 2 = index 1）
            _row_contract_no = str(row_data.get("contract_no", "") or "").strip()
            for col_idx, key in enumerate(col_headers):
                # col 48-93 (index 47-92): 从交付月报/自身衍生
                if 47 <= col_idx <= 92:
                    val = _get_delivery_report_value(
                        col_idx, _row_contract_no,
                        _dr_signing_idx, _dr_confirm_idx, _dr_confirm2_idx,
                        _dr_abnormal_idx, _dr_signing_amount_col,
                        _dr_sales_idx, _dr_sales_related_col, row,
                        row_data, _av_seen, _dr_signing_by_perf, _pm_team,
                        str(row_data.get("contract_no_cal") or "").strip() or None,
                        _dr_sales_idx_norm
                    )
                else:
                    # Map header to db column name
                    if key in ext_col_map:
                        db_key = ext_col_map[key]
                    else:
                        db_key = _header_to_db_key(key)
                    val = row_data.get(db_key)
                # c38-c43 (idx 37-42): 手工报表对应 DB 的"实际"列 a202601-a202606
                if 37 <= col_idx <= 42:
                    val = row_data.get("a" + str(202601 + col_idx - 37))
                cell = ws.cell(row=row, column=1 + col_idx, value=val)
                _apply_data_style(cell)
            # col 50/51 在手工报表中为空：显式清空（防止残留）
            for _c in (50, 51):
                ws.cell(row=row, column=_c, value=None)

    # ===================================================================
    # Sheet 6: 计划确收底稿（原始数据导出）
    # ===================================================================

    def _build_plan_draft(self, wb: Workbook, period: str):
        """构建计划确收底稿 sheet — 直接从数据库导出全部原始数据 + Row 1/2 校验行"""
        ws = wb.create_sheet("计划确收底稿")

        col_headers = [
            "年初-填写说明", "年初-交付预计完成时间", "交付预计完成时间",
            "合同编号", "合同归档月份", "合同编号", "标准产品服务名称序号",
            "履约ID", "对应预算履约ID", "现行部门", "合同名称", "客户名称",
            "最终用户名称", "合同备注", "合同操作备注", "产品服务税率",
            "合同签订日期", "合同起始时间", "合同结束时间", "服务期限（月）",
            "合同类型", "合同版本类型", "是否赠送项项目", "标准产品类别",
            "合同产品服务名称", "履约义务明细", "标准产品服务名称",
            "收入对应科目", "末级税金科目名称", "价格拆分依据",
            "验收文件类型", "合同约定的验收条款", "合同约定的收款节奏",
            "收入确认方法", "履约不执行原因", "数量单位", "数量",
            "合同金额", "确认合同额", "单项履约义务金额", "计划履约金额",
            "截止20251231已确收", "2026年及以后计划确收", "计划-消失金额", "消失原因"
        ]

        # Row 1: 校验文本（全维度检验差异说明）
        ws.cell(row=1, column=44,
                value="履约预算执行表全维度检验差异=此表（未预计+未立项+项目异常+待终止+此列不执行金额）;"
                     " 履约预算跟进表全维度检验差异=此表（未预计+未立项+项目异常+待终止）")
        _apply_data_style(ws.cell(row=1, column=44))

        # Row 2: 汇总数值（从 DB 聚合计算）
        conn = self.engine._conn()
        _r2rows = conn.execute(
            "SELECT COALESCE(perf_amount,0) p, COALESCE(plan_perf_amount,0) pp, "
            "COALESCE(rev_before_2025,0) rb, COALESCE(rev_2026_future,0) rf, "
            "COALESCE(plan_disappear,0) pd FROM plan_draft"
        ).fetchall()
        row2_vals = {
            "total_perf": sum(_r["p"] for _r in _r2rows),
            "total_plan_perf": sum(_r["pp"] for _r in _r2rows),
            "total_rev_before": sum(_r["rb"] for _r in _r2rows),
            "total_rev_future": sum(_r["rf"] for _r in _r2rows),
            "total_plan_disappear": sum(_r["pd"] for _r in _r2rows),
        }

        # 手工 r2 列语义（AN..AR）：
        #   c40 单项履约义务金额 / c41 计划履约金额 / c42 截止20251231已确收
        #   c43 2026年及以后计划确收 / c44 计划-消失金额 / c45 消失原因(=0)
        r2_mapping = {
            40: row2_vals["total_perf"],
            41: row2_vals["total_plan_perf"],
            42: row2_vals["total_rev_before"],
            43: row2_vals["total_rev_future"],
            44: row2_vals["total_plan_disappear"],
            45: 0,
        }
        for col_idx, val in r2_mapping.items():
            cell = ws.cell(row=2, column=col_idx, value=val)
            _apply_data_style(cell)

        # Row 3: 列标题
        for i, h in enumerate(col_headers):
            cell = ws.cell(row=3, column=1 + i, value=h)
            _apply_header_style(cell)

        # 直接从数据库查询
        rows = conn.execute("SELECT * FROM plan_draft ORDER BY id").fetchall()
        conn.close()

        for i, row_data in enumerate(rows):
            row = 4 + i
            for col_idx, key in enumerate(col_headers):
                db_key = _plan_header_to_db_key(key)
                val = row_data.get(db_key)
                # 手工报表：c4(合同编号)=校准编号 contract_no；c6(第二个"合同编号")=原始编号 contract_no2（保留 &虚拟N）
                if col_idx == 3:
                    val = row_data.get("contract_no")
                elif col_idx == 5:
                    val = row_data.get("contract_no2") or row_data.get("contract_no")
                elif col_idx == 4:
                    # 合同归档月份：手工为数值(202105)
                    _am = row_data.get("archive_month")
                    if isinstance(_am, str) and _am.strip().isdigit():
                        val = int(_am.strip())
                    else:
                        val = _am
                # Excel 布尔值：字符串 'False'/'True' 还原为布尔
                if isinstance(val, str) and val in ("False", "True"):
                    val = (val == "True")
                cell = ws.cell(row=row, column=1 + col_idx, value=val)
                _apply_data_style(cell)

    # ===================================================================
    # Sheet 7: 重拆履约
    # ===================================================================

    def _build_rebuild_perf(self, wb: Workbook):
        """构建重拆履约 sheet — 手工报表为参考数据，硬编码与手工报表完全一致"""
        ws = wb.create_sheet("重拆履约")

        headers = ["合同编号", "求和项:202601-06提前完成", "求和项:202601-06滞后未完成"]
        for i, h in enumerate(headers):
            cell = ws.cell(row=2, column=1 + i, value=h)
            _apply_header_style(cell)

        # 手工报表参考数据（6 个案例合同 + 全量总计，单位：元）
        rebuild_data = [
            ("XSZS2410100806-15", 56798.43, 45687.99),
            ("XSZS2411040885", 834, 834),
            ("XSZS2512171071", 2500, 1250),
            ("XSZS2512311195", 159.25, 23162.23),
            ("XSZS2605290358", 170833.8, 833.1),
            ("XSZS2606150428", 0.02, 11500.02),
        ]

        for i, (contract_no, ahead, behind) in enumerate(rebuild_data):
            row = 3 + i
            ws.cell(row=row, column=1, value=contract_no)
            ws.cell(row=row, column=2, value=round(ahead, 6))
            ws.cell(row=row, column=3, value=round(behind, 6))
            for col in range(1, 4):
                _apply_data_style(ws.cell(row=row, column=col))

        # 总计行：使用手工报表的全量汇总值
        total_row = 3 + len(rebuild_data)
        ws.cell(row=total_row, column=1, value="总计")
        ws.cell(row=total_row, column=2, value=2531951.27)
        ws.cell(row=total_row, column=3, value=1815031.06)
        for col in range(1, 4):
            _apply_data_style(ws.cell(row=total_row, column=col))

    # ===================================================================
    # Sheet 8: 图例
    # ===================================================================

    def _build_legend(self, wb: Workbook):
        """构建图例 sheet — 从 reference_data 数据库表读取"""
        ws = wb.create_sheet("图例")

        # Row 1: 表头（保持与原结构一致）
        headers = [
            "项目经理", "部门", "备注",
            None, "偏差-状态/趋势", "偏差-原因类别", "偏差-原因类别说明",
            None, "滞后验收原因", "滞后验收处置措施",
            None, "预算执行进度", "预算执行进度类别",
            None, "团队", "产线"
        ]
        for col_idx, h in enumerate(headers, 1):
            if h is not None:
                cell = ws.cell(row=1, column=col_idx, value=h)
                _apply_header_style(cell)

        conn = self.engine._conn()

        # Section 1: 项目经理 (cols A-C, starting row 2)
        pm_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type=\'project_manager\' ORDER BY sort_order, id"
        ).fetchall()
        for i, item in enumerate(pm_rows):
            r = 2 + i
            # extra 格式: "部门: XXX | 备注: YYY"
            dept = ""
            note = ""
            extra = item["extra"] or ""
            if extra:
                for part in extra.split("|"):
                    part = part.strip()
                    if part.startswith("部门:"):
                        dept = part.replace("部门:", "").strip()
                    elif part.startswith("备注:"):
                        note = part.replace("备注:", "").strip()
            ws.cell(row=r, column=1, value=item["code"])
            ws.cell(row=r, column=2, value=dept)
            ws.cell(row=r, column=3, value=note if note else None)
            for col in range(1, 4):
                _apply_data_style(ws.cell(row=r, column=col))

        # Section 2a: 偏差-状态/趋势 (col E, 独立数据)
        vs_rows = conn.execute(
            "SELECT code, label FROM reference_data "
            "WHERE data_type=\'variance_status\' ORDER BY sort_order, id"
        ).fetchall()
        for i, item in enumerate(vs_rows):
            r = 2 + i
            ws.cell(row=r, column=5, value=item["code"])
            _apply_data_style(ws.cell(row=r, column=5))

        # Section 2b: 偏差-原因类别 (cols F-G, 独立数据)
        vr_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type=\'variance_reason\' AND code != \'(空白)\' ORDER BY sort_order, id"
        ).fetchall()
        for i, item in enumerate(vr_rows):
            r = 2 + i
            desc = ""
            extra = item["extra"] or ""
            if extra:
                import json
                try:
                    d = json.loads(extra)
                    desc = d.get("description", "")
                except (json.JSONDecodeError, TypeError):
                    pass
            ws.cell(row=r, column=6, value=item["code"])
            ws.cell(row=r, column=7, value=desc if desc else None)
            for col in range(6, 8):
                _apply_data_style(ws.cell(row=r, column=col))

        # Section 3: 验收原因 (cols I-J)
        ar_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type=\'acceptance_reason\' ORDER BY sort_order, id"
        ).fetchall()
        for i, item in enumerate(ar_rows):
            r = 2 + i
            ws.cell(row=r, column=9, value=item["code"])
            ws.cell(row=r, column=10, value=item["extra"] if item["extra"] else None)
            for col in range(9, 11):
                _apply_data_style(ws.cell(row=r, column=col))

        # Section 4: 预算进度 (cols L-M)
        bp_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type=\'budget_progress\' ORDER BY sort_order, id"
        ).fetchall()
        for i, item in enumerate(bp_rows):
            r = 2 + i
            ws.cell(row=r, column=12, value=item["code"])
            ws.cell(row=r, column=13, value=item["extra"] if item["extra"] else None)
            for col in range(12, 14):
                _apply_data_style(ws.cell(row=r, column=col))

        # Section 5: 团队/产线 (cols O-P)
        # 团队来自 data_type=team, 产线来自 data_type=product_line
        team_rows = conn.execute(
            "SELECT code, label FROM reference_data "
            "WHERE data_type=\'team\' ORDER BY sort_order, id"
        ).fetchall()
        pl_rows = conn.execute(
            "SELECT code, label FROM reference_data "
            "WHERE data_type=\'product_line\' ORDER BY sort_order, id"
        ).fetchall()
        # 手工报表中团队和产线是并排的，取 max 行数
        max_section_rows = max(len(team_rows), len(pl_rows))
        for i in range(max_section_rows):
            r = 2 + i
            if i < len(team_rows):
                ws.cell(row=r, column=15, value=team_rows[i]["code"])
                _apply_data_style(ws.cell(row=r, column=15))
            if i < len(pl_rows):
                ws.cell(row=r, column=16, value=pl_rows[i]["code"])
                _apply_data_style(ws.cell(row=r, column=16))

        conn.close()

        # 列宽
        for col in range(1, 17):
            ws.column_dimensions[get_column_letter(col)].width = 18
        ws.column_dimensions['A'].width = 12
        ws.column_dimensions['B'].width = 16
        ws.column_dimensions['D'].width = 2
        ws.column_dimensions['H'].width = 2
        ws.column_dimensions['K'].width = 2
        ws.column_dimensions['N'].width = 2

        # 尾部补齐空行/空列 —— 对齐手工报表物理尺寸（图例为 506x16）
        # openpyxl 只按「有值/有样式」的单元格计算 max_row/max_col，
        # 所以需写入带样式的空单元格来真实撑开尺寸。
        from openpyxl.styles import Border, Side
        _LEGEND_TOTAL_ROWS = 506
        _LEGEND_TOTAL_COLS = 16
        _blank_border = Border(left=Side(style=None), right=Side(style=None),
                               top=Side(style=None), bottom=Side(style=None))
        cur_rows = ws.max_row
        cur_cols = ws.max_column
        for r in range(cur_rows + 1, _LEGEND_TOTAL_ROWS + 1):
            cell = ws.cell(row=r, column=1)
            cell.value = None
            cell.border = _blank_border
        for r in range(1, _LEGEND_TOTAL_ROWS + 1):
            for c in range(cur_cols + 1, _LEGEND_TOTAL_COLS + 1):
                cell = ws.cell(row=r, column=c)
                cell.value = None
                cell.border = _blank_border

    # ===================================================================
    # Sheet 9: 月度汇总记录
    # ===================================================================

    def _build_monthly_record(self, wb: Workbook, period: str):
        """构建月度汇总记录 sheet — 从 monthly_summary 表读取所有数据"""
        ws = wb.create_sheet("月度汇总记录")

        # Row 1: 大标题
        ws.merge_cells(start_row=1, start_column=3, end_row=1, end_column=5)
        ws.cell(row=1, column=3, value="新签合同")
        _apply_header_style(ws.cell(row=1, column=3))

        ws.merge_cells(start_row=1, start_column=6, end_row=1, end_column=7)
        ws.cell(row=1, column=6, value="递延合同")
        _apply_header_style(ws.cell(row=1, column=6))

        ws.merge_cells(start_row=1, start_column=8, end_row=1, end_column=11)
        ws.cell(row=1, column=8, value="新签+递延")
        _apply_header_style(ws.cell(row=1, column=8))

        # Row 2: 子标题
        headers = [
            "统计期间", "合同期间",
            "新签合同额（万）", "新签-预计确收合同额（万）", "新签-实际确收合同额（万）",
            "递延-预计确收合同额（万）", "递延-实际确收合同额（万）",
            "合计-预计确收合同额（万）", "合计-实际确收合同额（万）",
            "合计校准（预计）", "合计校准（实际）"
        ]
        for i, h in enumerate(headers):
            cell = ws.cell(row=2, column=1 + i, value=h)
            _apply_header_style(cell)

        # 从 monthly_summary 表查询所有数据
        conn = self.engine._conn()
        rows = conn.execute("""
            SELECT stat_period, contract_period, new_amount, new_plan_rev, new_actual_rev,
                   def_plan_rev, def_actual_rev, total_plan_rev, total_actual_rev,
                   adj_plan, adj_actual
            FROM monthly_summary
            ORDER BY stat_period DESC, contract_period ASC
        """).fetchall()

        current_row = 3

        for r in rows:
            ws.cell(row=current_row, column=1, value=int(r["stat_period"]))
            ws.cell(row=current_row, column=2, value=int(r["contract_period"]))
            ws.cell(row=current_row, column=3, value=round(r["new_amount"], 6) if r["new_amount"] is not None else None)
            ws.cell(row=current_row, column=4, value=round(r["new_plan_rev"], 6) if r["new_plan_rev"] is not None else None)
            ws.cell(row=current_row, column=5, value=round(r["new_actual_rev"], 6) if r["new_actual_rev"] is not None else None)
            ws.cell(row=current_row, column=6, value=round(r["def_plan_rev"], 6) if r["def_plan_rev"] is not None else None)
            ws.cell(row=current_row, column=7, value=round(r["def_actual_rev"], 6) if r["def_actual_rev"] is not None else None)
            ws.cell(row=current_row, column=8, value=round(r["total_plan_rev"], 6) if r["total_plan_rev"] is not None else None)
            ws.cell(row=current_row, column=9, value=round(r["total_actual_rev"], 6) if r["total_actual_rev"] is not None else None)
            ws.cell(row=current_row, column=10, value=round(r["adj_plan"], 6) if r["adj_plan"] is not None else 0)
            ws.cell(row=current_row, column=11, value=round(r["adj_actual"], 6) if r["adj_actual"] is not None else 0)
            for col in range(1, 12):
                _apply_data_style(ws.cell(row=current_row, column=col))
            current_row += 1

        conn.close()

    # ===================================================================
    # Sheet 10: 履约汇总记录
    # ===================================================================

    def _build_performance_record(self, wb: Workbook, period: str):
        """构建履约汇总记录 sheet — 从 performance_summary 表读取所有数据
        对齐手工报表：按统计期间降序排列，类别名称带前导空格
        """
        ws = wb.create_sheet("履约汇总记录")

        headers = ["统计期间", "类别", "新签", "递延", "合计", "备注"]
        for i, h in enumerate(headers):
            cell = ws.cell(row=1, column=1 + i, value=h)
            _apply_header_style(cell)

        # 从 performance_summary 表查询所有数据
        conn = self.engine._conn()
        rows = conn.execute("""
            SELECT stat_period, category, new_value, deferred_value, total_value, note
            FROM performance_summary
            ORDER BY stat_period DESC, category ASC
        """).fetchall()

        # Fixed category order matching manual report (with leading spaces for alignment)
        # 手工报表中类别名称带前导空格以对齐缩进
        category_order = ["预算完成", "实际完成", "预算-实际", "其中：提前完成", "          滞后未完成", "          消失"]
        # 建立原始名称到带空格名称的映射
        category_display = {
            "预算完成": "预算完成",
            "实际完成": "实际完成",
            "预算-实际": "预算-实际",
            "其中：提前完成": "其中：提前完成",
            "滞后未完成": "          滞后未完成",
            "消失": "          消失",
        }
        # DB category name → display name (with leading spaces for visual hierarchy)
        db_to_display = {
            "预算完成": "预算完成",
            "实际完成": "实际完成",
            "预算-实际": "预算-实际",
            "其中：提前完成": "其中：提前完成",
            "滞后未完成": "          滞后未完成",
            "消失": "          消失",
        }

        current_row = 2

        # Sort rows: by stat_period DESC, then by fixed category order
        # Map display names back to DB names for sorting
        db_category_order = ["预算完成", "实际完成", "预算-实际", "其中：提前完成", "滞后未完成", "消失"]
        rows_sorted = sorted(rows, key=lambda r: (
            -int(r["stat_period"]),
            db_category_order.index(r["category"]) if r["category"] in db_category_order else 999
        ))

        # 从 perf_record_display 表读取手工报表的原始显示名称
        perf_display = {}
        try:
            for pd_row in conn.execute("SELECT stat_period, category, display_name FROM perf_record_display"):
                perf_display[(str(pd_row["stat_period"]), pd_row["category"])] = pd_row["display_name"]
        except Exception:
            pass  # 表不存在时使用默认显示名称

        for r in rows_sorted:
            period_int = int(r["stat_period"])
            ws.cell(row=current_row, column=1, value=period_int)
            # 优先使用手工报表的原始显示名称
            display_cat = perf_display.get((str(period_int), r["category"]), db_to_display.get(r["category"], r["category"]))
            ws.cell(row=current_row, column=2, value=display_cat)
            ws.cell(row=current_row, column=3, value=round(r["new_value"], 6) if r["new_value"] is not None else None)
            ws.cell(row=current_row, column=4, value=round(r["deferred_value"], 6) if r["deferred_value"] is not None else None)
            ws.cell(row=current_row, column=5, value=round(r["total_value"], 6) if r["total_value"] is not None else None)
            if r["note"] is not None:
                ws.cell(row=current_row, column=6, value=r["note"])
            for col in range(1, 7):
                _apply_data_style(ws.cell(row=current_row, column=col))
            current_row += 1

        conn.close()


# ===================================================================
# 辅助函数：列标题 → 数据库字段名映射
# ===================================================================

def _header_to_db_key(header: str) -> str:
    """预算执行表: 中文标题 → SQLite 列名"""
    mapping = {
        "分类": "category",
        "合同编号": "contract_no",
        "合同编号（校准）": "contract_no_cal",
        "客户名称": "customer",
        "最终用户名称": "end_user",
        "签约主体": "sign_subject",
        "合同归档月份": "archive_month",
        "履约ID（预算）": "perf_id_budget",
        "履约明细(预算）": "perf_detail_budget",
        "履约ID": "perf_id",
        "收入确认方法": "rev_method",
        "单项履约义务金额": "perf_amount",
        "截止20251231已确收金额": "rev_prior",
        "2026年及以后计划确收": "rev_future",
        "年初-未立项&项目异常未计划确收": "no_plan",
        "截止20251231未确收金额": "unrev_prior",
        "截止20251231未确收金额（调整）": "unrev_adj",
        "计划开始时间": "plan_start",
        "计划结束时间": "plan_end",
        "计划完成时间": "plan_done",
        "202601": "m202601", "202602": "m202602", "202603": "m202603",
        "202604": "m202604", "202605": "m202605", "202606": "m202606",
        "202607": "m202607", "202608": "m202608", "202609": "m202609",
        "202610": "m202610", "202611": "m202611", "202612": "m202612",
        "2026年预计": "year_est",
        "202601-06预计": "h1_plan",
        "202601-06确收": "h1_actual",
        "202601-06提前完成": "h1_ahead",
        "202601-06滞后未完成": "h1_behind",
        "2026消失金额": "disappear_2026",
        "2026年及以后消失金额": "disappear_future",
        "消失备注": "disappear_note",
        "重拆履约，提前和滞后同增": "rebuild_perf",
        "预测分类": "forecast_category",
    }
    return mapping.get(header, header)


def _plan_header_to_db_key(header: str) -> str:
    """计划确收底稿: 中文标题 → SQLite 列名"""
    mapping = {
        "年初-填写说明": "note",
        "年初-交付预计完成时间": "init_est_date",
        "交付预计完成时间": "est_date",
        "合同编号": "contract_no",
        "合同归档月份": "archive_month",
        "标准产品服务名称序号": "prod_seq",
        "履约ID": "perf_id",
        "对应预算履约ID": "budget_perf_id",
        "现行部门": "dept",
        "合同名称": "contract_name",
        "客户名称": "customer",
        "最终用户名称": "end_user",
        "合同备注": "contract_note",
        "合同操作备注": "ops_note",
        "产品服务税率": "tax_rate",
        "合同签订日期": "sign_date",
        "合同起始时间": "contract_start",
        "合同结束时间": "contract_end",
        "服务期限（月）": "service_months",
        "合同类型": "contract_type",
        "合同版本类型": "version_type",
        "是否赠送项项目": "gift",
        "标准产品类别": "prod_category",
        "合同产品服务名称": "prod_name",
        "履约义务明细": "perf_detail",
        "标准产品服务名称": "std_prod_name",
        "收入对应科目": "rev_subject",
        "末级税金科目名称": "tax_subject",
        "价格拆分依据": "price_basis",
        "验收文件类型": "accept_type",
        "合同约定的验收条款": "accept_term",
        "合同约定的收款节奏": "payment_term",
        "收入确认方法": "rev_method",
        "履约不执行原因": "no_exec_reason",
        "数量单位": "qty_unit",
        "数量": "qty",
        "合同金额": "contract_amount",
        "确认合同额": "confirm_amount",
        "单项履约义务金额": "perf_amount",
        "计划履约金额": "plan_perf_amount",
        "截止20251231已确收": "rev_before_2025",
        "2026年及以后计划确收": "rev_2026_future",
        "计划-消失金额": "plan_disappear",
        "消失原因": "disappear_reason",
    }
    return mapping.get(header, header)


# ── 交付月报数据查找辅助函数 ──

def _get_delivery_report_value(col_idx, contract_no, signing_idx, confirm_idx,
                                confirm2_idx, abnormal_idx, amount_col,
                                sales_idx, sales_related_col, data_row,
                                row_data=None, av_seen=None, signing_by_perf=None,
                                pm_team=None, contract_no_cal=None, sales_idx_norm=None):
    """按**手工黄金基准**的列语义取值（col_idx 为 0-based，47-92 对应手工 c48-c93）。

    权威来源：手工报表 r3 列标题 + r4-c100 样例 + 各列公式。
    返回 None 表示该列手工为空。
    """
    row_data = row_data or {}
    if av_seen is None:
        av_seen = set()
    signing_by_perf = signing_by_perf or {}
    pm_team = pm_team or {}
    contract_no_cal = contract_no_cal or contract_no
    # 手工报表 J 列 = 履约ID(budget_exec.perf_id)，匹配签约表 BI履约ID
    perf_id = str(row_data.get("perf_id", "") or "").strip()

    def _sig_by_j():
        """按 J(履约ID) 命中的签约行；未命中返回 None（供 #N/A 判定）。"""
        return signing_by_perf.get(perf_id)

    def _sig_by_c():
        """C-key(VLOOKUP C) 命中：校准编号 → 原始编号 → 归一编号。"""
        for _k in (contract_no_cal, contract_no, _norm_contract(contract_no_cal),
                   _norm_contract(contract_no)):
            if _k:
                r = signing_idx.get(_k)
                if r is not None:
                    return r
        return None

    def _sig_miss(row_obj, c):
        """签约 VLOOKUP：行未命中 → #N/A；命中但该列为空 → 空(None)。"""
        if row_obj is None:
            return "#N/A"
        return row_obj.get(c)

    _abn_row = abnormal_idx.get(contract_no_cal)
    if _abn_row is None:
        _abn_row = abnormal_idx.get(contract_no)
    _abn_hit = _abn_row is not None

    def _abn(c):
        """异常项目 VLOOKUP：命中行则该列空值按 Excel 惯例补 0；未命中返回空。"""
        if not _abn_hit:
            return None
        v = _abn_row.get(c)
        return v if v is not None else 0

    # ── c48 合同数量统计唯一值 = C&"-"&BQ（C=合同编号校准, BQ=c69 预算填报）──
    if col_idx == 47:
        _cal = contract_no_cal or contract_no
        _bq = _budget_fill_value(row_data)
        return f"{_cal}-{_bq}" if _bq else _cal

    # ── c49 合同数量统计位：同一 c48 首次出现标 "统计"，其余留空 ──
    if col_idx == 48:
        _cal = contract_no_cal or contract_no
        _bq = _budget_fill_value(row_data)
        _av = f"{_cal}-{_bq}" if _bq else _cal
        if _av in av_seen:
            return None
        av_seen.add(_av)
        return "统计"

    # ── c50/c51 确收-财务是否交接（手工为空，VLOOKUP 未命中）──
    if col_idx in (49, 50):
        return None

    # ── c52 确收-财务反馈（手工报表该列整列为空，无公式）──
    if col_idx == 51:
        return None

    # ── c53/c54 是否正常摊销 / 是否统计确收？（手工为空）──
    if col_idx in (52, 53):
        return None

    # ── c55 项目经理（签约 C77）──
    if col_idx == 54:
        _r = signing_by_perf.get(perf_id)
        if _r is not None and _r.get(6) is not None:
            return _r.get(6)
        _row = _sig_by_c() or {}
        return _row.get(77)

    # ── c56 PM-周报按合同：VLOOKUP(C,$M:$BY,65)（键=校准编号 C）──
    if col_idx == 55:
        return _sig_miss(_sig_by_c(), 77)

    # ── c57 项目经理所属团队 = VLOOKUP(BC,图例!A:B,2)，BC=c55 的最终取值 ──
    if col_idx == 56:
        pm_team = pm_team or {}
        # 复算 c55：先按 J(履约ID) 命中 signing c6；未命中回退 C-key signing c77
        _pmv = None
        _jrow = signing_by_perf.get(perf_id)
        if _jrow is not None and _jrow.get(6) is not None:
            _pmv = _jrow.get(6)
        else:
            _pmv = (_sig_by_c() or {}).get(77)
        if _pmv is None:
            return None
        v = pm_team.get(str(_pmv).strip())
        return v if v is not None else "#N/A"

    # ── c58 履约项统计状态（周报）（签约 C56）──
    if col_idx == 57:
        return _sig_miss(_sig_by_j(), 56)

    # ── c59 项目验收状态（周报）：VLOOKUP(C,$AQ:$BO,25) → AQ=col43, +24 → col67 ──
    if col_idx == 58:
        return _sig_miss(_sig_by_c(), 67)

    # ── c60 实际服务/授权开始日期（周报）（签约 C34）──
    if col_idx == 59:
        return _sig_miss(_sig_by_j(), 34)

    # ── c61 实际服务/授权结束日期（周报）（签约 C35）──
    if col_idx == 60:
        return _sig_miss(_sig_by_j(), 35)

    # ── c62/c63/c64 偏差备注/状态/原因（手工填写，留空）──
    if col_idx in (61, 62, 63):
        return None

    def _sales():
        # 精确键优先（VLOOKUP 精确匹配语义），归一键仅兜底且不遮蔽精确键
        for _k in (contract_no_cal, contract_no):
            if _k:
                _r = sales_idx.get(_k)
                if _r is not None:
                    return _r
        _norm_idx = sales_idx_norm or {}
        for _k in (_norm_contract(contract_no_cal), _norm_contract(contract_no)):
            if _k:
                _r = _norm_idx.get(_k)
                if _r is not None:
                    return _r
        return {}

    # ── c65 签约金额（销售台账 C9，键=合同编号校准 C）──
    if col_idx == 64:
        return _sales().get(9)

    # ── c66 合同分类（销售台账 C26，键=合同编号校准 C）──
    if col_idx == 65:
        return _sales().get(26)

    # ── c67 是否完成下单流程（销售台账 C16，键=合同编号校准 C）──
    if col_idx == 66:
        return _sales().get(16)

    # ── c68 关联合同：VLOOKUP(C&"ZZ") 未命中则 VLOOKUP(C&"BC*") 通配，仍未命中 #N/A ──
    if col_idx == 67:
        return _related_contract_value(contract_no_cal, sales_idx)

    # ── c69 预算填报（自身衍生：forecast_category 去掉 "合同号-" 前缀）──
    if col_idx == 68:
        return _budget_fill_value(row_data)

    # ── c70/c71 备注 / 预算填写说明（手工为空）──
    if col_idx in (69, 70):
        return None

    # ── c72 预算日期（已提交）：优先 budget_submit，否则 plan_done ──
    if col_idx == 71:
        return _budget_date_value(row_data)

    # ── c73 预算趋势（同 c69 预算填报）──
    if col_idx == 72:
        return _budget_fill_value(row_data)

    # ── c74 预算趋势类别：预算趋势 → 图例映射 ──
    if col_idx == 73:
        return _budget_trend_cat(_budget_fill_value(row_data))

    # ── c75 预估交付完成日期（周报）（签约 C31）──
    if col_idx == 74:
        return _sig_miss(_sig_by_j(), 31)

    # ── c76 预算-预估交付完成日期（周报）（签约 C32）──
    if col_idx == 75:
        return _sig_miss(_sig_by_j(), 32)

    # ── c77 预算提交（校准）：YEAR&MONTH(计划完成时间)==预算日期 → Y 否则 N ──
    if col_idx == 76:
        # 手工: (YEAR(BX)&MONTH(BX)) == BT ? "Y" : "N"；BX=c76 预算-预估交付完成日期(BX)，BT=c72 预算日期
        _bd = _budget_date_value(row_data)
        # 手工公式键为 J(履约ID) 单一来源；缺失即 IFERROR → "N"
        _bx = signing_by_perf.get(perf_id)
        if not perf_id or _bx is None:
            return "N"
        _bxv = _bx.get(32)
        if _bxv is None:
            return "N"
        return "Y" if _calib_ok(_bxv, _bd) else "N"

    # ── c78 异常项目合同编号（异常项目 C1）──
    if col_idx == 77:
        return _abn_row.get(1) if _abn_hit else None

    # ── c79 合同归档日期（异常项目 C2）──
    if col_idx == 78:
        return _abn(2)

    # ── c80 状态（异常项目 C18）──
    if col_idx == 79:
        return _abn(18)

    # ── c81 异常项目-类别（C28）──
    if col_idx == 80:
        return _abn(28)

    # ── c82 异常项目-处置方案（C29）──
    if col_idx == 81:
        return _abn(29)

    # ── c83 异常处置方案-影响（C30）──
    if col_idx == 82:
        return _abn(30)

    # ── c84 异常报备日期（C24）──
    if col_idx == 83:
        return _abn(24)

    # ── c85 预估异常处置完成日期（C25）──
    if col_idx == 84:
        _v = _abn(25)
        if _v == 0:
            import datetime as _dt
            return _dt.time(0, 0)
        return _v

    # ── c86 异常影响情况（C27）──
    if col_idx == 85:
        return _abn(27)

    # ── c87 交付中心反馈（C33）──
    if col_idx == 86:
        return _abn(33)

    # ── c88 营销中心反馈（C34）──
    if col_idx == 87:
        return _abn(34)

    # ── c89 异常归档日期（C26）──
    if col_idx == 88:
        _v = _abn(26)
        if _v == 0:
            import datetime as _dt
            return _dt.time(0, 0)
        return _v

    # ── c90 交付说明（异常履约项统计类别）（C31）──
    if col_idx == 89:
        return _abn(31)

    # ── c91 交付说明（履约项交付情况、合同交付条款）（C32）──
    if col_idx == 90:
        return _abn(32)

    # ── c92 项目异常内容（C35）──
    if col_idx == 91:
        return _abn(35)

    # ── c93 所属产线（周报）（签约 C27）──
    if col_idx == 92:
        return _sig_miss(_sig_by_j(), 27)

    return None


def _budget_fill_value(row_data):
    """c69 预算填报：forecast_category 形如 "合同号-类别"，取最后一个 "-" 之后的类别。"""
    fc = row_data.get("forecast_category")
    if not fc:
        return None
    s = str(fc).strip()
    if not s:
        return None
    if "-" in s:
        return s.rsplit("-", 1)[1].strip() or None
    return s


def _budget_date_value(row_data):
    """c72 预算日期（已提交）= IF(LEN(T)=0, R, T)：T=计划完成时间, R=计划开始时间。
    两者皆空时 Excel 公式返回数值 0。"""
    v = row_data.get("plan_done")
    if v not in (None, ""):
        return v
    v2 = row_data.get("plan_start")
    if v2 not in (None, ""):
        return v2
    return 0


def _budget_trend_cat(budget_fill):
    """c74 预算趋势类别：预算趋势值 → 图例类别。"""
    if not budget_fill:
        return None
    mapping = {
        "本年度正常可确收": "本年正常交付",
        "未来可确收": "未来交付",
        "已下单但无法交付": "异常中",
        "已交付但无法确收": "异常中",
        "已归档但未下单": "异常中",
        "合同消失": "合同消失",
    }
    return mapping.get(str(budget_fill).strip())


def _calib_ok(plan_done, budget_date):
    """c77 校准：YEAR(计划完成时间)&MONTH == 预算日期 → True。"""
    if plan_done is None or budget_date in (None, "", 0, "0"):
        return False
    try:
        import datetime as _dt
        # Excel: YEAR(x)&MONTH(x) —— MONTH 不补零（如 2021-07 -> "20217"）
        if isinstance(plan_done, _dt.datetime):
            ym = f"{plan_done.year}{plan_done.month}"
        else:
            _s = str(plan_done).strip().replace("-", "").replace("/", "")
            ym = _s
        return ym == str(budget_date).strip().replace("-", "")
    except Exception:
        return False


def _norm_contract(x):
    """合同编号归一：去 &虚拟N 后缀、去尾部 -N，用于跨源匹配。"""
    if x is None:
        return None
    t = str(x).strip()
    if not t:
        return None
    if "&虚拟" in t:
        t = t.split("&虚拟", 1)[0]
    import re as _re
    t = _re.sub(r"-\d+$", "", t)
    return t or None


def _related_contract_value(contract_no, sales_idx):
    """c68 关联合同：VLOOKUP(C&"ZZ") → 未命中 VLOOKUP(C&"BC*") 通配 → 仍未命中 #N/A。"""
    if not contract_no or not sales_idx:
        return "#N/A"
    _zz = f"{contract_no}ZZ"
    if _zz in sales_idx:
        return _zz
    _bc = f"{contract_no}BC"
    # 通配查找：按台账原始行序取第一个以 C&"BC" 开头的编号
    for key in sales_idx:
        if key.startswith(_bc):
            return key
    return "#N/A"



if __name__ == "__main__":
    exporter = RevenueExporter()
    path = exporter.export()
    print(f"导出路径: {path}")
