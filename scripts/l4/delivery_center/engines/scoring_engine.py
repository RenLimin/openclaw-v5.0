"""考核扣分计算引擎

计算交付计划准确率和按时交付率的考核扣分。
支持按部门/项目经理汇总。

扣分规则（已验证 2026-09-01）：
  - 交付计划准确率：
    - 方向=一致 或 当期未填写 → 0 分
    - 跨月=不统计 → 0 分
    - 跨月=否 且 |差异| < 15天 → 0.5 分
    - 跨月=是 或 |差异| ≥ 15天 → 1 分
  - 按时交付率：同上逻辑，使用按时交付字段
"""

import pandas as pd
from typing import Union


def _safe_float(val, default: float = 0.0) -> float:
    """安全转换为 float"""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def calculate_accuracy_score(df: pd.DataFrame) -> pd.DataFrame:
    """计算交付计划准确率考核扣分

    字段：交付计划方向、交付计划跨月、交付计划差异
    """
    def _score(row) -> float:
        direction = str(row.get("交付计划方向", "")).strip()
        cross_month = str(row.get("交付计划跨月", "")).strip()
        diff = _safe_float(row.get("交付计划差异", 0))

        if direction in ("一致", "当期未填写", ""):
            return 0.0
        if cross_month == "不统计":
            return 0.0
        if cross_month == "否" and abs(diff) < 15:
            return 0.5
        return 1.0

    df = df.copy()
    df["交付计划扣分"] = df.apply(_score, axis=1)
    total = df["交付计划扣分"].sum()
    print(f"  交付计划扣分: 总计 {total:.1f} 分（{len(df)} 个项目）")
    return df


def calculate_timeliness_score(df: pd.DataFrame) -> pd.DataFrame:
    """计算按时交付率考核扣分

    字段：按时交付方向、按时交付跨月、按时交付差异
    """
    def _score(row) -> float:
        direction = str(row.get("按时交付方向", "")).strip()
        cross_month = str(row.get("按时交付跨月", "")).strip()
        diff = _safe_float(row.get("按时交付差异", 0))

        if direction in ("一致", "当期未填写", ""):
            return 0.0
        if cross_month == "不统计":
            return 0.0
        if cross_month == "否" and abs(diff) < 15:
            return 0.5
        return 1.0

    df = df.copy()
    df["按时交付扣分"] = df.apply(_score, axis=1)
    total = df["按时交付扣分"].sum()
    print(f"  按时交付扣分: 总计 {total:.1f} 分（{len(df)} 个项目）")
    return df


def calculate_total_score(df: pd.DataFrame) -> pd.DataFrame:
    """计算总扣分"""
    df = df.copy()
    if "交付计划扣分" not in df.columns:
        df = calculate_accuracy_score(df)
    if "按时交付扣分" not in df.columns:
        df = calculate_timeliness_score(df)
    df["总扣分"] = df["交付计划扣分"] + df["按时交付扣分"]
    return df


def calculate_department_summary(df: pd.DataFrame) -> pd.DataFrame:
    """按部门汇总考核扣分"""
    required_cols = ["项目经理所属部门", "项目经理"]
    for col in required_cols:
        if col not in df.columns:
            print(f"  ⚠️ 缺少列: {col}")
            return pd.DataFrame()

    agg_dict = {"项目编号": "count"}
    if "交付计划扣分" in df.columns:
        agg_dict["交付计划扣分"] = "sum"
    if "按时交付扣分" in df.columns:
        agg_dict["按时交付扣分"] = "sum"
    if "总扣分" in df.columns:
        agg_dict["总扣分"] = "sum"

    summary = df.groupby(required_cols).agg(agg_dict).reset_index()
    summary = summary.rename(columns={"项目编号": "项目数"})

    if "总扣分" in summary.columns:
        summary = summary.sort_values("总扣分", ascending=False)

    print(f"  部门汇总: {len(summary)} 个项目经理")
    return summary


def calculate_individual_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    """生成个人考核卡"""
    if "总扣分" not in df.columns:
        df = calculate_total_score(df)

    card = df.groupby(["项目经理所属部门", "项目经理"]).agg({
        "交付计划扣分": "sum",
        "按时交付扣分": "sum",
        "总扣分": "sum",
        "项目编号": "count"
    }).reset_index()

    card.columns = ["部门", "项目经理", "交付计划扣分", "按时交付扣分", "总扣分", "项目数"]
    card = card.sort_values(["部门", "总扣分"], ascending=[True, False])

    print(f"  个人考核卡: {len(card)} 人")
    return card


if __name__ == "__main__":
    print("=== 考核计算引擎测试 ===\n")

    test_data = pd.DataFrame([
        {"项目经理所属部门": "北区", "项目经理": "张三", "项目编号": "P001",
         "交付计划方向": "一致", "交付计划跨月": "否", "交付计划差异": 0,
         "按时交付方向": "提前", "按时交付跨月": "否", "按时交付差异": 10},
        {"项目经理所属部门": "北区", "项目经理": "李四", "项目编号": "P002",
         "交付计划方向": "提前", "交付计划跨月": "否", "交付计划差异": 20,
         "按时交付方向": "一致", "按时交付跨月": "否", "按时交付差异": 0},
        {"项目经理所属部门": "南区", "项目经理": "王五", "项目编号": "P003",
         "交付计划方向": "滞后", "交付计划跨月": "是", "交付计划差异": 30,
         "按时交付方向": "当期未填写", "按时交付跨月": "否", "按时交付差异": 0},
    ])

    result = calculate_total_score(test_data)
    print("\n个人考核卡:")
    card = calculate_individual_scorecard(result)
    print(card.to_string())
