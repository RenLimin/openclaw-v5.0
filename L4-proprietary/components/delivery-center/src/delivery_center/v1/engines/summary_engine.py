"""汇总统计引擎

实现 Pivot 统计逻辑，替代 Excel 中的 Pivot Table。
支持多维度交叉统计。

已验证 2026-09-01。
"""

import pandas as pd
from typing import Optional


def pivot_by_dept_status(df: pd.DataFrame) -> pd.DataFrame:
    """按部门 x 项目状态统计"""
    if "项目经理所属部门" not in df.columns or "项目状态" not in df.columns:
        print("  ⚠️ 缺少必要列")
        return pd.DataFrame()

    pivot = pd.pivot_table(
        df, index="项目经理所属部门", columns="项目状态",
        values="项目编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"  部门x状态 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot


def pivot_by_product(df: pd.DataFrame) -> pd.DataFrame:
    """按产品/服务统计"""
    if "标准产品/服务序号" not in df.columns:
        print("  ⚠️ 缺少列: 标准产品/服务序号")
        return pd.DataFrame()

    pivot = pd.pivot_table(
        df, index="标准产品/服务序号", columns="项目类型(概览)",
        values="项目编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"  产品x类型 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot


def pivot_exception_by_dept(df: pd.DataFrame) -> pd.DataFrame:
    """按部门统计异常项目"""
    if "状态" not in df.columns:
        print("  ⚠️ 缺少列: 状态")
        return pd.DataFrame()

    pivot = pd.pivot_table(
        df, index="状态", columns="异常影响情况",
        values="销售合同编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"  异常x影响 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot


def pivot_poc_by_dept(df: pd.DataFrame) -> pd.DataFrame:
    """按部门统计 POC&提前实施"""
    if "项目经理所属部门" not in df.columns:
        print("  ⚠️ 缺少列: 项目经理所属部门")
        return pd.DataFrame()

    pivot = pd.pivot_table(
        df, index="项目经理所属部门", columns="项目类型(概览)",
        values="项目编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"  POCx部门 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot


def pivot_revenue_by_dept(df: pd.DataFrame) -> pd.DataFrame:
    """按部门统计确收情况"""
    required = ["部门", "合同编号"]
    for col in required:
        if col not in df.columns:
            print(f"  ⚠️ 缺少列: {col}")
            return pd.DataFrame()

    agg_dict = {"合同编号": "nunique"}
    if "签约金额" in df.columns:
        agg_dict["签约金额"] = "sum"
    if "确收金额" in df.columns:
        agg_dict["确收金额"] = "sum"

    summary = df.groupby("部门").agg(agg_dict).reset_index()
    summary = summary.rename(columns={"合同编号": "合同数"})

    if "签约金额" in summary.columns and "确收金额" in summary.columns:
        summary["完成率"] = summary.apply(
            lambda row: row["确收金额"] / row["签约金额"] if row["签约金额"] != 0 else 0,
            axis=1,
        )

    summary = summary.sort_values("合同数", ascending=False)
    print(f"  确收x部门: {len(summary)} 个部门")
    return summary


def pivot_workhour_by_project(df: pd.DataFrame) -> pd.DataFrame:
    """按项目统计工时"""
    if "工作项" not in df.columns:
        print("  ⚠️ 缺少列: 工作项")
        return pd.DataFrame()

    agg_dict = {"总工时": "sum"}
    if "迁移工时" in df.columns:
        agg_dict["迁移工时"] = "sum"

    summary = df.groupby("工作项").agg(agg_dict).reset_index()
    summary = summary.sort_values("总工时", ascending=False)

    print(f"  工时x项目: {len(summary)} 个工作项")
    return summary


if __name__ == "__main__":
    print("=== 汇总统计引擎测试 ===\n")

    # 测试确收x部门
    test_data = pd.DataFrame([
        {"部门": "北区", "合同编号": "XSZS001", "签约金额": 100000, "确收金额": 100000},
        {"部门": "北区", "合同编号": "XSZS002", "签约金额": 200000, "确收金额": 150000},
        {"部门": "南区", "合同编号": "XSZS003", "签约金额": 300000, "确收金额": 350000},
    ])

    print("确收x部门:")
    result = pivot_revenue_by_dept(test_data)
    print(result.to_string())

    # 测试工时x项目
    wh_data = pd.DataFrame([
        {"工作项": "项目A", "总工时": 100, "迁移工时": 80},
        {"工作项": "项目B", "总工时": 200, "迁移工时": 150},
    ])

    print("\n工时x项目:")
    wh_result = pivot_workhour_by_project(wh_data)
    print(wh_result.to_string())
