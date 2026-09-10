"""数据清洗 & 标准化

将来自不同数据源的数据标准化为统一格式，存入 SQLite。
"""

import pandas as pd
from pathlib import Path
from typing import Optional

DATA_DIR = Path.home() / ".openclaw" / "data"


def calibrate_contract_no(contract_no: str) -> str:
    """合同编号校准：去除 & 后面的内容"""
    if isinstance(contract_no, str) and "&" in contract_no:
        return contract_no.split("&")[0]
    return contract_no


def clean_ones_contract(csv_path: str) -> pd.DataFrame:
    """清洗 ONES 签约项目统计数据"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
    df.columns = [c.strip() for c in df.columns]

    if "销售合同编号" in df.columns:
        df["合同编号（校准）"] = df["销售合同编号"].apply(calibrate_contract_no)

    date_cols = ["立项日期", "基线-预估结项日期", "实际结项日期",
                 "合同归档日期", "合同起始日期", "合同结束日期",
                 "交付服务开始日期", "交付服务结束日期"]
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    print(f"签约数据清洗完成: {len(df)} 行 x {len(df.columns)} 列")
    return df


def clean_ones_poc(csv_path: str) -> pd.DataFrame:
    """清洗 ONES POC&提前实施统计数据"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
    df.columns = [c.strip() for c in df.columns]

    if "销售合同编号" in df.columns:
        df["合同编号（校准）"] = df["销售合同编号"].apply(calibrate_contract_no)

    print(f"POC 数据清洗完成: {len(df)} 行 x {len(df.columns)} 列")
    return df


def clean_ones_exception(csv_path: str) -> pd.DataFrame:
    """清洗 ONES 异常处置数据"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig", low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    print(f"异常数据清洗完成: {len(df)} 行 x {len(df.columns)} 列")
    return df


def clean_oa_contract(excel_path: str) -> pd.DataFrame:
    """清洗 OA 销售合同信息台账数据"""
    df = pd.read_excel(excel_path)
    df.columns = [c.strip() for c in df.columns]
    print(f"OA 合同台账清洗完成: {len(df)} 行 x {len(df.columns)} 列")
    return df


def clean_wecom_revenue(csv_path: str) -> pd.DataFrame:
    """清洗企业微信确收凭证数据"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    print(f"确收凭证清洗完成: {len(df)} 行 x {len(df.columns)} 列")
    return df


def clean_wecom_acceptance(csv_path: str) -> pd.DataFrame:
    """清洗企业微信验收凭证数据"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    print(f"验收凭证清洗完成: {len(df)} 行 x {len(df.columns)} 列")
    return df


def clean_workhour(excel_path: str) -> pd.DataFrame:
    """清洗工时填报数据"""
    df = pd.read_excel(excel_path)
    df.columns = [c.strip() for c in df.columns]
    print(f"工时数据清洗完成: {len(df)} 行 x {len(df.columns)} 列")
    return df
