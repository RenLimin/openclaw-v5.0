"""汇总统计引擎

实现 Pivot 统计逻辑，替代 Excel 中的 Pivot Table。
"""

import pandas as pd


def pivot_by_dept_status(df: pd.DataFrame) -> pd.DataFrame:
    """按部门 x 项目状态统计"""
    pivot = pd.pivot_table(
        df, index="项目经理所属部门", columns="项目状态",
        values="项目编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"部门x状态 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot


def pivot_by_product(df: pd.DataFrame) -> pd.DataFrame:
    """按产品/服务统计"""
    pivot = pd.pivot_table(
        df, index="标准产品/服务序号", columns="项目类型(概览)",
        values="项目编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"产品x类型 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot


def pivot_exception_by_dept(df: pd.DataFrame) -> pd.DataFrame:
    """按部门统计异常项目"""
    pivot = pd.pivot_table(
        df, index="状态", columns="异常影响情况",
        values="销售合同编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"异常x影响 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot


def pivot_poc_by_dept(df: pd.DataFrame) -> pd.DataFrame:
    """按部门统计 POC&提前实施"""
    pivot = pd.pivot_table(
        df, index="项目经理所属部门", columns="项目类型(概览)",
        values="项目编号", aggfunc="nunique", fill_value=0,
        margins=True, margins_name="合计"
    )
    print(f"POCx部门 Pivot: {pivot.shape[0]} 行 x {pivot.shape[1]} 列")
    return pivot
