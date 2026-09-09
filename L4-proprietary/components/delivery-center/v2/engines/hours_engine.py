"""
交付月报 V2 — POC 工时引擎

从工时填报数据中按项目/合同汇总工时，输出工时统计 + 人天换算。

数据源：
  - 工时填报 Excel（2 Sheet：按项目汇总 + 工时填报情况查询）
  - 关联键：合同编号 / 项目名称

核心规则（来自 spec-calculation-logic §七 + utils/poc_hours.py）：
  - POC 项目工时合计：按合同编号求和，写入 POC 明细最后一列
  - 人天换算：默认 8 小时/天（可配置）
  - POC 统计右侧 Pivot：所属产线 × 项目经理所属部门，值=工时合计
"""

import pandas as pd
from pathlib import Path
from typing import Optional


# 默认人天换算系数（小时/天）
DEFAULT_HOURS_PER_DAY = 8.0


# ============================================================
# 核心方法 1：加载工时填报明细
# ============================================================

def load_workhour_detail(
    excel_path: Optional[Path] = None,
    sheet_name: str = "工时填报情况查询",
    header_row: int = 0,
) -> pd.DataFrame:
    """
    加载工时填报明细 Sheet。

    Args:
        excel_path: 工时填报 Excel 路径。None 时返回空结构。
        sheet_name: 明细 Sheet 名，默认"工时填报情况查询"
        header_row: 表头所在行（0-based）

    Returns:
        DataFrame，原始工时明细（23 列）
    """
    if excel_path is None or not Path(excel_path).exists():
        empty_cols = [
            "ID", "项目名称", "合同编号", "登记工时",
            "开始时间", "结束时间", "填报人", "审批状态"
        ]
        return pd.DataFrame(columns=empty_cols)

    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row, dtype=str)
    print(f"📊 工时填报明细: {len(df)} 行 × {len(df)} 列")
    return df


def load_workhour_pivot(
    excel_path: Optional[Path] = None,
    sheet_name: str = "按项目汇总",
    header_row: int = 2,
) -> pd.DataFrame:
    """
    加载"按项目汇总"Sheet（已做好 pivot 的汇总表）。

    这个 Sheet 是 Excel Pivot 格式：行标签=项目名，值=登记工时求和。
    直接读取并规范化列名。

    Args:
        excel_path: 工时填报 Excel 路径
        sheet_name: pivot 汇总 Sheet 名
        header_row: 表头行（0-based，通常是第 3 行即 index=2）

    Returns:
        DataFrame，两列：项目编号 / 工时合计
    """
    if excel_path is None or not Path(excel_path).exists():
        return pd.DataFrame(columns=["项目编号", "工时合计"])

    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row)

    # 规范化列名（兼容不同模板的列名差异）
    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if "行标签" in str(col) or "项目" in str(col):
            col_map[col] = "项目编号"
        elif "求和" in str(col) or "工时" in str(col):
            col_map[col] = "工时合计"

    df = df.rename(columns=col_map)

    # 确保有两列
    if "项目编号" not in df.columns or "工时合计" not in df.columns:
        print(f"⚠️ 工时 pivot sheet 列名不匹配: {list(df.columns)}")
        return pd.DataFrame(columns=["项目编号", "工时合计"])

    # 去掉空行和总计行
    df = df[df["项目编号"].notna()]
    df = df[~df["项目编号"].astype(str).str.contains("总计|合计|Grand Total", na=False)]

    # 工时转数值
    df["工时合计"] = pd.to_numeric(df["工时合计"], errors="coerce").fillna(0)

    df = df.reset_index(drop=True)
    print(f"📊 工时按项目汇总: {len(df)} 个项目")
    return df


# ============================================================
# 核心方法 2：按项目/合同分组汇总工时
# ============================================================

def aggregate_by_project(df_detail: pd.DataFrame) -> pd.DataFrame:
    """
    从工时明细按项目编号（项目名称）分组汇总工时。

    效果等同于"按项目汇总"Sheet，但从明细重新计算，更准确。

    Args:
        df_detail: 工时明细 DataFrame（需含 项目名称/合同编号/登记工时 列）

    Returns:
        DataFrame，列：项目编号、工时合计（小时）
    """
    if df_detail.empty:
        return pd.DataFrame(columns=["项目编号", "工时合计"])

    df = df_detail.copy()

    # 确定项目列
    project_col = None
    for candidate in ["项目名称", "项目编号", "所属项目"]:
        if candidate in df.columns:
            project_col = candidate
            break

    # 确定工时列
    hours_col = None
    for candidate in ["登记工时", "工时", "工时合计"]:
        if candidate in df.columns:
            hours_col = candidate
            break

    if project_col is None or hours_col is None:
        print(f"⚠️ 工时明细缺少必要列: {list(df.columns)}")
        return pd.DataFrame(columns=["项目编号", "工时合计"])

    # 工时转数值
    df["_hours_num"] = pd.to_numeric(df[hours_col], errors="coerce").fillna(0)

    # 按项目分组求和
    result = df.groupby(project_col)["_hours_num"].sum().reset_index()
    result.columns = ["项目编号", "工时合计"]
    result = result.sort_values("工时合计", ascending=False).reset_index(drop=True)

    return result


def aggregate_by_contract(df_detail: pd.DataFrame) -> pd.DataFrame:
    """
    从工时明细按合同编号分组汇总工时。

    用于 POC 明细的"POC项目工时合计"列（spec §七 工时关联规则）。

    Args:
        df_detail: 工时明细 DataFrame（需含 合同编号/登记工时 列）

    Returns:
        DataFrame，列：合同编号、工时合计（小时）
    """
    if df_detail.empty:
        return pd.DataFrame(columns=["合同编号", "工时合计"])

    df = df_detail.copy()

    # 确定合同列
    contract_col = None
    for candidate in ["合同编号", "销售合同编号"]:
        if candidate in df.columns:
            contract_col = candidate
            break

    hours_col = None
    for candidate in ["登记工时", "工时", "工时合计"]:
        if candidate in df.columns:
            hours_col = candidate
            break

    if contract_col is None or hours_col is None:
        print(f"⚠️ 工时明细缺少合同/工时列: {list(df.columns)}")
        return pd.DataFrame(columns=["合同编号", "工时合计"])

    # 工时转数值
    df["_hours_num"] = pd.to_numeric(df[hours_col], errors="coerce").fillna(0)

    # 按合同编号分组求和
    result = df.groupby(contract_col)["_hours_num"].sum().reset_index()
    result.columns = ["合同编号", "工时合计"]
    result = result.sort_values("工时合计", ascending=False).reset_index(drop=True)

    return result


# ============================================================
# 核心方法 3：人天换算 + 写入 POC 明细
# ============================================================

def hours_to_person_days(
    hours: float,
    hours_per_day: float = DEFAULT_HOURS_PER_DAY,
) -> float:
    """
    工时（小时） → 人天换算。

    默认 8 小时/天，保留 2 位小数。

    Args:
        hours: 工时（小时）
        hours_per_day: 每天工时数，默认 8

    Returns:
        人天（float，保留 2 位小数）
    """
    if pd.isna(hours) or hours is None:
        return 0.0
    return round(float(hours) / hours_per_day, 2)


def add_poc_hours_column(
    df_poc: pd.DataFrame,
    df_hours_by_contract: pd.DataFrame,
    hours_col_name: str = "POC项目工时合计（小时）",
) -> pd.DataFrame:
    """
    将工时合计写入 POC 明细 DataFrame（最后一列）。

    对应 spec §七：POC 项目工时合计从工时填报明细按合同编号求和。
    对应 spec-report-structure §2.2 第 84 列。

    Args:
        df_poc: POC 明细 DataFrame（需含 销售合同编号 列）
        df_hours_by_contract: 按合同汇总的工时 DataFrame（合同编号 + 工时合计）
        hours_col_name: 新列名，默认"POC项目工时合计（小时）"

    Returns:
        增加了工时列的 POC DataFrame
    """
    df = df_poc.copy()

    if df_hours_by_contract.empty or "合同编号" not in df_hours_by_contract.columns:
        df[hours_col_name] = 0.0
        return df

    # 构建查找字典
    hours_map = dict(zip(
        df_hours_by_contract["合同编号"].astype(str),
        df_hours_by_contract["工时合计"]
    ))

    # 用销售合同编号匹配（先校准，再查）
    from contract_engine import calibrate_contract_no

    def _lookup(contract_no):
        if pd.isna(contract_no) or not contract_no:
            return 0.0
        key = calibrate_contract_no(str(contract_no))
        return hours_map.get(key, 0.0)

    df[hours_col_name] = df["销售合同编号"].apply(_lookup)

    return df


def add_person_days_column(
    df_poc: pd.DataFrame,
    hours_col: str = "POC项目工时合计（小时）",
    days_col: str = "POC项目工时合计（人天）",
    hours_per_day: float = DEFAULT_HOURS_PER_DAY,
) -> pd.DataFrame:
    """
    给 POC DataFrame 加人天换算列。

    Args:
        df_poc: POC 明细 DataFrame
        hours_col: 工时（小时）列名
        days_col: 人天列名
        hours_per_day: 每天工时数

    Returns:
        增加了人天列的 DataFrame
    """
    df = df_poc.copy()

    if hours_col not in df.columns:
        df[days_col] = 0.0
        return df

    df[days_col] = df[hours_col].apply(
        lambda x: hours_to_person_days(x, hours_per_day)
    )

    return df


# ============================================================
# 便捷入口：一体化加载 + 汇总
# ============================================================

def get_poc_project_hours_by_contract(
    excel_path: Optional[Path] = None,
) -> pd.DataFrame:
    """
    便捷函数：加载工时 Excel → 按合同汇总 → 返回结果。

    替换 utils/poc_hours.py 的 get_poc_project_hours()，
    但输出按合同编号而不是按项目编号（更准确，因为 POC 关联用合同号）。

    Args:
        excel_path: 工时填报 Excel 路径

    Returns:
        DataFrame，列：合同编号、POC项目工时合计（小时）
    """
    df_detail = load_workhour_detail(excel_path)
    if df_detail.empty:
        return pd.DataFrame(columns=["合同编号", "POC项目工时合计（小时）"])

    result = aggregate_by_contract(df_detail)
    result = result.rename(columns={"工时合计": "POC项目工时合计（小时）"})
    return result
