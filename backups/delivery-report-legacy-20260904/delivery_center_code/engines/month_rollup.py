"""月度继承引擎

实现确收月报的月度继承逻辑：每月的结果作为下月的输入。
"""

import pandas as pd
from pathlib import Path
from typing import Optional

DATA_DIR = Path.home() / ".openclaw" / "data" / "bdms"


def load_month_data(month: str, data_type: str) -> Optional[pd.DataFrame]:
    """加载指定月份的数据"""
    file_path = DATA_DIR / f"{data_type}_{month}.csv"
    if file_path.exists():
        return pd.read_csv(file_path, encoding="utf-8-sig")
    return None


def save_month_data(df: pd.DataFrame, month: str, data_type: str):
    """保存指定月份的数据"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DATA_DIR / f"{data_type}_{month}.csv"
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"数据已保存: {file_path}")


def rollup_month(current_month: str, previous_month: str, current_data: pd.DataFrame) -> pd.DataFrame:
    """月度继承：将上月未完成项滚入本月"""
    prev_data = load_month_data(previous_month, "budget")

    if prev_data is None:
        print(f"上月数据不存在: {previous_month}")
        return current_data

    incomplete = prev_data[prev_data.get("确收状态", "") != "已结项"].copy()

    if len(incomplete) > 0:
        merged = pd.concat([current_data, incomplete], ignore_index=True)
        print(f"月度继承: 上月 {len(incomplete)} 项未完成滚入本月")
        return merged

    print("月度继承: 上月全部完成，无需滚入")
    return current_data
