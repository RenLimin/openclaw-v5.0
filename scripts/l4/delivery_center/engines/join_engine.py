"""关联查询引擎

将 Excel 中的 VLOOKUP 逻辑转换为 pandas merge 操作。
支持多数据源关联：ONES <-> OA <-> 企业微信 <-> 工时 <-> 图例配置。
"""

import pandas as pd
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_config(name: str) -> dict:
    """加载 JSON 配置文件"""
    import json
    config_path = CONFIG_DIR / f"{name}.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def calibrate_contract_no(contract_no: str) -> str:
    """合同编号校准：去除 & 后面的内容"""
    if isinstance(contract_no, str) and "&" in contract_no:
        return contract_no.split("&")[0]
    return contract_no


def join_contract_oa(
    ones_df: pd.DataFrame,
    oa_df: pd.DataFrame,
    ones_key: str = "合同编号（校准）",
    oa_key: str = "合同编号"
) -> pd.DataFrame:
    """关联 ONES 签约数据与 OA 合同台账"""
    if ones_key not in ones_df.columns and "销售合同编号" in ones_df.columns:
        ones_df[ones_key] = ones_df["销售合同编号"].apply(calibrate_contract_no)

    if oa_key not in oa_df.columns and "合同编号" in oa_df.columns:
        oa_df[oa_key] = oa_df["合同编号"].apply(calibrate_contract_no)

    result = ones_df.merge(oa_df, left_on=ones_key, right_on=oa_key, how="left", suffixes=("", "_oa"))
    print(f"ONES-OA 关联: {len(ones_df)} 行 -> {len(result)} 行")
    return result


def join_with_legend(
    df: pd.DataFrame,
    legend_type: str,
    lookup_col: str,
    return_col: str
) -> pd.DataFrame:
    """关联图例配置"""
    legend = load_config(f"legend_{legend_type}")
    if not legend:
        print(f"图例配置不存在: legend_{legend_type}.json")
        return df

    mapping = pd.Series(legend)
    return_col_name = f"{return_col}_lookup"
    df[return_col_name] = df[lookup_col].map(mapping)

    matched = df[return_col_name].notna().sum()
    print(f"图例关联 ({legend_type}): {matched}/{len(df)} 行匹配")
    return df


def generate_project_summary(workhour_df: pd.DataFrame) -> pd.DataFrame:
    """从工时数据生成按项目汇总"""
    if "项目名称" not in workhour_df.columns or "登记工时" not in workhour_df.columns:
        print("工时数据缺少必要列")
        return pd.DataFrame(columns=["项目名称", "总工时"])

    summary = workhour_df.groupby("项目名称")["登记工时"].sum().reset_index()
    summary.columns = ["项目名称", "总工时"]
    print(f"工时汇总: {len(summary)} 个项目")
    return summary
