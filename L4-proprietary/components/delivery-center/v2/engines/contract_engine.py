"""
交付月报 V2 — 合同信息引擎

从 OA 销售合同台账提取标准化合同信息，关联到 ONES 履约项。
输出：合同号/金额/签订日期/服务期限 等标准化字段。

数据源：
  - OA 销售合同信息查询台账（64 列），主键：合同编号！
  - ONES 履约项（销售合同编号），N:1 关联

关联规则（复用 v1 join_engine 经验）：
  - 合同编号校准：去除 & 后内容 + 统一大写
  - 左连接：ONES 为主表，OA 为补充
"""

import pandas as pd
from pathlib import Path
from typing import Optional


# ============================================================
# 工具函数
# ============================================================

def calibrate_contract_no(contract_no) -> str:
    """
    合同编号校准：去除 & 后面内容，统一大写，去空格

    沿用 v1 join_engine 逻辑（已验证）。
    """
    if not isinstance(contract_no, str):
        return ""
    contract_no = contract_no.strip()
    if not contract_no:
        return ""
    if "&" in contract_no:
        contract_no = contract_no.split("&")[0]
    return contract_no.upper()


def _parse_date(s):
    """解析日期，返回 datetime 或 NaT"""
    if not s or pd.isna(s):
        return pd.NaT
    try:
        return pd.to_datetime(str(s)[:10], errors="coerce")
    except (ValueError, TypeError):
        return pd.NaT


# ============================================================
# 核心方法 1：加载并清洗 OA 合同台账
# ============================================================

def load_oa_contracts(oa_path: Optional[Path] = None) -> pd.DataFrame:
    """
    加载 OA 销售合同信息查询台账，输出标准化 DataFrame。

    清洗规则：
      - 列名统一：合同编号！→ 合同编号（用于 JOIN）
      - 合同编号校准（去 & + 大写）
      - 日期字段统一为 datetime
      - 金额字段转为数值型

    Args:
        oa_path: OA 合同 Excel 路径。None 时返回空 DataFrame（骨架模式）。

    Returns:
        DataFrame，至少包含：合同编号、签约金额、合同归档日期、
        合同起始日期、合同结束日期、客户名称、责任销售、责任销售所属部门
    """
    if oa_path is None or not Path(oa_path).exists():
        # 骨架模式：返回空结构，列定义与规格一致
        empty_cols = [
            "合同编号", "原始合同编号", "签约金额", "合同归档日期",
            "合同起始日期", "合同结束日期", "客户名称",
            "责任销售", "责任销售所属部门", "合同类型", "产品分类"
        ]
        return pd.DataFrame(columns=empty_cols)

    df = pd.read_excel(oa_path, dtype=str)

    # 列名统一：合同编号！→ 合同编号（主键列，原始列名末尾有感叹号）
    col_rename = {}
    for col in df.columns:
        if col.endswith("！") and "合同编号" in col:
            col_rename[col] = "合同编号"
        elif col == "签约金额（元）":
            col_rename[col] = "签约金额"
        elif col == "客户名称（浏览框）":
            col_rename[col] = "客户名称浏览框"
    df = df.rename(columns=col_rename)

    # 保存原始合同编号（用于展示）
    if "合同编号" in df.columns:
        df["原始合同编号"] = df["合同编号"]
        df["合同编号"] = df["合同编号"].apply(calibrate_contract_no)

    # 金额转数值
    if "签约金额" in df.columns:
        df["签约金额"] = pd.to_numeric(df["签约金额"], errors="coerce")

    # 日期字段统一
    date_cols = ["合同归档日期", "合同起始日期", "合同结束日期"]
    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].apply(_parse_date)

    # 去重：同一合同编号取第一条（OA 可能有重复行）
    if "合同编号" in df.columns:
        df = df.drop_duplicates(subset=["合同编号"], keep="first")
        df = df.reset_index(drop=True)

    return df


# ============================================================
# 核心方法 2：关联合同信息到履约项
# ============================================================

def join_contract_info(
    df_projects: pd.DataFrame,
    df_contracts: pd.DataFrame,
    project_contract_col: str = "销售合同编号",
) -> pd.DataFrame:
    """
    将 OA 合同信息关联到 ONES 履约项 DataFrame。

    关联逻辑：
      - 左连接：df_projects 为主，df_contracts 为补充
      - 关联键：项目侧 sales_contract_col → 合同侧 合同编号
      - 关联前双方合同编号都做校准

    Args:
        df_projects: 项目/履约项 DataFrame（ONES 签约或 POC）
        df_contracts: OA 合同 DataFrame（来自 load_oa_contracts）
        project_contract_col: 项目表中合同编号列名

    Returns:
        补充了合同字段的 DataFrame（新增列带 oa_ 前缀，避免冲突）
    """
    if df_contracts.empty:
        # 合同数据为空时，补空列保证结构一致
        for col in ["oa_签约金额", "oa_合同归档日期", "oa_合同起始日期",
                     "oa_合同结束日期", "oa_客户名称", "oa_责任销售"]:
            df_projects[col] = ""
        return df_projects

    df = df_projects.copy()

    # 项目侧合同编号校准（保存原始值，新增校准列用于 JOIN）
    df["_contract_key"] = df[project_contract_col].apply(calibrate_contract_no)

    # 合同侧选取需要的列
    contract_cols = [
        "合同编号", "签约金额", "合同归档日期", "合同起始日期",
        "合同结束日期", "客户名称", "责任销售", "责任销售所属部门",
        "合同类型", "产品分类"
    ]
    available_cols = [c for c in contract_cols if c in df_contracts.columns]
    df_oa_subset = df_contracts[available_cols].copy()

    # 重命名：加 oa_ 前缀避免与 ONES 列冲突
    rename_map = {c: f"oa_{c}" for c in available_cols if c != "合同编号"}
    df_oa_subset = df_oa_subset.rename(columns=rename_map)

    # 左连接
    df = df.merge(
        df_oa_subset,
        left_on="_contract_key",
        right_on="合同编号",
        how="left"
    )

    # 清理临时列和冗余列
    if "合同编号" in df.columns:
        df.drop(columns=["合同编号"], inplace=True)
    df.drop(columns=["_contract_key"], inplace=True)

    return df


# ============================================================
# 核心方法 3：合同信息统计汇总
# ============================================================

def summarize_contracts(df_projects: pd.DataFrame) -> pd.DataFrame:
    """
    按合同维度汇总统计（供签约统计/异常统计等使用）。

    统计维度：
      - 合同归档年度 × 履约项统计状态 → 合同数 + 金额合计
      - 每合同的履约项数量

    Args:
        df_projects: 已关联合同信息的项目 DataFrame
                     （需包含：销售合同编号、合同归档年度、履约项统计状态、oa_签约金额）

    Returns:
        DataFrame，每行一个合同，含汇总信息
    """
    if df_projects.empty:
        return pd.DataFrame()

    df = df_projects.copy()

    # 合同编号校准键
    df["_contract_key"] = df["销售合同编号"].apply(calibrate_contract_no)

    # 按合同分组汇总
    agg_dict = {
        "销售合同编号": "count",  # 履约项数量
        "所属项目": "nunique",    # 项目数
    }

    # 如果有金额列，汇总金额
    amount_col = "oa_签约金额" if "oa_签约金额" in df.columns else None
    if amount_col:
        agg_dict[amount_col] = "first"  # 同合同金额相同，取第一个

    # 如果有状态列，取第一个状态（用于透视）
    status_col = "履约项统计状态（即，财报-交付/确收状态）"
    if status_col in df.columns:
        agg_dict[status_col] = "first"

    df_summary = df.groupby("_contract_key").agg(agg_dict).reset_index()
    df_summary = df_summary.rename(columns={
        "销售合同编号": "履约项数量",
        "所属项目": "项目数量",
        "_contract_key": "合同编号",
    })

    return df_summary


# ============================================================
# 便捷入口：给 DataFrame 加合同信息列（一体化方法）
# ============================================================

def add_contract_columns(
    df: pd.DataFrame,
    oa_path: Optional[Path] = None,
    df_contracts: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    一体化方法：加载 OA 合同 + 关联到 DataFrame + 返回完整列。

    使用方式：
      df = add_contract_columns(df_sign, oa_path=Path("oa_contracts.xlsx"))
      或
      df = add_contract_columns(df_sign, df_contracts=preloaded_df)

    Args:
        df: 项目 DataFrame
        oa_path: OA 合同文件路径（与 df_contracts 二选一）
        df_contracts: 已加载的 OA 合同 DataFrame（与 oa_path 二选一）

    Returns:
        补充了 oa_* 合同字段的 DataFrame
    """
    if df_contracts is None:
        df_contracts = load_oa_contracts(oa_path)

    return join_contract_info(df, df_contracts)
