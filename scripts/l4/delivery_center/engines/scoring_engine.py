"""考核扣分计算引擎

计算交付计划准确率和按时交付率的考核扣分。
"""

import pandas as pd


def calculate_accuracy_score(df: pd.DataFrame) -> pd.DataFrame:
    """计算交付计划准确率考核扣分"""
    def _score(row):
        direction = row.get("交付计划方向", "")
        cross_month = row.get("交付计划跨月", "")
        diff = row.get("交付计划差异", 0)

        if direction in ("一致", "当期未填写") or cross_month == "不统计":
            return 0
        if cross_month == "否" and abs(diff) < 15:
            return 0.5
        return 1

    df["交付计划扣分"] = df.apply(_score, axis=1)
    print("交付计划扣分计算完成")
    return df


def calculate_timeliness_score(df: pd.DataFrame) -> pd.DataFrame:
    """计算按时交付率考核扣分"""
    def _score(row):
        direction = row.get("按时交付方向", "")
        cross_month = row.get("按时交付跨月", "")
        diff = row.get("按时交付差异", 0)

        if direction in ("一致", "当期未填写") or cross_month == "不统计":
            return 0
        if cross_month == "否" and abs(diff) < 15:
            return 0.5
        return 1

    df["按时交付扣分"] = df.apply(_score, axis=1)
    print("按时交付扣分计算完成")
    return df


def calculate_department_summary(df: pd.DataFrame) -> pd.DataFrame:
    """按部门汇总考核扣分"""
    summary = df.groupby(["项目经理所属部门", "项目经理"]).agg({
        "交付计划扣分": "sum",
        "按时交付扣分": "sum",
        "项目编号": "count"
    }).reset_index()

    summary.columns = ["部门", "项目经理", "交付计划扣分", "按时交付扣分", "项目数"]
    print(f"部门汇总完成: {len(summary)} 个项目经理")
    return summary
