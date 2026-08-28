"""确收月报生成器

生成 10 Sheet 的确收月报 Excel 文件。
"""

import pandas as pd
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path.home() / ".openclaw" / "data" / "reports"


def generate_revenue_report(
    month: str,
    budget_df: pd.DataFrame,
    actual_df: pd.DataFrame,
    contract_df: pd.DataFrame,
    output_dir: Optional[str] = None
) -> str:
    """生成确收月报

    Args:
        month: 报告月份（YYYYMM）
        budget_df: 预算执行数据
        actual_df: 实际确收数据
        contract_df: 合同台账数据
        output_dir: 输出目录

    Returns:
        生成的 Excel 文件路径
    """
    from openpyxl import Workbook

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    wb.remove(wb.active)

    # 预算执行表
    ws1 = wb.create_sheet("预算执行表")
    _fill_budget_sheet(ws1, budget_df)

    # 差异分析
    ws2 = wb.create_sheet("差异分析")
    _fill_variance_sheet(ws2, budget_df, actual_df)

    # 保存
    output_path = out_dir / f"确收月报-{month}.xlsx"
    wb.save(output_path)
    print(f"确收月报已生成: {output_path}")
    return str(output_path)


def _fill_budget_sheet(ws, df: pd.DataFrame):
    """填充预算执行表"""
    if df.empty:
        return
    for col_idx, col_name in enumerate(df.columns, 1):
        ws.cell(row=1, column=col_idx, value=col_name)
    for row_idx, row in df.iterrows():
        for col_idx, value in enumerate(row, 1):
            ws.cell(row=row_idx + 2, column=col_idx, value=value)


def _fill_variance_sheet(ws, budget_df: pd.DataFrame, actual_df: pd.DataFrame):
    """填充差异分析表"""
    ws.cell(row=1, column=1, value="项目")
    ws.cell(row=1, column=2, value="预算金额")
    ws.cell(row=1, column=3, value="实际金额")
    ws.cell(row=1, column=4, value="差异")
