"""
交付月报 V2 — 考核引擎（交付计划准确率、按时交付率）

复用旧版资产中已验证的考核计算逻辑。
"""

import pandas as pd
from datetime import datetime


def _parse_date(s):
    """解析日期，返回 datetime 或 None"""
    if not s or pd.isna(s):
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _is_cross_month(base_dt, actual_dt):
    """判断是否跨月"""
    if not base_dt or not actual_dt:
        return "否"
    if base_dt.year != actual_dt.year or base_dt.month != actual_dt.month:
        return "是"
    return "否"


def _calc_diff_days(base_dt, actual_dt):
    """计算差异天数（实际 - 基线）"""
    if not base_dt or not actual_dt:
        return None
    return (actual_dt - base_dt).days


def _calc_early_late(diff):
    """判断提前/延后"""
    if diff is None:
        return ""
    if diff < 0:
        return "提前"
    elif diff > 0:
        return "延后"
    else:
        return "准时"


def _calc_score(diff, cross_month):
    """
    计算考核扣分

    规则（已验证，沿用旧版）：
    - 差异绝对值 < 15 天 且 不跨月 → 0 分
    - 差异绝对值 >= 15 天 且 不跨月 → 0.5 分
    - 跨月 → 1 分
    """
    if diff is None:
        return None
    if cross_month == "是":
        return 1
    if abs(diff) < 15:
        return 0
    return 0.5


def add_scoring_columns(df: pd.DataFrame) -> pd.DataFrame:
    """给 DataFrame 加考核相关列（列 68-76）"""

    # 列 68：基线-预估结项日期（计算后反填）
    df["基线-预估结项日期（计算后反填）"] = df["基线-预估结项日期"]

    # 列 69-72：交付计划准确率（4 列：差异 / 提前延后 / 是否跨月 / 扣分）
    def _delivery_plan_accuracy(row):
        base = _parse_date(row.get("基线-预估结项日期", ""))
        actual = _parse_date(row.get("实际结项日期", ""))
        diff = _calc_diff_days(base, actual)
        early_late = _calc_early_late(diff)
        cross_month = _is_cross_month(base, actual)
        score = _calc_score(diff, cross_month)
        return pd.Series([diff, early_late, cross_month, score])

    df[["交付计划准确率“差异”", "交付计划准确率“提前/延后”",
        "交付计划准确率“是否跨月”", "交付计划准确率-考核扣分"]] = df.apply(
        _delivery_plan_accuracy, axis=1
    )

    # 列 73-76：按时交付率（4 列）
    def _on_time_delivery_rate(row):
        base = _parse_date(row.get("预算-预估验收完成日期", ""))
        # 实际验收完成日期：用 实际服务/授权结束日期 近似（或者验收文件归档日期？）
        actual = _parse_date(row.get("实际服务/授权结束日期", ""))
        diff = _calc_diff_days(base, actual)
        early_late = _calc_early_late(diff)
        cross_month = _is_cross_month(base, actual)
        score = _calc_score(diff, cross_month)
        return pd.Series([diff, early_late, cross_month, score])

    df[["按时交付率“差异”", "按时交付率“提前/延后”",
        "按时交付率“是否跨月”", "按时交付率-考核扣分"]] = df.apply(
        _on_time_delivery_rate, axis=1
    )

    return df
