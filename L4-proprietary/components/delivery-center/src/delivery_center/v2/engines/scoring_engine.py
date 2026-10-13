"""
交付月报 V2 — 考核引擎（交付计划准确率、按时交付率）

对齐人工基准公式语义（202606 黄金基准签约 sheet，r3 公式）：

  c68 基线-预估结项日期（计算后反填） = IF(BO3="全部验收", MAXIFS(预估验收完成日期, 项目编号, 本项目), "")
  c69 交付计划准确率"差异"      = IF(AE3=0,-9999, IF(ISNA(AF3),0, IF(AF3=0,0,AE3-AF3)))
                                   AE=预估交付完成日期  AF=预算-预估交付完成日期
  c70 交付计划准确率"提前/延后" = IF(BQ3=-9999,"当期未填写", IF(BQ3>0,"延后", IF(BQ3<0,"提前","一致")))
  c71 交付计划准确率"是否跨月" = IF(OR(BQ3=0,BQ3=-9999,AC3="履约项交付异常"),"不统计",
                                   IF(YEAR(AE)=MONTH(AE)=YEAR(AF)&MONTH(AF),"否","是"))
  c72 交付计划准确率-考核扣分  = IF(OR(BR3="一致",BR3="当期未填写",BS3="不统计"),0,
                                   IF(AND(BS3="否",ABS(BQ3)<15),0.5,1))
  c73 按时交付率"差异"        = IF(VLOOKUP(状态,图例M:N)="未实施",0, IF(OR(AE3=0,AG3=0),-9999,AG3-AE3))
                                   AG=交付邮件发送日期
  c74 按时交付率"提前/延后"   = 同 c70（基于 c73）
  c75 按时交付率"是否跨月"    = 同 c71（比较 AE 与 AG 年月）
  c76 按时交付率-考核扣分     = 同 c72（基于 c74/c75）
"""

import json
from datetime import datetime, time as dtime
from pathlib import Path
import pandas as pd

# 图例状态→类别映射（图例 M:N）
# engines/ 下 → 需上溯三级到 delivery_center 包根，再进 v1/config
LEGEND_STATUS_PATH = Path(__file__).parent.parent.parent / "v1" / "config" / "legend_status.json"


def _load_status_category_map() -> dict:
    if LEGEND_STATUS_PATH.exists():
        return json.loads(LEGEND_STATUS_PATH.read_text(encoding="utf-8"))
    return {}


def _parse_date(s):
    """解析日期，返回 datetime 或 None"""
    if not s or pd.isna(s):
        return None
    if isinstance(s, datetime):
        return s
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _diff_days(base_dt, actual_dt):
    """差异天数（实际 - 基线）；任一为空返回 None"""
    if not base_dt or not actual_dt:
        return None
    return (actual_dt - base_dt).days


def _early_late_text(diff):
    if diff is None:
        return ""
    if diff == -9999:
        return "当期未填写"
    if diff > 0:
        return "延后"
    if diff < 0:
        return "提前"
    return "一致"


def _cross_month_text(d1, d2):
    if not d1 or not d2:
        return "不统计"
    if d1.year == d2.year and d1.month == d2.month:
        return "否"
    return "是"


def _score(diff, cross_month):
    """考核扣分：一致/当期未填写/不统计 → 0；不跨月且 |diff|<15 → 0.5；否则 1"""
    if cross_month == "不统计":
        return 0
    if diff is None:
        return 0
    if cross_month == "否" and abs(diff) < 15:
        return 0.5
    return 1


def add_scoring_columns(df: pd.DataFrame) -> pd.DataFrame:
    """给 DataFrame 加考核相关列（列 68-76），对齐人工基准公式。"""

    # 需要的前置列
    status_map = _load_status_category_map()

    # c68 基线-预估结项日期（计算后反填）
    # 人工公式：=IF(BO3="全部验收", MAXIFS(AI:AI, AO:AO, AP3), "")
    #   AI=c35 实际服务/授权结束日期, AO=c41 项目编号, AP=c42 统计项目编号
    #   - 逐行判断当前行 c67（非聚合首行）
    #   - 条件用当前行 c42 统计项目编号（非首行为空 → MAXIFS 返回 0 → time(0,0)）
    #   - 结果写原生 datetime / time 类型（对齐人工单元格类型）
    df["基线-预估结项日期（计算后反填）"] = ""
    if ("项目编号" in df.columns and "统计项目编号" in df.columns
            and "项目验收状态（即，财报-验收状态）" in df.columns):
        # 每个项目 实际服务/授权结束日期 最大值（AO=c41 项目编号 匹配）
        max_acc_date = {}
        for i in range(len(df)):
            p = str(df.iloc[i].get("项目编号", ""))
            d = _parse_date(df.iloc[i].get("实际服务/授权结束日期", ""))
            if d:
                cur = max_acc_date.get(p)
                if cur is None or d > cur:
                    max_acc_date[p] = d
        vals = []
        for i in range(len(df)):
            status = df.iloc[i].get("项目验收状态（即，财报-验收状态）", "")
            # 对齐人工语义：c67 为 #N/A（错误值）时，IF 比较传播 #N/A
            if str(status) == "#N/A":
                vals.append("#N/A")
                continue
            if str(status) != "全部验收":
                vals.append("")
                continue
            cond = df.iloc[i].get("统计项目编号", "")
            if cond is None or pd.isna(cond) or str(cond).strip() == "":
                # MAXIFS 空条件 → 无匹配 → 0 → Excel 时间 00:00:00
                vals.append(dtime(0, 0))
                continue
            d = max_acc_date.get(str(cond))
            vals.append(d if d else dtime(0, 0))
        df["基线-预估结项日期（计算后反填）"] = vals

    # c69-72 交付计划准确率
    delivery_diff, delivery_early, delivery_cross, delivery_score = [], [], [], []
    for _, row in df.iterrows():
        est = _parse_date(row.get("预估交付完成日期", ""))       # AE
        budget = _parse_date(row.get("预算-预估交付完成日期", ""))  # AF
        abnormal = str(row.get("履约项异常/变更类型", "") or "").strip()

        if est is None:
            diff = -9999
        elif budget is None:
            diff = 0
        elif est == budget:
            diff = 0
        else:
            diff = (est - budget).days  # AE - AF

        early = _early_late_text(diff)
        if diff in (0, -9999) or abnormal == "履约项交付异常":
            cross = "不统计"
        else:
            cross = _cross_month_text(est, budget)
        score = _score(diff, cross)

        delivery_diff.append(diff)
        delivery_early.append(early)
        delivery_cross.append(cross)
        delivery_score.append(score)

    df["交付计划准确率“差异”"] = delivery_diff
    df["交付计划准确率“提前/延后”"] = delivery_early
    df["交付计划准确率“是否跨月”"] = delivery_cross
    df["交付计划准确率-考核扣分"] = delivery_score

    # c73-76 按时交付率
    ot_diff, ot_early, ot_cross, ot_score = [], [], [], []
    for _, row in df.iterrows():
        status = str(row.get("状态", "") or "").strip()            # AB
        est = _parse_date(row.get("预估交付完成日期", ""))         # AE
        mail_date = _parse_date(row.get("交付邮件发送日期", ""))    # AG
        abnormal = str(row.get("履约项异常/变更类型", "") or "").strip()

        status_cat = status_map.get(status, "")
        if status and not status_cat:
            # 状态不在图例映射（如 交付邮件已发送）→ VLOOKUP 返回 #N/A 并传播
            diff = "#N/A"
        elif status_cat == "未实施":
            diff = 0
        elif est is None or mail_date is None:
            diff = -9999
        else:
            diff = (mail_date - est).days  # AG - AE

        early = _early_late_text(diff) if diff != "#N/A" else "#N/A"
        if diff == "#N/A":
            cross = "#N/A"
            score = "#N/A"
        elif diff in (0, -9999) or abnormal == "履约项交付异常":
            cross = "不统计"
            score = _score(diff, cross)
        else:
            cross = _cross_month_text(est, mail_date)
            score = _score(diff, cross)

        ot_diff.append(diff)
        ot_early.append(early)
        ot_cross.append(cross)
        ot_score.append(score)

    df["按时交付率“差异”"] = ot_diff
    df["按时交付率“提前/延后”"] = ot_early
    df["按时交付率“是否跨月”"] = ot_cross
    df["按时交付率-考核扣分"] = ot_score

    return df
