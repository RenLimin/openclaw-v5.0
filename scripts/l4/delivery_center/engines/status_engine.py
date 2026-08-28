"""状态判定引擎

实现 Excel 中 9 种履约项状态的判定逻辑。
基于实施状态 + 交付邮件日期 + 是否异常进行判定。
"""

import pandas as pd
from datetime import datetime
from typing import Optional


def determine_delivery_status(row: pd.Series, report_date: datetime) -> str:
    """判定履约项状态（对应 Excel BD 列的 IFS 公式）"""
    impl_status = str(row.get("状态", ""))
    delivery_mail_date = row.get("交付邮件发送日期", None)
    exception_type = str(row.get("履约项异常/变更类型", ""))

    normal_impl = ["实施未开始", "义务已拆分", "实施进行中", "实施已完成", "交付邮件交接中"]

    # 条件 1: 正常交付
    if (impl_status in normal_impl and
        (pd.isna(delivery_mail_date) or delivery_mail_date == "" or delivery_mail_date >= report_date) and
        exception_type != "履约项交付异常"):
        return "1：正常交付"

    # 条件 2: 应交未交
    if (impl_status in normal_impl and
        pd.notna(delivery_mail_date) and delivery_mail_date != "" and delivery_mail_date < report_date and
        exception_type != "履约项交付异常"):
        return "2：应交未交"

    # 条件 3: 交付异常
    if exception_type == "履约项交付异常":
        return "3：交付异常"

    # 条件 4: 正常验收
    if impl_status == "交付邮件已归档":
        return "4：正常验收"

    # 条件 5: 应验未验
    if impl_status == "验收文件交接中":
        return "5：应验未验"

    # 条件 7: 正常服务
    if impl_status == "验收文件已归档":
        return "7：正常服务"

    # 条件 9: 已结项
    if impl_status == "已结项":
        return "9：已结项"

    return "未分类"


def apply_status_engine(df: pd.DataFrame, report_date: datetime) -> pd.DataFrame:
    """对 DataFrame 应用全部状态判定"""
    df["履约项统计状态"] = df.apply(lambda row: determine_delivery_status(row, report_date), axis=1)

    status_counts = df.groupby(["项目编号", "履约项统计状态"]).size().unstack(fill_value=0)

    for status in ["1：正常交付", "2：应交未交", "3：交付异常", "4：正常验收",
                   "5：应验未验", "6：验收异常", "7：正常服务", "8：应结未结", "9：已结项"]:
        if status in status_counts.columns:
            df[status] = df["项目编号"].map(status_counts[status]).fillna(0).astype(int)
        else:
            df[status] = 0

    print(f"状态判定完成: {len(df)} 行")
    return df
