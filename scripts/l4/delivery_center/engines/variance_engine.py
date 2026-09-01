"""差异分析引擎

计算预算 vs 实际差异，支持确收月报的差异分析。
基于 OA 合同台账 + WeCom 确收/验收凭证的差异计算。

核心逻辑（已验证 2026-09-01）：
  - 差异 = 预算金额 - 实际确收金额
  - 差异率 = 差异 / 预算金额
  - 分类：正常确收 / 差异确收（当年可消除）/ 提前确收
"""

import pandas as pd
from typing import Optional


def calculate_variance(
    df: pd.DataFrame,
    planned_col: str = "签约金额",
    actual_col: str = "确收金额",
) -> pd.DataFrame:
    """计算差异

    Args:
        df: 输入 DataFrame
        planned_col: 预算/计划列名
        actual_col: 实际列名

    Returns:
        新增 差异、差异率 列
    """
    df = df.copy()

    for col in [planned_col, actual_col]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["差异"] = df[planned_col] - df[actual_col]
    df["差异率"] = df.apply(
        lambda row: row["差异"] / row[planned_col] if row[planned_col] != 0 else 0,
        axis=1,
    )

    matched = (df[actual_col] > 0).sum()
    print(f"  差异计算: {matched}/{len(df)} 行有实际数据")
    return df


def classify_variance(row: pd.Series) -> str:
    """差异分类"""
    variance = row.get("差异", 0)
    if abs(variance) < 0.01:
        return "正常确收"
    elif variance > 0:
        return "差异确收（当年可消除）"
    else:
        return "提前确收"


def add_variance_classification(df: pd.DataFrame) -> pd.DataFrame:
    """添加差异分类列"""
    df = df.copy()
    if "差异" not in df.columns:
        df = calculate_variance(df)
    df["差异分类"] = df.apply(classify_variance, axis=1)
    return df


def calculate_revenue_summary(
    df: pd.DataFrame,
    group_col: str = "合同归档月份",
    planned_col: str = "签约金额",
    actual_col: str = "确收金额",
) -> pd.DataFrame:
    """确收汇总（按月份或其他维度）"""
    df = df.copy()
    for col in [planned_col, actual_col]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if group_col not in df.columns:
        print(f"  ⚠️ 分组列不存在: {group_col}")
        return pd.DataFrame()

    summary = df.groupby(group_col).agg({
        planned_col: "sum",
        actual_col: "sum",
        "合同编号": "nunique",
    }).reset_index()

    summary.columns = [group_col, "预算金额", "实际金额", "合同数"]
    summary["完成率"] = summary.apply(
        lambda row: row["实际金额"] / row["预算金额"] if row["预算金额"] != 0 else 0,
        axis=1,
    )
    summary["差异"] = summary["预算金额"] - summary["实际金额"]

    print(f"  确收汇总: {len(summary)} 个{group_col}")
    return summary


def calculate_acceptance_summary(
    df: pd.DataFrame,
    group_col: str = "项目经理",
) -> pd.DataFrame:
    """验收汇总（按项目经理或其他维度）"""
    if group_col not in df.columns:
        print(f"  ⚠️ 分组列不存在: {group_col}")
        return pd.DataFrame()

    summary = df.groupby(group_col).agg({
        "合同编号": "nunique",
        "voucher_id": "count",
    }).reset_index()

    summary.columns = [group_col, "合同数", "验收次数"]

    # 验收方式分布
    if "验收方式" in df.columns:
        method_dist = df.groupby([group_col, "验收方式"]).size().unstack(fill_value=0)
        summary = summary.merge(method_dist, on=group_col, how="left")

    print(f"  验收汇总: {len(summary)} 个{group_col}")
    return summary


if __name__ == "__main__":
    print("=== 差异分析引擎测试 ===\n")

    test_data = pd.DataFrame([
        {"合同编号": "XSZS001", "签约金额": 100000, "确收金额": 100000, "合同归档月份": "2026-06"},
        {"合同编号": "XSZS002", "签约金额": 200000, "确收金额": 150000, "合同归档月份": "2026-06"},
        {"合同编号": "XSZS003", "签约金额": 300000, "确收金额": 350000, "合同归档月份": "2026-07"},
    ])

    result = add_variance_classification(test_data)
    print("差异分类:")
    for _, row in result.iterrows():
        print(f"  {row['合同编号']}: 预算={row['签约金额']:,.0f} 实际={row['确收金额']:,.0f} "
              f"差异={row['差异']:,.0f} ({row['差异率']:.1%}) → {row['差异分类']}")

    print("\n月度汇总:")
    summary = calculate_revenue_summary(result)
    print(summary.to_string())
