"""
交付月报 V2 — 状态引擎（9 种履约项统计状态判定）

复用旧版资产中已验证的状态判定逻辑。
"""

from datetime import datetime
import pandas as pd


def determine_status(row: pd.Series, report_date: str) -> str:
    """
    判断单个履约项的统计状态（9 种之一）

    规则（已验证，沿用旧版）：
    1. 正常交付：实施已完成 AND 交付邮件已归档 AND 未验收 AND 服务期未结束
    2. 应交未交：实施进行中 AND 预估交付完成 < 报告截止 AND 未交付邮件
    3. 交付异常：异常类型 == 履约项交付异常
    4. 正常验收：验收文件已归档 AND 服务期未结束
    5. 应验未验：交付邮件已归档 AND 预估验收完成 < 报告截止 AND 未验收文件
    6. 验收异常：异常类型 == 履约项验收异常
    7. 正常服务：验收文件已归档 AND 服务期未结束 AND 结束日期 >= 报告截止
    8. 应结未结：验收文件已归档 AND 实际服务/授权结束日期 < 报告截止
    9. 已结项：服务期已结束
    """
    status = str(row.get("状态", ""))
    abnormal_type = str(row.get("履约项异常/变更类型", ""))
    estimated_delivery = row.get("预估交付完成日期", "")
    estimated_acceptance = row.get("预估验收完成日期", "")
    actual_service_end = row.get("实际服务/授权结束日期", "")

    report_dt = datetime.strptime(report_date, "%Y-%m-%d")

    def _parse_date(s):
        if not s or pd.isna(s):
            return None
        try:
            return datetime.strptime(str(s)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    est_delivery_dt = _parse_date(estimated_delivery)
    est_acceptance_dt = _parse_date(estimated_acceptance)
    service_end_dt = _parse_date(actual_service_end)

    # 状态标记（9 种）
    is_implementation_not_started = status == "实施未开始"
    is_obligation_split = status == "义务已拆分"
    is_implementation_in_progress = status == "实施进行中"
    is_implementation_done = status == "实施已完成"
    is_delivery_mail_in_progress = status == "交付邮件交接中"
    is_delivery_mail_archived = status == "交付邮件已归档"
    is_acceptance_file_in_progress = status == "验收文件交接中"
    is_acceptance_file_archived = status == "验收文件已归档"

    # 异常类型
    is_delivery_abnormal = "交付异常" in abnormal_type
    is_acceptance_abnormal = "验收异常" in abnormal_type

    # 服务期状态
    service_ended = service_end_dt and service_end_dt < report_dt

    # 9 种状态判定（优先级从高到低）
    if service_ended and is_acceptance_file_archived:
        return "已结项"  # 9

    if is_delivery_abnormal:
        return "交付异常"  # 3

    if is_acceptance_abnormal:
        return "验收异常"  # 6

    if is_acceptance_file_archived and service_end_dt and service_end_dt >= report_dt:
        return "正常服务"  # 7

    if is_acceptance_file_archived and service_ended:
        return "应结未结"  # 8

    if is_delivery_mail_archived and est_acceptance_dt and est_acceptance_dt < report_dt and not is_acceptance_file_archived and not is_acceptance_file_in_progress:
        return "应验未验"  # 5

    if is_acceptance_file_archived:
        return "正常验收"  # 4

    if is_implementation_in_progress and est_delivery_dt and est_delivery_dt < report_dt and not is_delivery_mail_archived and not is_delivery_mail_in_progress:
        return "应交未交"  # 2

    if is_delivery_mail_archived or is_delivery_mail_in_progress:
        return "正常交付"  # 1

    # 其他：按当前状态归类
    if is_implementation_done:
        return "正常交付"
    if is_implementation_in_progress:
        return "正常交付"
    if is_implementation_not_started or is_obligation_split:
        return "正常交付"

    return "正常交付"  # 默认


def add_status_columns(df: pd.DataFrame, report_date: str) -> pd.DataFrame:
    """给 DataFrame 加所有状态相关的计算列（列 45-67）"""
    # 列 45-53：9 个状态标记 + 履约项合计
    status_list = [
        "实施未开始", "义务已拆分", "实施进行中", "实施已完成",
        "交付邮件交接中", "交付邮件已归档", "验收文件交接中", "验收文件已归档"
    ]
    for s in status_list:
        df[s] = (df["状态"] == s).astype(int)

    df["履约项合计"] = df[status_list].sum(axis=1)
    df["校验"] = ""  # 保留列

    # 列 55-67：项目统计状态 + 9 种履约统计状态
    df["项目统计状态"] = df["项目状态"]  # 保留列
    df["履约项统计状态（即，财报-交付/确收状态）"] = df.apply(
        lambda r: determine_status(r, report_date), axis=1
    )

    # 9 种状态标记列
    status_names = [
        ("1：正常交付", "正常交付"),
        ("2：应交未交", "应交未交"),
        ("3：交付异常", "交付异常"),
        ("4：正常验收", "正常验收"),
        ("5：应验未验", "应验未验"),
        ("6：验收异常", "验收异常"),
        ("7：正常服务", "正常服务"),
        ("8：应结未结", "应结未结"),
        ("9：已结项", "已结项"),
    ]
    for col_name, status_val in status_names:
        df[col_name] = (df["履约项统计状态（即，财报-交付/确收状态）"] == status_val).astype(int)

    df["统计校验"] = ""  # 保留列
    df["项目验收状态（即，财报-验收状态）"] = df.apply(
        lambda r: "正常验收" if r["履约项统计状态（即，财报-交付/确收状态）"] in ["正常验收", "正常服务", "已结项"]
        else "验收异常" if r["履约项统计状态（即，财报-交付/确收状态）"] == "验收异常"
        else "未验收", axis=1
    )

    return df
