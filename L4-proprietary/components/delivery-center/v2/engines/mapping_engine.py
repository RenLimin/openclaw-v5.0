"""
交付月报 V2 — 映射引擎（项目经理/部门/中心/销售团队映射）

复用旧版资产 legend_pm_dept.json 等映射配置。
"""

import json
from pathlib import Path
import pandas as pd


CONFIG_DIR = Path(__file__).parent.parent.parent / "delivery_center" / "config"


def load_pm_dept_map() -> dict:
    """加载项目经理 → 部门映射"""
    with open(CONFIG_DIR / "legend_pm_dept.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_team_map() -> dict:
    """加载销售团队映射"""
    try:
        with open(CONFIG_DIR / "legend_team.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def add_mapping_columns(df: pd.DataFrame) -> pd.DataFrame:
    """给 DataFrame 加映射相关列（列 77-79）"""
    pm_dept_map = load_pm_dept_map()

    # 列 77：项目经理 = 负责人（图例映射后出项目经理名称）
    # 这里简化：负责人就是项目经理（图例匹配后显示规范化名称）
    df["项目经理"] = df["负责人"].fillna("")

    # 列 78：项目经理所属部门
    df["项目经理所属部门"] = df["负责人"].map(
        lambda x: pm_dept_map.get(str(x), "未匹配") if pd.notna(x) else ""
    )

    # 列 79：销售团队-统计（从责任销售所属团队映射）
    team_map = load_team_map()
    if team_map:
        df["销售团队-统计"] = df["责任销售所属团队"].map(
            lambda x: team_map.get(str(x), str(x)) if pd.notna(x) else ""
        )
    else:
        df["销售团队-统计"] = df["责任销售所属团队"].fillna("")

    return df


def add_simple_computed_columns(df: pd.DataFrame) -> pd.DataFrame:
    """加简单计算列（列 41-44）"""
    # 列 41：项目编号（从 所属项目 或 ID 推导，先按参考模板：项目编号 = 所属项目 关联出来）
    # 实际值：参考报表里这列有值，我们先从 ONES 数据找
    # 简化处理：项目编号 = 所属项目（先这么用，验证后调整）
    df["项目编号"] = df["所属项目"].fillna("")

    # 列 42：统计项目编号
    df["统计项目编号"] = df["销售合同编号"].fillna("") + " - " + df["所属项目"].fillna("")

    # 列 43：统计合同编号
    df["统计合同编号"] = df["销售合同编号"].fillna("")

    # 列 44：合同归档年度
    def _extract_year(s):
        if not s or pd.isna(s):
            return ""
        s = str(s)
        if len(s) >= 4 and s[:4].isdigit():
            return s[:4]
        return ""

    df["合同归档年度"] = df["合同归档日期"].apply(_extract_year)

    return df


def add_exception_lookup_columns(df_sign: pd.DataFrame, df_exc: pd.DataFrame) -> pd.DataFrame:
    """
    加异常关联列（列 80-83）
    用销售合同编号关联异常项目表，VLOOKUP 取数
    """
    # 异常表中按销售合同编号去重，取第一个
    exc_lookup = {}
    for _, row in df_exc.iterrows():
        contract_id = str(row.get("销售合同编号", ""))
        if contract_id and contract_id not in exc_lookup:
            exc_lookup[contract_id] = row

    def _lookup(col_name, default_val=""):
        def _f(contract_id):
            if not contract_id or pd.isna(contract_id):
                return default_val
            cid = str(contract_id)
            if cid in exc_lookup:
                val = exc_lookup[cid].get(col_name, default_val)
                return val if pd.notna(val) else default_val
            return default_val
        return _f

    # 列 80：异常项目对比（是否有异常，1/0 或文本）
    df_sign["异常项目对比"] = df_sign["销售合同编号"].apply(
        lambda x: "有" if str(x) in exc_lookup else ""
    )

    # 列 81：异常处置状态
    df_sign["异常处置状态"] = df_sign["销售合同编号"].apply(
        _lookup("异常处置状态", "")
    )

    # 列 82：异常影响情况
    df_sign["异常影响情况"] = df_sign["销售合同编号"].apply(
        _lookup("异常影响情况", "")
    )

    # 列 83：交付说明
    df_sign["交付说明"] = df_sign["销售合同编号"].apply(
        _lookup("交付说明", "")
    )

    return df_sign
