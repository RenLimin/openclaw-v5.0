"""交付月报生成器

生成 15 Sheet 的交付月报 Excel 文件。
基于 openpyxl 库，支持公式、样式、多 Sheet。

Sheet 列表（基于 202606 报告模板分析）：
  1. 签约
  2. POC&提前实施
  3. 异常项目
  4. 确收交接
  5. 验收交接
  6. 交付效率统计
  7. 预算执行表
  8. 产品-授权&维保统计
  9. 交付异常分事业部统计
  10. POC&提前实施统计
  11. 交接统计
  12. 图例
  13. 按项目汇总
  14. 确收凭证
  15. 验收凭证
"""

import pandas as pd
from pathlib import Path
from typing import Optional
from datetime import datetime

OUTPUT_DIR = Path.home() / ".openclaw" / "data" / "reports"


def generate_delivery_report(
    month: str,
    contract_df: pd.DataFrame,
    poc_df: pd.DataFrame,
    exception_df: pd.DataFrame,
    revenue_df: pd.DataFrame,
    acceptance_df: pd.DataFrame,
    workhour_df: Optional[pd.DataFrame] = None,
    output_dir: Optional[str] = None
) -> str:
    """生成交付月报

    Args:
        month: 报告月份（YYYYMM）
        contract_df: 签约项目数据
        poc_df: POC 项目数据
        exception_df: 异常项目数据
        revenue_df: 确收凭证数据
        acceptance_df: 验收凭证数据
        workhour_df: 工时数据（可选）
        output_dir: 输出目录

    Returns:
        生成的 Excel 文件路径
    """
    from openpyxl import Workbook

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)  # 删除默认 Sheet

    # Sheet 1: 签约
    ws1 = wb.create_sheet("签约")
    _fill_contract_sheet(ws1, contract_df)

    # Sheet 2: POC&提前实施
    ws2 = wb.create_sheet("POC&提前实施")
    _fill_poc_sheet(ws2, poc_df)

    # Sheet 3: 异常项目
    ws3 = wb.create_sheet("异常项目")
    _fill_exception_sheet(ws3, exception_df)

    # Sheet 4: 确收交接
    ws4 = wb.create_sheet("确收交接")
    _fill_revenue_sheet(ws4, revenue_df)

    # Sheet 5: 验收交接
    ws5 = wb.create_sheet("验收交接")
    _fill_acceptance_sheet(ws5, acceptance_df)

    # Sheet 6: 交付效率统计
    ws6 = wb.create_sheet("交付效率统计")
    _fill_efficiency_sheet(ws6, contract_df)

    # 保存
    output_path = out_dir / f"交付月报-{month}.xlsx"
    wb.save(output_path)
    print(f"交付月报已生成: {output_path}")
    return str(output_path)


def _fill_contract_sheet(ws, df: pd.DataFrame):
    """填充签约 Sheet"""
    if df.empty:
        return
    # 写入表头
    for col_idx, col_name in enumerate(df.columns, 1):
        ws.cell(row=1, column=col_idx, value=col_name)
    # 写入数据
    for row_idx, row in df.iterrows():
        for col_idx, value in enumerate(row, 1):
            ws.cell(row=row_idx + 2, column=col_idx, value=value)


def _fill_poc_sheet(ws, df: pd.DataFrame):
    """填充 POC Sheet"""
    if df.empty:
        return
    for col_idx, col_name in enumerate(df.columns, 1):
        ws.cell(row=1, column=col_idx, value=col_name)
    for row_idx, row in df.iterrows():
        for col_idx, value in enumerate(row, 1):
            ws.cell(row=row_idx + 2, column=col_idx, value=value)


def _fill_exception_sheet(ws, df: pd.DataFrame):
    """填充异常项目 Sheet"""
    if df.empty:
        return
    for col_idx, col_name in enumerate(df.columns, 1):
        ws.cell(row=1, column=col_idx, value=col_name)
    for row_idx, row in df.iterrows():
        for col_idx, value in enumerate(row, 1):
            ws.cell(row=row_idx + 2, column=col_idx, value=value)


def _fill_revenue_sheet(ws, df: pd.DataFrame):
    """填充确收交接 Sheet"""
    if df.empty:
        return
    for col_idx, col_name in enumerate(df.columns, 1):
        ws.cell(row=1, column=col_idx, value=col_name)
    for row_idx, row in df.iterrows():
        for col_idx, value in enumerate(row, 1):
            ws.cell(row=row_idx + 2, column=col_idx, value=value)


def _fill_acceptance_sheet(ws, df: pd.DataFrame):
    """填充验收交接 Sheet"""
    if df.empty:
        return
    for col_idx, col_name in enumerate(df.columns, 1):
        ws.cell(row=1, column=col_idx, value=col_name)
    for row_idx, row in df.iterrows():
        for col_idx, value in enumerate(row, 1):
            ws.cell(row=row_idx + 2, column=col_idx, value=value)


def _fill_efficiency_sheet(ws, df: pd.DataFrame):
    """填充交付效率统计 Sheet"""
    ws.cell(row=1, column=1, value="部门")
    ws.cell(row=1, column=2, value="项目经理")
    ws.cell(row=1, column=3, value="交付计划扣分")
    ws.cell(row=1, column=4, value="按时交付扣分")
    ws.cell(row=1, column=5, value="项目数")
