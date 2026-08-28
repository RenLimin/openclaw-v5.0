"""差异分析引擎

计算预算 vs 实际差异，支持确收月报的差异分析。
"""

import pandas as pd


def calculate_variance(df: pd.DataFrame, planned_col: str, actual_col: str) -> pd.DataFrame:
    """计算差异"""
    df["差异"] = df[planned_col] - df[actual_col]
    df["差异率"] = df.apply(
        lambda row: row["差异"] / row[planned_col] if row[planned_col] != 0 else 0, axis=1
    )
    print("差异计算完成")
    return df


def classify_variance(row: pd.Series) -> str:
    """差异分类"""
    variance = row.get("差异", 0)
    if variance == 0:
        return "正常确收"
    elif variance > 0:
        return "差异确收（当年可消除）"
    else:
        return "提前确收"


def calculate_revenue_summary(df: pd.DataFrame) -> pd.DataFrame:
    """确收汇总"""
    summary = df.groupby("合同归档月份").agg({
        "预算金额": "sum",
        "实际金额": "sum",
        "合同编号": "nunique"
    }).reset_index()

    summary["完成率"] = summary.apply(
        lambda row: row["实际金额"] / row["预算金额"] if row["预算金额"] != 0 else 0, axis=1
    )
    print(f"确收汇总完成: {len(summary)} 个月")
    return summary
