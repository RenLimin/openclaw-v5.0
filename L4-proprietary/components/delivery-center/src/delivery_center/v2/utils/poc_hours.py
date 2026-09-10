#!/usr/bin/env python3
"""
计算 POC 项目工时合计：从 202606工时填报.xlsx 里按项目求和
"""

import pandas as pd
from pathlib import Path

WORKING_HOURS = Path("/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/202606工时填报.xlsx")


def get_poc_project_hours() -> pd.DataFrame:
    """
    读取工时填报，按项目分组求和，返回:
    - 项目编号 → 工时合计
    """
    # 表头在第三行（0-based index = 2）
    df = pd.read_excel(WORKING_HOURS, header=2)
    df.rename(columns={"行标签": "项目编号", "求和项:登记工时": "工时"}, inplace=True)
    print(f"工时填报总行数: {len(df)}")

    # 按项目编号分组求和
    grouped = df.groupby("项目编号")["工时"].sum().reset_index()
    grouped.columns = ["项目编号", "POC项目工时合计（小时）"]
    print(f"汇总后项目数: {len(grouped)}")

    return grouped


if __name__ == "__main__":
    df = get_poc_project_hours()
    print(df.head())
