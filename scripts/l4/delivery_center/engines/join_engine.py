"""关联查询引擎

跨系统数据关联：ONES ↔ OA ↔ WeCom ↔ 工时 ↔ 图例配置。
所有 M2 引擎的基础依赖。

核心能力：
  1. 从 SQLite 加载各数据源
  2. 合同编号校准（去除 & 后面内容）
  3. 跨系统 merge（左连接，保留所有项目）
  4. 图例配置关联（项目经理→部门、团队→大区）
  5. 统一输出 DataFrame
"""

import sqlite3
import json
import pandas as pd
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".openclaw" / "data" / "bdms.db"
CONFIG_DIR = Path(__file__).parent.parent / "config"


# ═══════════════════════════════════════════════════════════════
# 基础工具
# ═══════════════════════════════════════════════════════════════

def calibrate_contract_no(contract_no: str) -> str:
    """合同编号校准：去除 & 后面内容，统一大写"""
    if not isinstance(contract_no, str):
        return ""
    contract_no = contract_no.strip()
    if "&" in contract_no:
        contract_no = contract_no.split("&")[0]
    return contract_no.upper()


def load_config(name: str) -> dict | list:
    """加载 JSON 配置文件"""
    config_path = CONFIG_DIR / f"{name}.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def load_table(table: str) -> pd.DataFrame:
    """从 SQLite 加载整张表"""
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        return pd.DataFrame()
    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    conn.close()
    return df


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

def load_oa_contracts() -> pd.DataFrame:
    """加载 OA 合同台账"""
    df = load_table("oa_contracts")
    if not df.empty and "htbh" in df.columns:
        df["合同编号"] = df["htbh"].apply(calibrate_contract_no)
    return df


def load_revenue_vouchers() -> pd.DataFrame:
    """加载确收凭证"""
    df = load_table("revenue_vouchers")
    if not df.empty and "合同编号" in df.columns:
        df["合同编号"] = df["合同编号"].apply(calibrate_contract_no)
    return df


def load_acceptance_vouchers() -> pd.DataFrame:
    """加载验收凭证"""
    df = load_table("acceptance_vouchers")
    if not df.empty and "合同编号" in df.columns:
        df["合同编号"] = df["合同编号"].apply(calibrate_contract_no)
    return df


def load_workhours() -> pd.DataFrame:
    """加载工时数据"""
    return load_table("workhours")


def load_ones_projects() -> pd.DataFrame:
    """加载 ONES 项目"""
    df = load_table("ones_projects")
    if not df.empty and "合同编号" in df.columns:
        df["合同编号"] = df["合同编号"].apply(calibrate_contract_no)
    return df


# ═══════════════════════════════════════════════════════════════
# 图例关联
# ═══════════════════════════════════════════════════════════════

def map_pm_to_dept(df: pd.DataFrame, pm_col: str = "项目经理") -> pd.DataFrame:
    """项目经理 → 部门映射"""
    legend = load_config("legend_pm_dept")
    if not legend or pm_col not in df.columns:
        return df
    df["部门"] = df[pm_col].map(lambda x: legend.get(str(x).strip(), "其他") if pd.notna(x) else "其他")
    matched = (df["部门"] != "其他").sum()
    print(f"  项目经理→部门: {matched}/{len(df)} 行匹配")
    return df


def map_team_to_region(df: pd.DataFrame, team_col: str = "销售部门") -> pd.DataFrame:
    """销售团队 → 大区映射"""
    legend = load_config("legend_team")
    if not legend or team_col not in df.columns:
        return df
    df["大区"] = df[team_col].map(lambda x: legend.get(str(x).strip(), "其他") if pd.notna(x) else "其他")
    matched = (df["大区"] != "其他").sum()
    print(f"  团队→大区: {matched}/{len(df)} 行匹配")
    return df


def map_status(df: pd.DataFrame, status_col: str = "项目状态") -> pd.DataFrame:
    """实施状态 → 实施阶段映射"""
    legend = load_config("legend_status")
    if not legend or status_col not in df.columns:
        return df
    df["实施阶段"] = df[status_col].map(lambda x: legend.get(str(x).strip(), "未知") if pd.notna(x) else "未知")
    return df


# ═══════════════════════════════════════════════════════════════
# 跨系统关联
# ═══════════════════════════════════════════════════════════════

def join_oa_revenue(oa_df: pd.DataFrame, rev_df: pd.DataFrame) -> pd.DataFrame:
    """OA 合同台账 ↔ 确收凭证"""
    if oa_df.empty or rev_df.empty:
        print("  ⚠️ OA 或确收数据为空")
        return oa_df

    result = oa_df.merge(rev_df, on="合同编号", how="left", suffixes=("", "_rev"))
    matched = result["voucher_id"].notna().sum()
    print(f"  OA↔确收: {matched}/{len(oa_df)} 行匹配")
    return result


def join_oa_acceptance(oa_df: pd.DataFrame, acc_df: pd.DataFrame) -> pd.DataFrame:
    """OA 合同台账 ↔ 验收凭证"""
    if oa_df.empty or acc_df.empty:
        print("  ⚠️ OA 或验收数据为空")
        return oa_df

    result = oa_df.merge(acc_df, on="合同编号", how="left", suffixes=("", "_acc"))
    matched = result["voucher_id"].notna().sum()
    print(f"  OA↔验收: {matched}/{len(oa_df)} 行匹配")
    return result


def join_all_sources() -> pd.DataFrame:
    """全量关联：OA + 确收 + 验收 + 工时 + 图例

    以 OA 合同台账为主表，左连接其他数据源。
    """
    print("[JoinEngine] 加载数据源...")

    oa_df = load_oa_contracts()
    rev_df = load_revenue_vouchers()
    acc_df = load_acceptance_vouchers()
    wh_df = load_workhours()

    print(f"  OA 合同: {len(oa_df)} 行")
    print(f"  确收凭证: {len(rev_df)} 行")
    print(f"  验收凭证: {len(acc_df)} 行")
    print(f"  工时: {len(wh_df)} 行")

    if oa_df.empty:
        print("  ⚠️ OA 合同台账为空，无法关联")
        return pd.DataFrame()

    # 关联确收
    print("\n[JoinEngine] 关联确收凭证...")
    result = join_oa_revenue(oa_df, rev_df)

    # 关联验收
    print("[JoinEngine] 关联验收凭证...")
    result = join_oa_acceptance(result, acc_df)

    # 图例关联
    print("[JoinEngine] 图例关联...")
    result = map_pm_to_dept(result, "项目经理")
    result = map_team_to_region(result, "责任销售部门")
    result = map_status(result, "项目状态")

    print(f"\n[JoinEngine] 关联完成: {len(result)} 行 x {len(result.columns)} 列")
    return result


# ═══════════════════════════════════════════════════════════════
# 查询接口
# ═══════════════════════════════════════════════════════════════

def query_by_contract(contract_no: str) -> Optional[dict]:
    """按合同编号查询全量信息"""
    contract_no = calibrate_contract_no(contract_no)
    df = join_all_sources()
    if df.empty:
        return None

    match = df[df["合同编号"] == contract_no]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def query_by_pm(pm_name: str) -> pd.DataFrame:
    """按项目经理查询"""
    df = join_all_sources()
    if df.empty:
        return pd.DataFrame()
    return df[df["项目经理"].str.contains(pm_name, na=False)]


def query_by_dept(dept: str) -> pd.DataFrame:
    """按部门查询"""
    df = join_all_sources()
    if df.empty:
        return pd.DataFrame()
    return df[df["部门"] == dept]


if __name__ == "__main__":
    print("=== 关联查询引擎测试 ===\n")
    df = join_all_sources()
    if not df.empty:
        print(f"\n列名: {list(df.columns)[:20]}")
        print(f"\n前3行:")
        print(df.head(3).to_string())
    else:
        print("数据为空，请先运行 pipeline 采集数据")
