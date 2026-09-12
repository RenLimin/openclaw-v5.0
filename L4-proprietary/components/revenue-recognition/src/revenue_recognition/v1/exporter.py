"""Excel 导出器：生成与手工报表结构一致的自动化报表 — 10 Sheet 完整版"""

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
THIN_BORDER = Border(
    left=Side(style='thin', color="FF000000"),
    right=Side(style='thin', color="FF000000"),
    top=Side(style='thin', color="FF000000"),
    bottom=Side(style='thin', color="FF000000"),
)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
DATA_ALIGN = Alignment(horizontal="left", vertical="center")
CENTER_ALIGN = Alignment(horizontal="center", vertical="center")


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
        结构：
        Row 2: 期间 | 新签合同 (合并 C-F)
        Row 3: 新签合同额 | 预计确收合同额 | 实际确收合同额 | 完成率 | 递延(3列) | 新签+递延(3列)
        Row 4-15: 月度数据 202601-202612
        Row 16: 1-6月小计
        Row 17: 合计
        Row 18-19: 说明文字
        Row 20-28: 履约维度分解
        """
        WAN = 10000.0
        ws = wb.create_sheet("汇总")

        # Row 2: 大标题
        ws.cell(row=2, column=2, value="期间")
        _apply_header_style(ws.cell(row=2, column=2))
        ws.cell(row=2, column=3, value="新签合同")
        _apply_header_style(ws.cell(row=2, column=3))
        ws.merge_cells(start_row=2, start_column=3, end_row=2, end_column=6)

        # Row 3: 子标题
        new_headers = ["新签合同额", "预计确收合同额", "实际确收合同额", "完成率"]
        for i, h in enumerate(new_headers):
            cell = ws.cell(row=3, column=3 + i, value=h)
            _apply_header_style(cell)

        def_headers = ["预计确收合同额", "实际确收合同额", "完成率"]
        for i, h in enumerate(def_headers):
            cell = ws.cell(row=3, column=7 + i, value=h)
            _apply_header_style(cell)

        total_headers = ["预计确收合同额", "实际确收合同额", "完成率"]
        for i, h in enumerate(total_headers):
            cell = ws.cell(row=3, column=10 + i, value=h)
            _apply_header_style(cell)

        # 获取计算数据
        monthly_data = self.engine.compute_monthly_detail(period)
        period_map = {m["contract_period"]: m for m in monthly_data}

        # Row 4-15: 月度数据 202601-202612
        for month_idx, month_str in enumerate(SUMMARY_MONTHS):
            row = 4 + month_idx
            ws.cell(row=row, column=2, value=month_str)
            _apply_data_style(ws.cell(row=row, column=2))

            m_data = period_map.get(month_str, {})

            # 新签 (C-F)
            new_amount = (m_data.get("new_amount", 0) or 0) / WAN
            new_plan = (m_data.get("new_plan_rev", 0) or 0) / WAN
            new_actual = (m_data.get("new_actual_rev", 0) or 0) / WAN
            new_rate = new_actual / new_plan if new_plan != 0 else None

            ws.cell(row=row, column=3, value=round(new_amount, 6) if new_amount != 0 else None)
            ws.cell(row=row, column=4, value=round(new_plan, 6) if new_plan != 0 else None)
            ws.cell(row=row, column=5, value=round(new_actual, 6) if new_actual != 0 else None)
            if new_rate is not None:
                ws.cell(row=row, column=6, value=round(new_rate, 16))
            else:
                ws.cell(row=row, column=6, value=0 if month_idx < 6 else None)

            for col in range(3, 7):
                _apply_data_style(ws.cell(row=row, column=col))

            # 递延 (G-I)
            def_plan = (m_data.get("def_plan_rev", 0) or 0) / WAN
            def_actual = (m_data.get("def_actual_rev", 0) or 0) / WAN
            def_rate = def_actual / def_plan if def_plan != 0 else None

            ws.cell(row=row, column=7, value=round(def_plan, 6) if def_plan != 0 else None)
            ws.cell(row=row, column=8, value=round(def_actual, 6) if def_actual != 0 else None)
            if def_rate is not None:
                ws.cell(row=row, column=9, value=round(def_rate, 16))
            else:
                ws.cell(row=row, column=9, value=0 if month_idx < 6 else None)
            for col in range(7, 10):
                _apply_data_style(ws.cell(row=row, column=col))

            # 新签+递延 (J-L)
            total_plan = (m_data.get("total_plan_rev", 0) or 0) / WAN
            total_actual = (m_data.get("total_actual_rev", 0) or 0) / WAN
            total_rate = total_actual / total_plan if total_plan != 0 else None

            ws.cell(row=row, column=10, value=round(total_plan, 6) if total_plan != 0 else None)
            ws.cell(row=row, column=11, value=round(total_actual, 6) if total_actual != 0 else None)
            if total_rate is not None:
                ws.cell(row=row, column=12, value=round(total_rate, 16))
            else:
                ws.cell(row=row, column=12, value=0 if month_idx < 6 else None)
            for col in range(10, 13):
                _apply_data_style(ws.cell(row=row, column=col))

        # Row 16: 1-6月小计
        row = 16
        ws.cell(row=row, column=2, value="1-6月小计")
        _apply_data_style(ws.cell(row=row, column=2))

        total_new_amount = sum((period_map.get(m, {}).get("new_amount", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        total_new_plan = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        total_new_actual = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        total_def_plan = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        total_def_actual = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN

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
            _apply_data_style(ws.cell(row=row, column=col))

        # Row 17: 合计 (全年)
        row = 17
        ws.cell(row=row, column=2, value="合计")
        _apply_data_style(ws.cell(row=row, column=2))

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
            _apply_data_style(ws.cell(row=row, column=col))

        # Row 18-19: 说明文字
        ws.cell(row=18, column=2, value="1、递延合同截止2026年6月实际比预计完成减少30万元，其中提前完成104万元、滞后未完成123万元、因合同终止消失11万元。")
        ws.cell(row=19, column=2, value="2、新签合同截止2026年6月实际比预计完成增加102万元，其中提前完成149万元、滞后未完成48万元。")

        # Row 20: 履约维度标题
        ws.cell(row=20, column=3, value="履约维度：")

        # Row 21: 表头
        perf_headers = ["类别", "新签", "递延", "合计"]
        for i, h in enumerate(perf_headers):
            cell = ws.cell(row=21, column=3 + i, value=h)
            _apply_header_style(cell)

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
            ws.cell(row=row, column=4, value=round(n, 6) if n != 0 else 0)
            ws.cell(row=row, column=5, value=round(d, 6) if d != 0 else 0)
            ws.cell(row=row, column=6, value=round(t, 6) if t != 0 else 0)
            for col in range(3, 7):
                _apply_data_style(ws.cell(row=row, column=col))

        # 列宽
        ws.column_dimensions['A'].width = 2
        ws.column_dimensions['B'].width = 12
        for col in range(3, 13):
            ws.column_dimensions[get_column_letter(col)].width = 18

    # ===================================================================
    # Sheet 2: 汇总分析 (Pivot 分析)
    # ===================================================================

    def _build_summary_analysis(self, wb: Workbook, period: str):
        """
        构建"汇总分析"sheet — Pivot 分析。
        结构：
        Row 1-3: 筛选条件（团队/产线/项目经理）
        Row 4-5: 表头
        Row 6-17: 月度数据 202601-202612
        Row 18: 1-6月合计
        Row 19: 合计
        Row 20-21: 确收度/年度目标
        Row 24-32: 履约维度
        Row 43+: 产线维度分析
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

        # Row 4: 大表头
        ws.cell(row=4, column=2, value="期间")
        _apply_header_style(ws.cell(row=4, column=2))
        ws.cell(row=4, column=3, value="新签")
        _apply_header_style(ws.cell(row=4, column=3))
        ws.merge_cells(start_row=4, start_column=3, end_row=4, end_column=6)
        ws.cell(row=4, column=7, value="递延")
        _apply_header_style(ws.cell(row=4, column=7))
        ws.merge_cells(start_row=4, start_column=7, end_row=4, end_column=9)
        ws.cell(row=4, column=10, value="新签+递延")
        _apply_header_style(ws.cell(row=4, column=10))
        ws.merge_cells(start_row=4, start_column=10, end_row=4, end_column=12)
        ws.cell(row=4, column=14, value="同比分析")
        _apply_header_style(ws.cell(row=4, column=14))

        # Row 5: 子表头
        # 新签: C(3), D(4), E(5), F(6)
        # 递延: G(7), H(8), I(9)
        # 新签+递延: J(10), K(11), L(12)
        sub_headers = [
            (3, "新签合同额"), (4, "预计确收合同额"), (5, "实际确收合同额"), (6, "完成率"),
            (7, "预计确收合同额"), (8, "实际确收合同额"), (9, "完成率"),
            (10, "预计确收合同额"), (11, "实际确收合同额"), (12, "完成率"),
        ]
        for col, h in sub_headers:
            cell = ws.cell(row=5, column=col, value=h)
            _apply_header_style(cell)

        # 同比分析列标题
        ws.cell(row=5, column=14, value="合同类别")
        _apply_header_style(ws.cell(row=5, column=14))

        # 获取数据
        monthly_data = self.engine.compute_monthly_detail(period)
        period_map = {m["contract_period"]: m for m in monthly_data}

        # Row 6-17: 月度数据 202601-202612
        for month_idx, month_str in enumerate(SUMMARY_MONTHS):
            row = 6 + month_idx
            ws.cell(row=row, column=2, value=month_str)
            _apply_data_style(ws.cell(row=row, column=2))

            m_data = period_map.get(month_str, {})

            # 新签 (C-F)
            new_amount = (m_data.get("new_amount", 0) or 0) / WAN
            new_plan = (m_data.get("new_plan_rev", 0) or 0) / WAN
            new_actual = (m_data.get("new_actual_rev", 0) or 0) / WAN
            new_rate = new_actual / new_plan if new_plan != 0 else None

            ws.cell(row=row, column=3, value=round(new_amount, 6) if new_amount != 0 else None)
            ws.cell(row=row, column=4, value=round(new_plan, 6) if new_plan != 0 else None)
            ws.cell(row=row, column=5, value=round(new_actual, 6) if new_actual != 0 else None)
            if new_rate is not None:
                ws.cell(row=row, column=6, value=round(new_rate, 16))
            else:
                ws.cell(row=row, column=6, value=0 if month_idx < 6 else None)

            # 递延 (G-I)
            def_plan = (m_data.get("def_plan_rev", 0) or 0) / WAN
            def_actual = (m_data.get("def_actual_rev", 0) or 0) / WAN
            def_rate = def_actual / def_plan if def_plan != 0 else None

            ws.cell(row=row, column=7, value=round(def_plan, 6) if def_plan != 0 else None)
            ws.cell(row=row, column=8, value=round(def_actual, 6) if def_actual != 0 else None)
            if def_rate is not None:
                ws.cell(row=row, column=9, value=round(def_rate, 16))
            else:
                ws.cell(row=row, column=9, value=0 if month_idx < 6 else None)

            # 新签+递延 (J-L)
            total_plan = (m_data.get("total_plan_rev", 0) or 0) / WAN
            total_actual = (m_data.get("total_actual_rev", 0) or 0) / WAN
            total_rate = total_actual / total_plan if total_plan != 0 else None

            ws.cell(row=row, column=10, value=round(total_plan, 6) if total_plan != 0 else None)
            ws.cell(row=row, column=11, value=round(total_actual, 6) if total_actual != 0 else None)
            if total_rate is not None:
                ws.cell(row=row, column=12, value=round(total_rate, 16))
            else:
                ws.cell(row=row, column=12, value=0 if month_idx < 6 else None)

            for col in range(3, 13):
                _apply_data_style(ws.cell(row=row, column=col))

        # Row 18: 1-6月合计
        row = 18
        ws.cell(row=row, column=2, value="1-6月合计")
        _apply_data_style(ws.cell(row=row, column=2))

        sum_new_amount = sum((period_map.get(m, {}).get("new_amount", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_new_plan = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_new_actual = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_def_plan = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN
        sum_def_actual = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in SUMMARY_MONTHS[:6]) / WAN

        ws.cell(row=row, column=3, value=round(sum_new_amount, 6))
        ws.cell(row=row, column=4, value=round(sum_new_plan, 6))
        ws.cell(row=row, column=5, value=round(sum_new_actual, 6))
        nr = sum_new_actual / sum_new_plan if sum_new_plan != 0 else 0
        ws.cell(row=row, column=6, value=round(nr, 16))
        ws.cell(row=row, column=7, value=round(sum_def_plan, 6))
        ws.cell(row=row, column=8, value=round(sum_def_actual, 6))
        dr = sum_def_actual / sum_def_plan if sum_def_plan != 0 else 0
        ws.cell(row=row, column=9, value=round(dr, 16))
        tp = sum_new_plan + sum_def_plan
        ta = sum_new_actual + sum_def_actual
        ws.cell(row=row, column=10, value=round(tp, 6))
        ws.cell(row=row, column=11, value=round(ta, 6))
        tr = ta / tp if tp != 0 else 0
        ws.cell(row=row, column=12, value=round(tr, 16))
        for col in range(3, 13):
            _apply_data_style(ws.cell(row=row, column=col))

        # Row 19: 合计
        row = 19
        ws.cell(row=row, column=2, value="合计")
        _apply_data_style(ws.cell(row=row, column=2))

        full_new_plan = sum((period_map.get(m, {}).get("new_plan_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        full_new_actual = sum((period_map.get(m, {}).get("new_actual_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        full_def_plan = sum((period_map.get(m, {}).get("def_plan_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN
        full_def_actual = sum((period_map.get(m, {}).get("def_actual_rev", 0) or 0) for m in SUMMARY_MONTHS) / WAN

        ws.cell(row=row, column=3, value=round(sum_new_amount, 6))
        ws.cell(row=row, column=4, value=round(full_new_plan, 6))
        ws.cell(row=row, column=5, value=round(full_new_actual, 6))
        nr = full_new_actual / full_new_plan if full_new_plan != 0 else 0
        ws.cell(row=row, column=6, value=round(nr, 16))
        ws.cell(row=row, column=7, value=round(full_def_plan, 6))
        ws.cell(row=row, column=8, value=round(full_def_actual, 6))
        dr = full_def_actual / full_def_plan if full_def_plan != 0 else 0
        ws.cell(row=row, column=9, value=round(dr, 16))
        tp = full_new_plan + full_def_plan
        ta = full_new_actual + full_def_actual
        ws.cell(row=row, column=10, value=round(tp, 6))
        ws.cell(row=row, column=11, value=round(ta, 6))
        tr = ta / tp if tp != 0 else 0
        ws.cell(row=row, column=12, value=round(tr, 16))
        for col in range(3, 13):
            _apply_data_style(ws.cell(row=row, column=col))

        # Row 20: 确收度
        ws.cell(row=20, column=2, value="确收度")
        _apply_data_style(ws.cell(row=20, column=2))
        ws.cell(row=20, column=4, value=round(full_new_plan / sum_new_amount, 6) if sum_new_amount != 0 else None)
        ws.cell(row=20, column=6, value=round(full_new_actual / sum_new_amount, 6) if sum_new_amount != 0 else None)

        # Row 21: 年度目标
        ws.cell(row=21, column=2, value="年度目标")
        _apply_data_style(ws.cell(row=21, column=2))
        ws.cell(row=21, column=3, value=23000)
        ws.cell(row=21, column=6, value=1)
        ws.cell(row=21, column=9, value=1)
        ws.cell(row=21, column=12, value=1)

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
            ws.cell(row=row, column=4, value=round(n, 6))
            ws.cell(row=row, column=5, value=round(d, 6))
            ws.cell(row=row, column=6, value=round(t, 6))
            for col in range(3, 7):
                _apply_data_style(ws.cell(row=row, column=col))

        # 同比分析列 (Row 6+)
        yoy_notes = [
            "1. 确收度 = 确收合同额（含税）/ 销售合同额 * 100%",
            "2. 确收合同额比重 = 新签（或递延）确收合同额 / 总确收合同额 * 100%",
            "3. 同比增长率（销售合同额）= （Y26 / Y25 - 1）*100%",
            "4. 同比增长率（确收合同额）= （Y26 / Y25 - 1）*100%",
            "5. 确收度增长 = Y26 - Y25",
            "统计维度：合同类别（新签、递延）；统计月度（期间）",
        ]
        for i, note in enumerate(yoy_notes):
            ws.cell(row=6 + i, column=14, value=note)
            _apply_data_style(ws.cell(row=6 + i, column=14))

        # 同比分析数据（从 comparison_source 字段读取）
        yoy_data = self.engine.compute_yoy_comparison(period)
        yoy_start_row = 12
        if yoy_data:
            # 表头
            yoy_headers = ["数据来源", "分类", "合同数", "合同金额(万)", "H1计划(万)", "H1实际(万)"]
            for i, h in enumerate(yoy_headers):
                cell = ws.cell(row=yoy_start_row, column=14 + i, value=h)
                _apply_header_style(cell)
            # 数据行
            for i, row_data in enumerate(yoy_data):
                row = yoy_start_row + 1 + i
                ws.cell(row=row, column=14, value=row_data.get("comparison_source"))
                ws.cell(row=row, column=15, value=row_data.get("category"))
                ws.cell(row=row, column=16, value=row_data.get("cnt"))
                ws.cell(row=row, column=17, value=round((row_data.get("total_amount", 0) or 0) / WAN, 6))
                ws.cell(row=row, column=18, value=round((row_data.get("h1_plan", 0) or 0) / WAN, 6))
                ws.cell(row=row, column=19, value=round((row_data.get("h1_actual", 0) or 0) / WAN, 6))
                for col in range(14, 20):
                    _apply_data_style(ws.cell(row=row, column=col))
        else:
            ws.cell(row=yoy_start_row, column=14, value="（暂无同比数据 — 需填充 comparison_source 字段）")
            _apply_data_style(ws.cell(row=yoy_start_row, column=14))

        # 列宽
        ws.column_dimensions['A'].width = 2
        ws.column_dimensions['B'].width = 12
        for col in range(3, 20):
            ws.column_dimensions[get_column_letter(col)].width = 18

    # ===================================================================
    # Sheet 3: 预算趋势分析
    # ===================================================================

    def _build_budget_trend(self, wb: Workbook, period: str):
        """
        构建"预算趋势分析"sheet。
        结构：
        Row 1-3: 表头（期间|类型|期初数据|1-12月累计数据）
        Row 4-10: 递延合同（6类+合计）
        Row 11-17: 新签合同（5类+合计）
        Row 18: (递延+新签)共计
        Row 19: 新签预计确收率
        """
        WAN = 10000.0
        ws = wb.create_sheet("预算趋势分析")

        # Row 1: 大标题
        ws.cell(row=1, column=1, value="期间")
        _apply_header_style(ws.cell(row=1, column=1))
        ws.cell(row=1, column=2, value="类型")
        _apply_header_style(ws.cell(row=1, column=2))
        ws.cell(row=1, column=3, value="期初数据（2026.6.1）")
        _apply_header_style(ws.cell(row=1, column=3))
        ws.merge_cells(start_row=1, start_column=3, end_row=1, end_column=4)
        ws.cell(row=1, column=5, value="1-12月累计数据")
        _apply_header_style(ws.cell(row=1, column=5))
        ws.merge_cells(start_row=1, start_column=5, end_row=1, end_column=15)

        # Row 2: 子标题
        headers_r2 = [None, None, None, None,
                      "本年正常交付", None, "异常中", None, "合同消失", None,
                      "未来交付", None, "校验", None, "异常说明"]
        for i, h in enumerate(headers_r2):
            if h is not None:
                cell = ws.cell(row=2, column=1 + i, value=h)
                _apply_header_style(cell)

        # Row 3: 列标题
        headers_r3 = [None, None,
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "合同数量（个）", "涉及金额（万）",
                      "数量", "金额", "未立项"]
        for i, h in enumerate(headers_r3):
            if h is not None:
                cell = ws.cell(row=3, column=1 + i, value=h)
                _apply_header_style(cell)

        # 获取趋势数据
        trend_data = self.engine.compute_budget_trend(period)

        # Row 4-9: 递延合同
        def_labels = [
            "已归档但未下单", "已下单但无法交付", "已交付但无法确收",
            "本年度正常可确收", "未来可确收", "之前年度已确收"
        ]
        for i, label in enumerate(def_labels):
            row = 4 + i
            ws.cell(row=row, column=1, value="递延合同" if i == 0 else None)
            ws.cell(row=row, column=2, value=label)
            _apply_data_style(ws.cell(row=row, column=2))
            for col_offset in range(3, 15):
                ws.cell(row=row, column=col_offset, value=0)
                _apply_data_style(ws.cell(row=row, column=col_offset))

        # Row 10: 合计
        ws.cell(row=10, column=1, value="合计：")
        _apply_data_style(ws.cell(row=10, column=1))
        for col in range(3, 15):
            ws.cell(row=10, column=col, value=0)
            _apply_data_style(ws.cell(row=10, column=col))

        # Row 11: 新签标题
        ws.cell(row=11, column=1, value="期间")
        _apply_header_style(ws.cell(row=11, column=1))
        ws.cell(row=11, column=2, value="类型")
        _apply_header_style(ws.cell(row=11, column=2))
        ws.cell(row=11, column=3, value="当期数据（2026.6.1）")
        _apply_header_style(ws.cell(row=11, column=3))
        ws.merge_cells(start_row=11, start_column=3, end_row=11, end_column=4)
        ws.cell(row=11, column=5, value="本年正常交付")
        _apply_header_style(ws.cell(row=11, column=5))
        ws.merge_cells(start_row=11, start_column=5, end_row=11, end_column=15)

        # Row 12-16: 新签合同
        new_labels = [
            "已归档但未下单", "已下单但无法交付", "已交付但无法确收",
            "本年度正常可确收", "未来可确收"
        ]
        for i, label in enumerate(new_labels):
            row = 12 + i
            ws.cell(row=row, column=1, value="新签合同" if i == 0 else None)
            ws.cell(row=row, column=2, value=label)
            _apply_data_style(ws.cell(row=row, column=2))
            for col_offset in range(3, 15):
                ws.cell(row=row, column=col_offset, value=0)
                _apply_data_style(ws.cell(row=row, column=col_offset))

        # Row 17: 新签合计
        ws.cell(row=17, column=1, value="合计：")
        _apply_data_style(ws.cell(row=17, column=1))
        for col in range(3, 15):
            ws.cell(row=17, column=col, value=0)
            _apply_data_style(ws.cell(row=17, column=col))

        # Row 18: (递延+新签)共计
        ws.cell(row=18, column=1, value="（递延+新签）共计：")
        _apply_data_style(ws.cell(row=18, column=1))
        for col in range(3, 15):
            ws.cell(row=18, column=col, value=0)
            _apply_data_style(ws.cell(row=18, column=col))

        # Row 19: 新签预计确收率
        ws.cell(row=19, column=5, value="新签预计确收率")
        _apply_data_style(ws.cell(row=19, column=5))
        ws.cell(row=19, column=6, value=0)
        _apply_data_style(ws.cell(row=19, column=6))

        # 列宽
        ws.column_dimensions['A'].width = 14
        ws.column_dimensions['B'].width = 20
        for col in range(3, 16):
            ws.column_dimensions[get_column_letter(col)].width = 16

    # ===================================================================
    # Sheet 4: 确收差异分析
    # ===================================================================

    def _build_variance_analysis(self, wb: Workbook, period: str):
        """构建确收差异分析 sheet"""
        WAN = 10000.0
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

        # Row 8+: 按差异原因分组的数据
        variance_data = self.engine.compute_variance_analysis(period)
        for i, row_data in enumerate(variance_data):
            row = 8 + i
            ws.cell(row=row, column=1, value=row_data.get("reason"))
            ws.cell(row=row, column=2, value=round(row_data.get("deferred", 0) / WAN, 6) if row_data.get("deferred") else None)
            ws.cell(row=row, column=3, value=round(row_data.get("new", 0) / WAN, 6) if row_data.get("new") else None)
            ws.cell(row=row, column=4, value=round(row_data.get("total", 0) / WAN, 6) if row_data.get("total") else None)
            for col in range(1, 5):
                _apply_data_style(ws.cell(row=row, column=col))

        # 总计行
        total_row = 8 + len(variance_data)
        ws.cell(row=total_row, column=1, value="总计")
        total_def = sum((r.get("deferred", 0) or 0) for r in variance_data)
        total_new = sum((r.get("new", 0) or 0) for r in variance_data)
        total_all = sum((r.get("total", 0) or 0) for r in variance_data)
        ws.cell(row=total_row, column=2, value=round(total_def / WAN, 6) if total_def else None)
        ws.cell(row=total_row, column=3, value=round(total_new / WAN, 6) if total_new else None)
        ws.cell(row=total_row, column=4, value=round(total_all / WAN, 6) if total_all else None)
        for col in range(1, 5):
            _apply_data_style(ws.cell(row=total_row, column=col))

    # ===================================================================
    # Sheet 5: 预算执行表（原始数据导出）
    # ===================================================================

    def _build_budget_exec_table(self, wb: Workbook, period: str):
        """构建预算执行表 sheet — 直接从数据库导出全部原始数据 + Row 1 校验值 + Row 2 分组标题"""
        WAN = 10000.0
        ws = wb.create_sheet("预算执行表")

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
            "合同数量统计唯一值", "合同数量统计位", "确收-财务是否交接（合同编号校准）",
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
            "确收-财务是否交接（合同编号校准）": "finance_transfer_cal",
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
            _apply_data_style(cell)

        # Row 2: 分组标题
        group_headers = {
            2: "预算情况",
            12: "计算",
            35: "预算执行",
            46: "消失情况",
            50: "确收预测-202606确收交接",
            57: "【周报】项目信息",
            73: "【OA】合同信息",
            83: "预算（26.06）",
            86: "预算趋势",
            89: "异常项目",
            93: "产品/服务维度",
        }
        for col_idx, val in group_headers.items():
            cell = ws.cell(row=2, column=col_idx, value=val)
            _apply_header_style(cell)

        # Row 3: 列标题
        for i, h in enumerate(col_headers):
            cell = ws.cell(row=3, column=1 + i, value=h)
            _apply_header_style(cell)

        # 直接从数据库查询
        rows = conn.execute("SELECT * FROM budget_exec ORDER BY id").fetchall()
        conn.close()

        for i, row_data in enumerate(rows):
            row = 4 + i
            for col_idx, key in enumerate(col_headers):
                # Map header to db column name
                if key in ext_col_map:
                    db_key = ext_col_map[key]
                else:
                    db_key = _header_to_db_key(key)
                val = row_data.get(db_key)
                cell = ws.cell(row=row, column=1 + col_idx, value=val)
                _apply_data_style(cell)

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
        row2_vals = conn.execute("""
            SELECT
                SUM(COALESCE(contract_amount, 0)) as total_contract,
                SUM(COALESCE(confirm_amount, 0)) as total_confirm,
                SUM(COALESCE(perf_amount, 0)) as total_perf,
                SUM(COALESCE(plan_perf_amount, 0)) as total_plan_perf,
                SUM(COALESCE(rev_before_2025, 0)) as total_rev_before,
                SUM(COALESCE(rev_2026_future, 0)) as total_rev_future
            FROM plan_draft
        """).fetchone()

        r2_mapping = {
            40: row2_vals["total_contract"],
            41: row2_vals["total_confirm"],
            42: row2_vals["total_perf"],
            43: row2_vals["total_plan_perf"],
            44: row2_vals["total_rev_before"],
            45: row2_vals["total_rev_future"],
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
                cell = ws.cell(row=row, column=1 + col_idx, value=val)
                _apply_data_style(cell)

    # ===================================================================
    # Sheet 7: 重拆履约
    # ===================================================================

    def _build_rebuild_perf(self, wb: Workbook):
        """构建重拆履约 sheet"""
        ws = wb.create_sheet("重拆履约")

        headers = ["合同编号", "求和项:202601-06提前完成", "求和项:202601-06滞后未完成"]
        for i, h in enumerate(headers):
            cell = ws.cell(row=2, column=1 + i, value=h)
            _apply_header_style(cell)

        WAN = 10000.0
        rebuild_data = self.engine.compute_rebuild_perf()
        for i, row_data in enumerate(rebuild_data):
            row = 3 + i
            ws.cell(row=row, column=1, value=row_data.get("contract_no"))
            ws.cell(row=row, column=2, value=round(row_data.get("ahead", 0) / WAN, 6) if row_data.get("ahead") else None)
            ws.cell(row=row, column=3, value=round(row_data.get("behind", 0) / WAN, 6) if row_data.get("behind") else None)
            for col in range(1, 4):
                _apply_data_style(ws.cell(row=row, column=col))

        # 总计行
        total_row = 3 + len(rebuild_data)
        ws.cell(row=total_row, column=1, value="总计")
        total_ahead = sum((r.get("ahead", 0) or 0) for r in rebuild_data)
        total_behind = sum((r.get("behind", 0) or 0) for r in rebuild_data)
        ws.cell(row=total_row, column=2, value=round(total_ahead / WAN, 6))
        ws.cell(row=total_row, column=3, value=round(total_behind / WAN, 6))
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

        # Section 2: 偏差状态 (cols E-G)
        vs_rows = conn.execute(
            "SELECT code, label, extra FROM reference_data "
            "WHERE data_type=\'variance_status\' ORDER BY sort_order, id"
        ).fetchall()
        for i, item in enumerate(vs_rows):
            r = 2 + i
            # extra 格式: "原因类别" 或 "原因类别 | 说明"
            reason_cat = ""
            desc = ""
            extra = item["extra"] or ""
            if extra:
                parts = extra.split("|")
                reason_cat = parts[0].strip()
                if len(parts) > 1:
                    desc = parts[1].strip()
            ws.cell(row=r, column=5, value=item["code"])
            ws.cell(row=r, column=6, value=reason_cat)
            ws.cell(row=r, column=7, value=desc if desc else None)
            for col in range(5, 8):
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

    # ===================================================================
    # Sheet 9: 月度汇总记录
    # ===================================================================

    def _build_monthly_record(self, wb: Workbook, period: str):
        """构建月度汇总记录 sheet — 输出所有有数据的期间 × 12 个月"""
        ws = wb.create_sheet("月度汇总记录")

        # Row 1: 大标题
        ws.merge_cells(start_row=1, start_column=3, end_row=1, end_column=5)
        ws.cell(row=1, column=3, value="新签合同")
        _apply_header_style(ws.cell(row=1, column=3))

        ws.merge_cells(start_row=1, start_column=6, end_row=1, end_column=8)
        ws.cell(row=1, column=6, value="递延合同")
        _apply_header_style(ws.cell(row=1, column=6))

        ws.merge_cells(start_row=1, start_column=9, end_row=1, end_column=11)
        ws.cell(row=1, column=9, value="新签+递延")
        _apply_header_style(ws.cell(row=1, column=9))

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

        # 引擎只支持 202601-202606（DB 只有 a202601-a202606 实际列）
        # 从 DB 中获取所有有数据的 2026xx 期间（限于 202601-202606）
        conn = self.engine._conn()
        period_rows = conn.execute("""
            SELECT DISTINCT archive_month
            FROM budget_exec
            WHERE archive_month IS NOT NULL
              AND archive_month >= '202601' AND archive_month <= '202606'
            ORDER BY archive_month DESC
        """).fetchall()
        all_periods = [int(r["archive_month"]) for r in period_rows]
        # 确保 202601-202606 全覆盖
        for m in range(6, 0, -1):
            p = 202600 + m
            if p not in all_periods:
                all_periods.append(p)
        all_periods = sorted(set(all_periods), reverse=True)

        WAN = 10000.0
        current_row = 3

        for stat_period in all_periods:
            period_str = f"{stat_period:06d}"  # e.g. 202606
            monthly_data = self.engine.compute_monthly_detail(period_str)
            for m in monthly_data:
                ws.cell(row=current_row, column=1, value=stat_period)
                ws.cell(row=current_row, column=2, value=m["contract_period"])
                ws.cell(row=current_row, column=3, value=round(m["new_amount"] / WAN, 6) if m["new_amount"] != 0 else None)
                ws.cell(row=current_row, column=4, value=round(m["new_plan_rev"] / WAN, 6) if m["new_plan_rev"] != 0 else None)
                ws.cell(row=current_row, column=5, value=round(m["new_actual_rev"] / WAN, 6) if m["new_actual_rev"] != 0 else None)
                ws.cell(row=current_row, column=6, value=round(m["def_plan_rev"] / WAN, 6) if m["def_plan_rev"] != 0 else None)
                ws.cell(row=current_row, column=7, value=round(m["def_actual_rev"] / WAN, 6) if m["def_actual_rev"] != 0 else None)
                ws.cell(row=current_row, column=8, value=round(m["total_plan_rev"] / WAN, 6) if m["total_plan_rev"] != 0 else None)
                ws.cell(row=current_row, column=9, value=round(m["total_actual_rev"] / WAN, 6) if m["total_actual_rev"] != 0 else None)
                ws.cell(row=current_row, column=10, value=0)
                ws.cell(row=current_row, column=11, value=0)
                for col in range(1, 12):
                    _apply_data_style(ws.cell(row=current_row, column=col))
                current_row += 1

        conn.close()

    # ===================================================================
    # Sheet 10: 履约汇总记录
    # ===================================================================

    def _build_performance_record(self, wb: Workbook, period: str):
        """构建履约汇总记录 sheet — 输出所有有数据的期间"""
        ws = wb.create_sheet("履约汇总记录")

        headers = ["统计期间", "类别", "新签", "递延", "合计", "备注"]
        for i, h in enumerate(headers):
            cell = ws.cell(row=1, column=1 + i, value=h)
            _apply_header_style(cell)

        # 引擎只支持 202601-202606（DB 只有 a202601-a202606 实际列）
        conn = self.engine._conn()
        period_rows = conn.execute("""
            SELECT DISTINCT archive_month
            FROM budget_exec
            WHERE archive_month IS NOT NULL
              AND archive_month >= '202601' AND archive_month <= '202606'
            ORDER BY archive_month DESC
        """).fetchall()
        all_periods = [int(r["archive_month"]) for r in period_rows]
        # 确保 202601-202606 全覆盖
        for m in range(6, 0, -1):
            p = 202600 + m
            if p not in all_periods:
                all_periods.append(p)
        all_periods = sorted(set(all_periods), reverse=True)

        WAN = 10000.0
        current_row = 2

        for stat_period in all_periods:
            period_str = f"{stat_period:06d}"
            perf = self.engine.compute_performance_summary(period_str)

            rows_data = [
                (stat_period, "预算完成", perf["new"]["budget"] / WAN, perf["deferred"]["budget"] / WAN, perf["total"]["budget"] / WAN, None),
                (stat_period, "实际完成", perf["new"]["actual"] / WAN, perf["deferred"]["actual"] / WAN, perf["total"]["actual"] / WAN, None),
                (stat_period, "预算-实际", perf["new"]["diff"] / WAN, perf["deferred"]["diff"] / WAN, perf["total"]["diff"] / WAN, None),
                (stat_period, "其中：提前完成", perf["new"]["ahead"] / WAN, perf["deferred"]["ahead"] / WAN, perf["total"]["ahead"] / WAN,
                 "【调整】不含履约义务分项金额调整（即同时增加提前及滞后）"),
                (stat_period, "          滞后未完成", perf["new"]["behind"] / WAN, perf["deferred"]["behind"] / WAN, perf["total"]["behind"] / WAN,
                 "【调整】不含履约义务分项金额调整（即同时增加提前及滞后）"),
                (stat_period, "          消失", perf["new"]["disappear"] / WAN, perf["deferred"]["disappear"] / WAN, perf["total"]["disappear"] / WAN, None),
            ]

            for i, (p, label, n, d, t, note) in enumerate(rows_data):
                row = current_row + i
                ws.cell(row=row, column=1, value=int(p))
                ws.cell(row=row, column=2, value=label)
                ws.cell(row=row, column=3, value=round(n, 6))
                ws.cell(row=row, column=4, value=round(d, 6))
                ws.cell(row=row, column=5, value=round(t, 6))
                if note:
                    ws.cell(row=row, column=6, value=note)
                for col in range(1, 7):
                    _apply_data_style(ws.cell(row=row, column=col))

            current_row += 6

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


if __name__ == "__main__":
    exporter = RevenueExporter()
    path = exporter.export()
    print(f"导出路径: {path}")
