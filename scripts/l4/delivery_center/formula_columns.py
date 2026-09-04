"""交付月报公式列计算引擎

实现签约 Sheet 中 40 个公式列（列44-83，AR-CE）的等价计算逻辑。

公式来源：REF Excel 签约 Sheet
- 列44(AR): 合同归档年度
- 列45-52(AS-AZ): 各状态履约项计数（按项目聚合）
- 列53(BA): 履约项合计
- 列54(BB): 校验
- 列55(BC): 项目统计状态
- 列56(BD): 履约项统计状态
- 列57-65(BE-BM): 各履约项统计状态计数（按项目聚合）
- 列66(BN): 统计校验
- 列67(BO): 项目验收状态
- 列68(BP): 基线-预估结项日期（计算后反填）
- 列69-72(BQ-BT): 交付计划准确率
- 列73-76(BU-BX): 按时交付率
- 列77(BY): 项目经理
- 列78(BZ): 项目经理所属部门
- 列79(CA): 销售团队-统计
- 列80-83(CB-CE): 异常项目相关

用法:
    from scripts.l4.delivery_center.formula_columns import compute_formula_columns
    result_df = compute_formula_columns(df, report_date, legend_df, abnormal_df)
"""

from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional

import numpy as np
import pandas as pd


# ============================================================
# 状态枚举
# ============================================================

STATUS_WEISHISHI = ["实施未开始", "义务已拆分", "实施进行中", "实施已完成", "交付邮件交接中"]
STATUS_YIJIAOFU = ["交付邮件已归档", "验收文件交接中"]
STATUS_YIYANSHOU = ["验收文件已归档"]

DELIVERY_STATUS_NORMAL = "1：正常交付"
DELIVERY_STATUS_OVERDUE = "2：应交未交"
DELIVERY_STATUS_ABNORMAL = "3：交付异常"
ACCEPTANCE_STATUS_NORMAL = "4：正常验收"
ACCEPTANCE_STATUS_OVERDUE = "5：应验未验"
ACCEPTANCE_STATUS_ABNORMAL = "6：验收异常"
SERVICE_STATUS_NORMAL = "7：正常服务"
SERVICE_STATUS_OVERDUE = "8：应结未结"
PROJECT_CLOSED = "9：已结项"


# ============================================================
# 辅助函数
# ============================================================

def _parse_date(val) -> Optional[pd.Timestamp]:
    """解析日期值，支持字符串、datetime、Excel序列号等。
    
    返回 pd.Timestamp 或 None（空值）。
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, str):
        val = val.strip()
        if val == "" or val.lower() == "nan":
            return None
    try:
        ts = pd.to_datetime(val, errors="coerce")
        if pd.isna(ts):
            return None
        return ts
    except Exception:
        return None


def _date_to_excel_serial(dt: pd.Timestamp) -> int:
    """将日期转换为 Excel 序列号（用于数值比较）。
    
    Excel 日期序列号：1900-01-01 = 1（实际 Excel 有 1900 闰年 bug，
    但对于现代日期我们用标准方式计算即可）。
    """
    if dt is None or pd.isna(dt):
        return 0
    # Excel: 1900-01-01 = 1
    base = pd.Timestamp("1899-12-30")  # 兼容 Excel 的 1900 闰年 bug
    delta = dt.normalize() - base
    return int(delta.days)


def _safe_len(val) -> int:
    """Excel LEN() 等价：空值返回0。"""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 0
    return len(str(val))


def _extract_project_code(project_name: str) -> Optional[str]:
    """从所属项目名称中提取项目编号。
    
    格式：【SSXM-2026-0708-1784】项目名称
    """
    if project_name is None or (isinstance(project_name, float) and np.isnan(project_name)):
        return None
    m = re.search(r"【([^】]+)】", str(project_name))
    if m:
        return m.group(1)
    return None


def _build_vlookup_map(df_lookup: pd.DataFrame, key_col: str, val_col: str) -> dict:
    """构建 VLOOKUP 映射字典。"""
    result = {}
    for _, row in df_lookup.iterrows():
        key = row.get(key_col)
        val = row.get(val_col)
        if key is not None and not (isinstance(key, float) and np.isnan(key)):
            result[str(key).strip()] = val
    return result


# ============================================================
# 列 44: 合同归档年度
# ============================================================

def _col_44_contract_archive_year(df: pd.DataFrame) -> pd.Series:
    """AR: 合同归档年度 = YEAR(合同归档日期)
    
    公式: =YEAR(P3)
    P列 = 合同归档日期
    """
    def get_year(val):
        dt = _parse_date(val)
        if dt is None:
            return np.nan
        return dt.year
    return df["合同归档日期"].apply(get_year)


# ============================================================
# 列 45-52: 各状态履约项计数（按项目编号聚合）
# ============================================================

STATUS_COLUMNS = [
    ("实施未开始", 45, "AS"),
    ("义务已拆分", 46, "AT"),
    ("实施进行中", 47, "AU"),
    ("实施已完成", 48, "AV"),
    ("交付邮件交接中", 49, "AW"),
    ("交付邮件已归档", 50, "AX"),
    ("验收文件交接中", 51, "AY"),
    ("验收文件已归档", 52, "AZ"),
]


def _compute_status_counts(df: pd.DataFrame) -> dict[str, pd.Series]:
    """计算各状态履约项计数（按项目编号聚合）。
    
    公式: =IF(LEN(AP3)>0, COUNTIFS($AO:$AO, AP3, $AB:$AB, $AS$2), 0)
    - AO = 项目编号
    - AP = 统计项目编号（仅首行有值）
    - AB = 状态
    """
    result = {}
    project_col = "项目编号"
    
    for status_name, col_idx, col_letter in STATUS_COLUMNS:
        # 按项目编号统计各状态数量
        status_mask = df["状态"] == status_name
        counts = df[status_mask].groupby(project_col).size()
        
        # 对每行，如果统计项目编号非空则取该项目的计数，否则为0
        def get_count(row, cnt=counts):
            proj_code = row.get("统计项目编号")
            if proj_code is None or (isinstance(proj_code, float) and np.isnan(proj_code)) or str(proj_code).strip() == "":
                return 0
            return int(cnt.get(str(proj_code).strip(), 0))
        
        result[status_name] = df.apply(get_count, axis=1)
    
    return result


# ============================================================
# 列 53: 履约项合计
# ============================================================

def _col_53_total_items(df: pd.DataFrame) -> pd.Series:
    """BA: 履约项合计 = 该项目下所有履约项总数
    
    公式: =IF(LEN(AP3)>0, COUNTIFS($AO:$AO, AP3), 0)
    """
    project_col = "项目编号"
    total_counts = df.groupby(project_col).size()
    
    def get_total(row):
        proj_code = row.get("统计项目编号")
        if proj_code is None or (isinstance(proj_code, float) and np.isnan(proj_code)) or str(proj_code).strip() == "":
            return 0
        return int(total_counts.get(str(proj_code).strip(), 0))
    
    return df.apply(get_total, axis=1)


# ============================================================
# 列 54: 校验
# ============================================================

def _col_54_check(df: pd.DataFrame, status_counts: dict[str, pd.Series], total_items: pd.Series) -> pd.Series:
    """BB: 校验 = 履约项合计 - 各状态计数之和
    
    公式: =IF(LEN(AP3)>0,COUNTIFS($AO:$AO,AP3),0)-SUM(AS3:AZ3)
    """
    sum_status = pd.Series(0, index=df.index)
    for status_name in [s[0] for s in STATUS_COLUMNS]:
        sum_status = sum_status + status_counts[status_name]
    
    return total_items - sum_status


# ============================================================
# 列 55: 项目统计状态
# ============================================================

def _col_55_project_stat_status(df: pd.DataFrame, status_counts: dict[str, pd.Series], 
                                 total_items: pd.Series) -> pd.Series:
    """BC: 项目统计状态
    
    公式:
    =IF(LEN(AP3)>0,
        IF(COUNTIFS($AO:$AO, AP3, $I:$I, "已归档"), "已结项",
            IF(BA3<=AZ3, "已完整验收",
                IF(BA3<=AX3+AY3+AZ3, "可完整验收",
                    IF(0<AX3+AY3+AZ3, "可部分验收", "完全不可验收")))), "")
    - I = 项目状态
    - BA = 履约项合计
    - AZ = 验收文件已归档
    - AY = 验收文件交接中
    - AX = 交付邮件已归档
    """
    # 检查每个项目是否有"已归档"状态
    project_col = "项目编号"
    archived_mask = df["项目状态"] == "已归档"
    archived_projects = set(df[archived_mask][project_col].dropna().unique())
    
    ax = status_counts["交付邮件已归档"]
    ay = status_counts["验收文件交接中"]
    az = status_counts["验收文件已归档"]
    
    def get_status(i, row):
        proj_code = row.get("统计项目编号")
        if proj_code is None or (isinstance(proj_code, float) and np.isnan(proj_code)) or str(proj_code).strip() == "":
            return np.nan
        
        proj_str = str(proj_code).strip()
        ba_val = total_items.iloc[i]
        az_val = az.iloc[i]
        ax_val = ax.iloc[i]
        ay_val = ay.iloc[i]
        
        if proj_str in archived_projects:
            return "已结项"
        if ba_val <= az_val:
            return "已完整验收"
        if ba_val <= ax_val + ay_val + az_val:
            return "可完整验收"
        if 0 < ax_val + ay_val + az_val:
            return "可部分验收"
        return "完全不可验收"
    
    return pd.Series([get_status(i, row) for i, row in df.iterrows()], index=df.index)


# ============================================================
# 列 56: 履约项统计状态
# ============================================================

def _col_56_delivery_stat_status(df: pd.DataFrame, report_date: date) -> pd.Series:
    """BD: 履约项统计状态（即，财报-交付/确收状态）
    
    公式: =_xlfn.IFS(
    AND(OR(AB="实施未开始",...,"交付邮件交接中"), OR(AF>=A1, LEN(AF)=0), AC<>"履约项交付异常"), "1：正常交付",
    AND(OR(AB="实施未开始",...,"交付邮件交接中"), AF<A1, AC<>"履约项交付异常"), "2：应交未交",
    AND(OR(AB="实施未开始",...,"交付邮件交接中"), AC="履约项交付异常"), "3：交付异常",
    AND(OR(AB="交付邮件已归档","验收文件交接中"), OR(AK>=A1, LEN(AK)=0), AC<>"履约项验收异常"), "4：正常验收",
    AND(OR(AB="交付邮件已归档","验收文件交接中"), AK<A1, AC<>"履约项验收异常"), "5：应验未验",
    AND(OR(AB="交付邮件已归档","验收文件交接中"), AC="履约项验收异常"), "6：验收异常",
    AND(I<>"已归档", OR(AB="验收文件已归档"), OR(K>=A1, LEN(K)=0)), "7：正常服务",
    AND(I<>"已归档", OR(AB="验收文件已归档"), K<A1), "8：应结未结",
    AND(I="已归档"), "9：已结项")
    
    列映射:
    - AB = 状态
    - AF = 预算-预估交付完成日期
    - A1 = 报告日期
    - AC = 履约项异常/变更备注
    - AK = 预算-预估验收完成日期
    - I = 项目状态
    - K = 基线-预估结项日期
    """
    report_dt = pd.Timestamp(report_date)
    
    def compute_row(row):
        status = row.get("状态", "")
        if status is None or (isinstance(status, float) and np.isnan(status)):
            status = ""
        status = str(status).strip()
        
        ac_val = row.get("履约项异常/变更备注", "")
        if ac_val is None or (isinstance(ac_val, float) and np.isnan(ac_val)):
            ac_val = ""
        ac_val = str(ac_val).strip()
        
        af_dt = _parse_date(row.get("预算-预估交付完成日期"))
        ak_dt = _parse_date(row.get("预算-预估验收完成日期"))
        k_dt = _parse_date(row.get("基线-预估结项日期"))
        
        project_status = row.get("项目状态", "")
        if project_status is None or (isinstance(project_status, float) and np.isnan(project_status)):
            project_status = ""
        project_status = str(project_status).strip()
        
        in_delivery = status in STATUS_WEISHISHI
        in_acceptance = status in STATUS_YIJIAOFU
        in_service = status in STATUS_YIYANSHOU
        
        # === 1-3: 交付阶段（IFS 顺序优先）===
        if in_delivery:
            if ac_val == "履约项交付异常":
                return DELIVERY_STATUS_ABNORMAL
            if af_dt is None or af_dt >= report_dt:
                return DELIVERY_STATUS_NORMAL
            else:
                return DELIVERY_STATUS_OVERDUE
        
        # === 4-6: 验收阶段 ===
        if in_acceptance:
            if ac_val == "履约项验收异常":
                return ACCEPTANCE_STATUS_ABNORMAL
            if ak_dt is None or ak_dt >= report_dt:
                return ACCEPTANCE_STATUS_NORMAL
            else:
                return ACCEPTANCE_STATUS_OVERDUE
        
        # === 7-8: 服务阶段 ===
        if in_service:
            if project_status != "已归档":
                if k_dt is None or k_dt >= report_dt:
                    return SERVICE_STATUS_NORMAL
                else:
                    return SERVICE_STATUS_OVERDUE
        
        # === 9: 已结项（最后检查）===
        if project_status == "已归档":
            return PROJECT_CLOSED
        
        # 兜底
        return ""
    
    return df.apply(compute_row, axis=1)


# ============================================================
# 列 57-65: 各履约项统计状态计数（按项目聚合）
# ============================================================

DELIVERY_STATUS_LIST = [
    (DELIVERY_STATUS_NORMAL, 57, "BE"),
    (DELIVERY_STATUS_OVERDUE, 58, "BF"),
    (DELIVERY_STATUS_ABNORMAL, 59, "BG"),
    (ACCEPTANCE_STATUS_NORMAL, 60, "BH"),
    (ACCEPTANCE_STATUS_OVERDUE, 61, "BI"),
    (ACCEPTANCE_STATUS_ABNORMAL, 62, "BJ"),
    (SERVICE_STATUS_NORMAL, 63, "BK"),
    (SERVICE_STATUS_OVERDUE, 64, "BL"),
    (PROJECT_CLOSED, 65, "BM"),
]


def _compute_delivery_status_counts(df: pd.DataFrame, delivery_stat: pd.Series) -> dict[str, pd.Series]:
    """计算各履约项统计状态计数（按项目聚合）。
    
    公式: =IF(LEN(AP3)>0, COUNTIFS($AO:$AO, AP3, BD:BD, $BE$2), 0)
    """
    result = {}
    project_col = "项目编号"
    
    # 临时列用于分组
    temp_df = df.copy()
    temp_df["_delivery_stat"] = delivery_stat
    
    for status_name, col_idx, col_letter in DELIVERY_STATUS_LIST:
        status_mask = temp_df["_delivery_stat"] == status_name
        counts = temp_df[status_mask].groupby(project_col).size()
        
        def get_count(row, cnt=counts):
            proj_code = row.get("统计项目编号")
            if proj_code is None or (isinstance(proj_code, float) and np.isnan(proj_code)) or str(proj_code).strip() == "":
                return 0
            return int(cnt.get(str(proj_code).strip(), 0))
        
        result[status_name] = df.apply(get_count, axis=1)
    
    return result


# ============================================================
# 列 66: 统计校验
# ============================================================

def _col_66_stat_check(delivery_counts: dict[str, pd.Series], total_items: pd.Series) -> pd.Series:
    """BN: 统计校验 = SUM(BE:BM) - BA
    
    公式: =SUM(BE3:BM3)-BA3
    """
    sum_delivery = None
    for status_name in [s[0] for s in DELIVERY_STATUS_LIST]:
        if sum_delivery is None:
            sum_delivery = delivery_counts[status_name].copy()
        else:
            sum_delivery = sum_delivery + delivery_counts[status_name]
    
    return sum_delivery - total_items


# ============================================================
# 列 67: 项目验收状态
# ============================================================

def _col_67_project_acceptance_status(df: pd.DataFrame, delivery_counts: dict[str, pd.Series],
                                       total_items: pd.Series) -> pd.Series:
    """BO: 项目验收状态（即，财报-验收状态）
    
    公式: =IF(LEN(AP3)>0,_xlfn.IFS(
        BM3=BA3,"已结项",
        BJ3>0,"异常验收",
        SUM(BK3:BM3)=BA3,"全部验收",
        AND(SUM(BK3:BM3)>0,SUM(BK3:BM3)<BA3),"部分验收",
        BI3>0,"应验未验",
        SUM(BE3:BH3)>0,"正常验收"),"")
    
    - BM = 9：已结项
    - BA = 履约项合计
    - BJ = 6：验收异常
    - BK = 7：正常服务
    - BL = 8：应结未结
    - BM = 9：已结项
    - BI = 5：应验未验
    - BE = 1：正常交付
    - BF = 2：应交未交
    - BG = 3：交付异常
    - BH = 4：正常验收
    """
    be = delivery_counts[DELIVERY_STATUS_NORMAL]
    bf = delivery_counts[DELIVERY_STATUS_OVERDUE]
    bg = delivery_counts[DELIVERY_STATUS_ABNORMAL]
    bh = delivery_counts[ACCEPTANCE_STATUS_NORMAL]
    bi = delivery_counts[ACCEPTANCE_STATUS_OVERDUE]
    bj = delivery_counts[ACCEPTANCE_STATUS_ABNORMAL]
    bk = delivery_counts[SERVICE_STATUS_NORMAL]
    bl = delivery_counts[SERVICE_STATUS_OVERDUE]
    bm = delivery_counts[PROJECT_CLOSED]
    
    def get_status(i, row):
        proj_code = row.get("统计项目编号")
        if proj_code is None or (isinstance(proj_code, float) and np.isnan(proj_code)) or str(proj_code).strip() == "":
            return np.nan
        
        ba_val = total_items.iloc[i]
        bm_val = bm.iloc[i]
        bj_val = bj.iloc[i]
        bk_val = bk.iloc[i]
        bl_val = bl.iloc[i]
        bi_val = bi.iloc[i]
        be_val = be.iloc[i]
        bf_val = bf.iloc[i]
        bg_val = bg.iloc[i]
        bh_val = bh.iloc[i]
        
        sum_bk_bm = bk_val + bl_val + bm_val
        sum_be_bh = be_val + bf_val + bg_val + bh_val
        
        if bm_val == ba_val:
            return "已结项"
        if bj_val > 0:
            return "异常验收"
        if sum_bk_bm == ba_val:
            return "全部验收"
        if sum_bk_bm > 0 and sum_bk_bm < ba_val:
            return "部分验收"
        if bi_val > 0:
            return "应验未验"
        if sum_be_bh > 0:
            return "正常验收"
        return ""
    
    return pd.Series([get_status(i, row) for i, row in df.iterrows()], index=df.index)


# ============================================================
# 列 68: 基线-预估结项日期（计算后反填）
# ============================================================

def _col_68_baseline_end_date(df: pd.DataFrame, acceptance_status: pd.Series) -> pd.Series:
    """BP: 基线-预估结项日期（计算后反填）
    
    公式: =IF(BO3="全部验收", _xlfn.MAXIFS(AI:AI, AO:AO, AP3), "")
    - BO = 项目验收状态
    - AI = 实际服务/授权结束日期
    - AO = 项目编号
    - AP = 统计项目编号
    
    全部验收时，取该项目下最大的实际服务/授权结束日期。
    """
    project_col = "项目编号"
    
    # 计算每个项目的最大实际服务结束日期
    # 先解析日期
    end_dates = df["实际服务/授权结束日期"].apply(_parse_date)
    
    # 按项目取最大值
    temp = pd.DataFrame({
        "project": df[project_col],
        "end_date": end_dates,
    })
    max_end_dates = temp.dropna(subset=["end_date"]).groupby("project")["end_date"].max()
    
    def get_date(i, row):
        acc_status = acceptance_status.iloc[i]
        if acc_status != "全部验收":
            return None
        
        proj_code = row.get("统计项目编号")
        if proj_code is None or (isinstance(proj_code, float) and np.isnan(proj_code)) or str(proj_code).strip() == "":
            return None
        
        proj_str = str(proj_code).strip()
        if proj_str in max_end_dates.index:
            return max_end_dates[proj_str]
        return None
    
    result = pd.Series([get_date(i, row) for i, row in df.iterrows()], index=df.index)
    return result


# ============================================================
# 列 69-72: 交付计划准确率
# ============================================================

def _col_69_delivery_plan_diff(df: pd.DataFrame) -> pd.Series:
    """BQ: 交付计划准确率"差异"
    
    公式: =IF(AE3=0,-9999,IF(ISNA(AF3),0,IF(AF3=0,0,AE3-AF3)))
    - AE = 预估交付完成日期
    - AF = 预算-预估交付完成日期
    
    返回日期差值（天），-9999 表示当期未填写。
    """
    def compute(row):
        ae = _parse_date(row.get("预估交付完成日期"))
        af = _parse_date(row.get("预算-预估交付完成日期"))
        
        if ae is None:
            return -9999
        if af is None:
            return 0
        delta = (ae - af).days
        return delta
    
    return df.apply(compute, axis=1)


def _col_70_delivery_plan_advance_delay(diff: pd.Series) -> pd.Series:
    """BR: 交付计划准确率"提前/延后"
    
    公式: =IF(BQ3=-9999,"当期未填写",IF(BQ3>0,"延后",IF(BQ3<0,"提前","一致")))
    """
    def classify(val):
        if val == -9999:
            return "当期未填写"
        if val > 0:
            return "延后"
        if val < 0:
            return "提前"
        return "一致"
    
    return diff.apply(classify)


def _col_71_delivery_plan_cross_month(df: pd.DataFrame, diff: pd.Series) -> pd.Series:
    """BS: 交付计划准确率"是否跨月"
    
    公式: =IF(OR(BQ3=0,BQ3=-9999,AC3="履约项交付异常"),"不统计",
              IF(YEAR(AE3)&"-"&MONTH(AE3)=YEAR(AF3)&"-"&MONTH(AF3),"否","是"))
    - AC = 履约项异常/变更备注
    - AE = 预估交付完成日期
    - AF = 预算-预估交付完成日期
    """
    def compute(i, row):
        bq = diff.iloc[i]
        ac_val = row.get("履约项异常/变更备注", "")
        if ac_val is None or (isinstance(ac_val, float) and np.isnan(ac_val)):
            ac_val = ""
        ac_val = str(ac_val).strip()
        
        if bq == 0 or bq == -9999 or ac_val == "履约项交付异常":
            return "不统计"
        
        ae = _parse_date(row.get("预估交付完成日期"))
        af = _parse_date(row.get("预算-预估交付完成日期"))
        
        if ae is None or af is None:
            return "不统计"
        
        ae_ym = f"{ae.year}-{ae.month}"
        af_ym = f"{af.year}-{af.month}"
        
        if ae_ym == af_ym:
            return "否"
        return "是"
    
    return pd.Series([compute(i, row) for i, row in df.iterrows()], index=df.index)


def _col_72_delivery_plan_score(advance_delay: pd.Series, cross_month: pd.Series, diff: pd.Series) -> pd.Series:
    """BT: 交付计划准确率-考核扣分
    
    公式: =IF(OR(BR3="一致",BR3="当期未填写",BS3="不统计"),0,
              IF(AND(BS3="否",ABS(BQ3)<15),0.5,1))
    """
    def compute(i):
        br = advance_delay.iloc[i]
        bs = cross_month.iloc[i]
        bq = diff.iloc[i]
        
        if br in ("一致", "当期未填写") or bs == "不统计":
            return 0
        if bs == "否" and abs(bq) < 15:
            return 0.5
        return 1
    
    return pd.Series([compute(i) for i in range(len(advance_delay))], index=advance_delay.index)


# ============================================================
# 列 73-76: 按时交付率
# ============================================================

def _col_73_ontime_delivery_diff(df: pd.DataFrame, status_category_map: dict) -> pd.Series:
    """BU: 按时交付率"差异"
    
    公式: =IF(VLOOKUP(AB3,图例!M:N,2,FALSE)="未实施",0,
              IF(OR(AE3=0,AG3=0),-9999,AG3-AE3))
    - AB = 状态
    - AE = 预估交付完成日期
    - AG = 交付邮件发送日期
    
    状态类别为"未实施"时差异为0；
    否则，预估交付完成日期或交付邮件发送日期为空时为-9999；
    否则为 交付邮件发送日期 - 预估交付完成日期。
    """
    def compute(row):
        status = row.get("状态", "")
        if status is None or (isinstance(status, float) and np.isnan(status)):
            status = ""
        status = str(status).strip()
        
        category = status_category_map.get(status, "")
        if category == "未实施":
            return 0
        
        ae = _parse_date(row.get("预估交付完成日期"))
        ag = _parse_date(row.get("交付邮件发送日期"))
        
        if ae is None or ag is None:
            return -9999
        
        delta = (ag - ae).days
        return delta
    
    return df.apply(compute, axis=1)


def _col_74_ontime_delivery_advance_delay(diff: pd.Series) -> pd.Series:
    """BV: 按时交付率"提前/延后"
    
    公式: =IF(BU3=-9999,"当期未填写",IF(BU3>0,"延后",IF(BU3<0,"提前","一致")))
    """
    def classify(val):
        if val == -9999:
            return "当期未填写"
        if val > 0:
            return "延后"
        if val < 0:
            return "提前"
        return "一致"
    
    return diff.apply(classify)


def _col_75_ontime_delivery_cross_month(df: pd.DataFrame, diff: pd.Series) -> pd.Series:
    """BW: 按时交付率"是否跨月"
    
    公式: =IF(OR(BU3=0,BU3=-9999,AC3="履约项交付异常"),"不统计",
              IF(YEAR(AE3)&"-"&MONTH(AE3)=YEAR(AG3)&"-"&MONTH(AG3),"否","是"))
    - AC = 履约项异常/变更备注
    - AE = 预估交付完成日期
    - AG = 交付邮件发送日期
    """
    def compute(i, row):
        bu = diff.iloc[i]
        ac_val = row.get("履约项异常/变更备注", "")
        if ac_val is None or (isinstance(ac_val, float) and np.isnan(ac_val)):
            ac_val = ""
        ac_val = str(ac_val).strip()
        
        if bu == 0 or bu == -9999 or ac_val == "履约项交付异常":
            return "不统计"
        
        ae = _parse_date(row.get("预估交付完成日期"))
        ag = _parse_date(row.get("交付邮件发送日期"))
        
        if ae is None or ag is None:
            return "不统计"
        
        ae_ym = f"{ae.year}-{ae.month}"
        ag_ym = f"{ag.year}-{ag.month}"
        
        if ae_ym == ag_ym:
            return "否"
        return "是"
    
    return pd.Series([compute(i, row) for i, row in df.iterrows()], index=df.index)


def _col_76_ontime_delivery_score(advance_delay: pd.Series, cross_month: pd.Series, diff: pd.Series) -> pd.Series:
    """BX: 按时交付率-考核扣分
    
    公式: =IF(OR(BV3="一致",BV3="当期未填写",BW3="不统计"),0,
              IF(AND(BW3="否",ABS(BU3)<15),0.5,1))
    """
    def compute(i):
        bv = advance_delay.iloc[i]
        bw = cross_month.iloc[i]
        bu = diff.iloc[i]
        
        if bv in ("一致", "当期未填写") or bw == "不统计":
            return 0
        if bw == "否" and abs(bu) < 15:
            return 0.5
        return 1
    
    return pd.Series([compute(i) for i in range(len(advance_delay))], index=advance_delay.index)


# ============================================================
# 列 77: 项目经理
# ============================================================

def _col_77_project_manager(df: pd.DataFrame) -> pd.Series:
    """BY: 项目经理 = 负责人
    
    公式: =F3
    F列 = 负责人
    """
    return df["负责人"].copy()


# ============================================================
# 列 78: 项目经理所属部门
# ============================================================

def _col_78_pm_department(df: pd.DataFrame, pm_dept_map: dict) -> pd.Series:
    """BZ: 项目经理所属部门
    
    公式: =VLOOKUP(F:F,图例!A:B,2,0)
    - F = 负责人
    - 图例!A = 项目经理
    - 图例!B = 部门
    """
    def lookup(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "#N/A"
        key = str(val).strip()
        return pm_dept_map.get(key, "#N/A")
    
    return df["负责人"].apply(lookup)


# ============================================================
# 列 79: 销售团队-统计
# ============================================================

def _col_79_sales_team_stat(df: pd.DataFrame, sales_team_map: dict) -> pd.Series:
    """CA: 销售团队-统计
    
    公式: =VLOOKUP(E3,图例!AA:AB,2,FALSE)
    - E = 责任销售所属团队
    - 图例!AA = 责任销售所属团队
    - 图例!AB = 销售团队-统计
    """
    def lookup(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "#N/A"
        key = str(val).strip()
        return sales_team_map.get(key, "#N/A")
    
    return df["责任销售所属团队"].apply(lookup)


# ============================================================
# 列 80-83: 异常项目相关
# ============================================================

def _col_80_83_abnormal_project(df: pd.DataFrame, abnormal_df: pd.DataFrame) -> dict[str, pd.Series]:
    """CB-CE: 异常项目对比、异常处置状态、异常影响情况、交付说明
    
    公式:
    CB: =VLOOKUP(M3,异常项目!A:AE,1,FALSE)  → 异常项目对比（销售合同编号存在性检查）
    CC: =VLOOKUP(M3,异常项目!A:AE,18,FALSE) → 异常处置状态 (第18列=状态列R)
    CD: =VLOOKUP(M3,异常项目!A:AE,27,FALSE) → 异常影响情况 (第27列=异常影响情况列AA)
    CE: =VLOOKUP(M3,异常项目!A:AE,31,FALSE) → 交付说明 (第31列=交付说明列AE)
    
    - M = 销售合同编号
    - 异常项目!A = 销售合同编号 (查找键)
    """
    # 构建异常项目映射（销售合同编号 → 各列值）
    abnormal_map = {}  # key: 销售合同编号, value: {col_idx: value}
    # Excel VLOOKUP with FALSE returns FIRST match - iterate from top
    for _, row in abnormal_df.iterrows():
        contract_no = row.iloc[0]  # 第1列 = 销售合同编号
        if contract_no is None or (isinstance(contract_no, float) and np.isnan(contract_no)):
            continue
        key = str(contract_no).strip()
        if key in abnormal_map:
            continue  # Keep first match (Excel VLOOKUP behavior)
        abnormal_map[key] = {
            1: row.iloc[0] if len(row) > 0 else "#N/A",      # 异常项目对比（返回键值本身）
            18: row.iloc[17] if len(row) > 17 else "#N/A",   # 异常处置状态
            27: row.iloc[26] if len(row) > 26 else "#N/A",   # 异常影响情况
            31: row.iloc[30] if len(row) > 30 else "#N/A",   # 交付说明
        }
    
    def lookup_value(row, col_idx):
        contract_no = row.get("销售合同编号")
        if contract_no is None or (isinstance(contract_no, float) and np.isnan(contract_no)):
            return "#N/A"
        key = str(contract_no).strip()
        if key in abnormal_map:
            val = abnormal_map[key].get(col_idx, "#N/A")
            if val is None or (isinstance(val, float) and np.isnan(val)):
                # Key found but value is empty - Excel returns 0 for numeric, empty for text
                # VLOOKUP returns the empty cell value, which Excel treats as 0 in most contexts
                return 0 if col_idx != 1 else key
            return val
        return "#N/A"
    
    result = {}
    result["异常项目对比"] = df.apply(lambda r: lookup_value(r, 1), axis=1)
    result["异常处置状态"] = df.apply(lambda r: lookup_value(r, 18), axis=1)
    result["异常影响情况"] = df.apply(lambda r: lookup_value(r, 27), axis=1)
    result["交付说明"] = df.apply(lambda r: lookup_value(r, 31), axis=1)
    
    return result


# ============================================================
# 主函数
# ============================================================

def compute_formula_columns(
    df: pd.DataFrame,
    report_date: date,
    legend_df: pd.DataFrame,
    abnormal_df: pd.DataFrame,
) -> pd.DataFrame:
    """计算签约 Sheet 的 40 个公式列。
    
    Args:
        df: 签约数据 DataFrame（ONES CSV 导出格式）。
            必须包含以下列：
            - 合同归档日期
            - 状态
            - 履约项异常/变更备注
            - 项目状态
            - 预估交付完成日期
            - 预算-预估交付完成日期
            - 交付邮件发送日期
            - 实际服务/授权结束日期
            - 预算-预估验收完成日期
            - 基线-预估结项日期
            - 负责人
            - 责任销售所属团队
            - 销售合同编号
            - 所属项目（用于提取项目编号）
        report_date: 报告日期（如 date(2026, 6, 30)）
        legend_df: 图例 Sheet 数据 DataFrame
        abnormal_df: 异常项目 Sheet 数据 DataFrame
    
    Returns:
        添加了 40 个公式列的 DataFrame。新增列名与 Excel 列含义对应。
    """
    result = df.copy()
    
    # --------------------------------------------------------
    # 预处理：提取项目编号 & 统计项目编号
    # --------------------------------------------------------
    # 项目编号（每行都有）
    if "项目编号" not in result.columns:
        # 从所属项目提取（格式：【SSXM-xxx】项目名称）
        result["项目编号"] = result["所属项目"].apply(_extract_project_code)
        # 如果提取失败（无【】格式），直接使用所属项目值
        result["项目编号"] = result.apply(
            lambda r: r["项目编号"] if pd.notna(r["项目编号"]) and r["项目编号"] != ""
            else (str(r["所属项目"]).strip() if pd.notna(r["所属项目"]) else np.nan),
            axis=1
        )
    
    # 统计项目编号（仅每组项目的第一行有值，用于项目级聚合公式）
    # 如果输入数据已有该列，直接使用；否则按项目编号分组生成
    if "统计项目编号" not in result.columns:
        result["统计项目编号"] = pd.Series([np.nan] * len(result), dtype="object")
        seen_projects = set()
        for idx, row in result.iterrows():
            proj = row.get("项目编号")
            if proj and pd.notna(proj) and str(proj).strip() != "" and proj not in seen_projects:
                seen_projects.add(proj)
                result.at[idx, "统计项目编号"] = proj
    
    # --------------------------------------------------------
    # 预处理：构建图例映射
    # --------------------------------------------------------
    # 项目经理 → 部门（图例!A:B）
    pm_dept_map = {}
    if legend_df is not None and len(legend_df.columns) >= 2:
        # 第一行是表头：项目经理/部门
        for i in range(1, len(legend_df)):
            pm = legend_df.iloc[i, 0]
            dept = legend_df.iloc[i, 1]
            if pm is not None and not (isinstance(pm, float) and np.isnan(pm)):
                pm_dept_map[str(pm).strip()] = dept if dept is not None else "#N/A"
    
    # 状态 → 状态类别（图例!M:N）
    status_category_map = {}
    if legend_df is not None and len(legend_df.columns) >= 14:
        # 列 M(12) 和 N(13) - 0-based index
        m_col_idx = 12
        n_col_idx = 13
        if len(legend_df.columns) > n_col_idx:
            for i in range(1, len(legend_df)):
                status = legend_df.iloc[i, m_col_idx]
                category = legend_df.iloc[i, n_col_idx]
                if status is not None and not (isinstance(status, float) and np.isnan(status)):
                    status_category_map[str(status).strip()] = str(category).strip() if category is not None else ""
    
    # 责任销售所属团队 → 销售团队-统计（图例!AA:AB）
    # AA = 第26列 (0-based), AB = 第27列
    sales_team_map = {}
    if legend_df is not None and len(legend_df.columns) >= 28:
        aa_col_idx = 26
        ab_col_idx = 27
        for i in range(1, len(legend_df)):
            team = legend_df.iloc[i, aa_col_idx]
            stat_team = legend_df.iloc[i, ab_col_idx]
            if team is not None and not (isinstance(team, float) and np.isnan(team)):
                sales_team_map[str(team).strip()] = stat_team if stat_team is not None else "#N/A"
    
    # --------------------------------------------------------
    # 列 44: 合同归档年度
    # --------------------------------------------------------
    result["合同归档年度"] = _col_44_contract_archive_year(result)
    
    # --------------------------------------------------------
    # 列 45-52: 各状态履约项计数
    # --------------------------------------------------------
    status_counts = _compute_status_counts(result)
    for status_name, col_idx, col_letter in STATUS_COLUMNS:
        result[f"cnt_{status_name}"] = status_counts[status_name]
    
    # --------------------------------------------------------
    # 列 53: 履约项合计
    # --------------------------------------------------------
    result["履约项合计"] = _col_53_total_items(result)
    
    # --------------------------------------------------------
    # 列 54: 校验
    # --------------------------------------------------------
    result["校验_状态"] = _col_54_check(result, status_counts, result["履约项合计"])
    
    # --------------------------------------------------------
    # 列 55: 项目统计状态
    # --------------------------------------------------------
    result["项目统计状态"] = _col_55_project_stat_status(result, status_counts, result["履约项合计"])
    
    # --------------------------------------------------------
    # 列 56: 履约项统计状态
    # --------------------------------------------------------
    result["履约项统计状态"] = _col_56_delivery_stat_status(result, report_date)
    
    # --------------------------------------------------------
    # 列 57-65: 各履约项统计状态计数
    # --------------------------------------------------------
    delivery_counts = _compute_delivery_status_counts(result, result["履约项统计状态"])
    for status_name, col_idx, col_letter in DELIVERY_STATUS_LIST:
        result[f"cnt_{status_name}"] = delivery_counts[status_name]
    
    # --------------------------------------------------------
    # 列 66: 统计校验
    # --------------------------------------------------------
    result["统计校验"] = _col_66_stat_check(delivery_counts, result["履约项合计"])
    
    # --------------------------------------------------------
    # 列 67: 项目验收状态
    # --------------------------------------------------------
    result["项目验收状态"] = _col_67_project_acceptance_status(result, delivery_counts, result["履约项合计"])
    
    # --------------------------------------------------------
    # 列 68: 基线-预估结项日期（计算后反填）
    # --------------------------------------------------------
    result["基线_预估结项日期_计算"] = _col_68_baseline_end_date(result, result["项目验收状态"])
    
    # --------------------------------------------------------
    # 列 69-72: 交付计划准确率
    # --------------------------------------------------------
    bq = _col_69_delivery_plan_diff(result)
    br = _col_70_delivery_plan_advance_delay(bq)
    bs = _col_71_delivery_plan_cross_month(result, bq)
    bt = _col_72_delivery_plan_score(br, bs, bq)
    
    result["交付计划准确率_差异"] = bq
    result["交付计划准确率_提前延后"] = br
    result["交付计划准确率_是否跨月"] = bs
    result["交付计划准确率_考核扣分"] = bt
    
    # --------------------------------------------------------
    # 列 73-76: 按时交付率
    # --------------------------------------------------------
    bu = _col_73_ontime_delivery_diff(result, status_category_map)
    bv = _col_74_ontime_delivery_advance_delay(bu)
    bw = _col_75_ontime_delivery_cross_month(result, bu)
    bx = _col_76_ontime_delivery_score(bv, bw, bu)
    
    result["按时交付率_差异"] = bu
    result["按时交付率_提前延后"] = bv
    result["按时交付率_是否跨月"] = bw
    result["按时交付率_考核扣分"] = bx
    
    # --------------------------------------------------------
    # 列 77: 项目经理
    # --------------------------------------------------------
    result["项目经理"] = _col_77_project_manager(result)
    
    # --------------------------------------------------------
    # 列 78: 项目经理所属部门
    # --------------------------------------------------------
    result["项目经理所属部门"] = _col_78_pm_department(result, pm_dept_map)
    
    # --------------------------------------------------------
    # 列 79: 销售团队-统计
    # --------------------------------------------------------
    result["销售团队_统计"] = _col_79_sales_team_stat(result, sales_team_map)
    
    # --------------------------------------------------------
    # 列 80-83: 异常项目相关
    # --------------------------------------------------------
    if abnormal_df is not None and len(abnormal_df) > 0:
        abnormal_result = _col_80_83_abnormal_project(result, abnormal_df)
        result["异常项目对比"] = abnormal_result["异常项目对比"]
        result["异常处置状态"] = abnormal_result["异常处置状态"]
        result["异常影响情况"] = abnormal_result["异常影响情况"]
        result["交付说明_异常"] = abnormal_result["交付说明"]
    else:
        result["异常项目对比"] = "#N/A"
        result["异常处置状态"] = "#N/A"
        result["异常影响情况"] = "#N/A"
        result["交付说明_异常"] = "#N/A"
    
    return result


# ============================================================
# 数据库落盘
# ============================================================

FORMULA_COLUMNS_DB = [
    # 列名, 类型
    ("合同归档年度", "INTEGER"),
    ("cnt_实施未开始", "INTEGER"),
    ("cnt_义务已拆分", "INTEGER"),
    ("cnt_实施进行中", "INTEGER"),
    ("cnt_实施已完成", "INTEGER"),
    ("cnt_交付邮件交接中", "INTEGER"),
    ("cnt_交付邮件已归档", "INTEGER"),
    ("cnt_验收文件交接中", "INTEGER"),
    ("cnt_验收文件已归档", "INTEGER"),
    ("履约项合计", "INTEGER"),
    ("校验_状态", "INTEGER"),
    ("项目统计状态", "TEXT"),
    ("履约项统计状态", "TEXT"),
    ("cnt_1：正常交付", "INTEGER"),
    ("cnt_2：应交未交", "INTEGER"),
    ("cnt_3：交付异常", "INTEGER"),
    ("cnt_4：正常验收", "INTEGER"),
    ("cnt_5：应验未验", "INTEGER"),
    ("cnt_6：验收异常", "INTEGER"),
    ("cnt_7：正常服务", "INTEGER"),
    ("cnt_8：应结未结", "INTEGER"),
    ("cnt_9：已结项", "INTEGER"),
    ("统计校验", "INTEGER"),
    ("项目验收状态", "TEXT"),
    ("基线_预估结项日期_计算", "DATE"),
    ("交付计划准确率_差异", "INTEGER"),
    ("交付计划准确率_提前延后", "TEXT"),
    ("交付计划准确率_是否跨月", "TEXT"),
    ("交付计划准确率_考核扣分", "REAL"),
    ("按时交付率_差异", "INTEGER"),
    ("按时交付率_提前延后", "TEXT"),
    ("按时交付率_是否跨月", "TEXT"),
    ("按时交付率_考核扣分", "REAL"),
    ("项目经理", "TEXT"),
    ("项目经理所属部门", "TEXT"),
    ("销售团队_统计", "TEXT"),
    ("异常项目对比", "TEXT"),
    ("异常处置状态", "TEXT"),
    ("异常影响情况", "TEXT"),
    ("交付说明_异常", "TEXT"),
]


def init_formula_table(conn=None):
    """创建 sign_formula_columns 表。"""
    from .db import get_connection
    
    close_after = conn is None
    if conn is None:
        conn = get_connection()
    cursor = conn.cursor()
    
    col_defs = ", ".join([f"{name} {dtype}" for name, dtype in FORMULA_COLUMNS_DB])
    
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS sign_formula_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            项目编号 TEXT,
            统计项目编号 TEXT,
            报告日期 DATE,
            BI履约ID TEXT,
            {col_defs},
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sign_fc_project ON sign_formula_columns(项目编号)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sign_fc_stat_project ON sign_formula_columns(统计项目编号)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sign_fc_report_date ON sign_formula_columns(报告日期)")
    
    conn.commit()
    if close_after:
        conn.close()


def save_formula_columns(df: pd.DataFrame, report_date: date, conn=None) -> int:
    """将公式列计算结果写入 sign_formula_columns 表。
    
    Args:
        df: compute_formula_columns 的输出 DataFrame
        report_date: 报告日期
        conn: 数据库连接（可选）
    
    Returns:
        写入行数
    """
    from .db import get_connection, executemany
    
    close_after = conn is None
    if conn is None:
        conn = get_connection()
    
    init_formula_table(conn)
    
    cursor = conn.cursor()
    
    # 清空该报告日期的旧数据
    cursor.execute("DELETE FROM sign_formula_columns WHERE 报告日期 = ?", (str(report_date),))
    
    # 准备插入数据
    col_names = [name for name, _ in FORMULA_COLUMNS_DB]
    placeholders = ", ".join(["?"] * (4 + len(col_names)))  # 项目编号, 统计项目编号, 报告日期, BI履约ID + 公式列
    insert_cols = ["项目编号", "统计项目编号", "报告日期", "BI履约ID"] + col_names
    
    records = []
    for _, row in df.iterrows():
        record = []
        record.append(str(row.get("项目编号", "")) if pd.notna(row.get("项目编号")) else "")
        stat_proj = row.get("统计项目编号", "")
        record.append(str(stat_proj) if stat_proj and pd.notna(stat_proj) else "")
        record.append(str(report_date))
        record.append(str(row.get("BI履约ID", "")) if pd.notna(row.get("BI履约ID")) else "")
        
        for col_name in col_names:
            val = row.get(col_name)
            if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
                record.append(None)
            elif isinstance(val, pd.Timestamp):
                record.append(val.strftime("%Y-%m-%d"))
            else:
                record.append(val)
        
        records.append(tuple(record))
    
    sql = f"INSERT INTO sign_formula_columns ({', '.join(insert_cols)}) VALUES ({placeholders})"
    cursor.executemany(sql, records)
    conn.commit()
    
    count = cursor.rowcount
    if close_after:
        conn.close()
    
    return count


def compute_abnormal_formula_columns(
    abnormal_df: pd.DataFrame,
    sign_formula_df: pd.DataFrame,
) -> pd.DataFrame:
    """计算异常项目 Sheet 的 2 个公式列（列37-38）。

    公式来源：REF Excel 异常项目 Sheet
    - 列37(徐亚东/项目经理团队): VLOOKUP(A2, 签约!M:BZ, 65, FALSE)
      → 用销售合同编号从 sign_formula_columns 查找项目经理所属部门（列78=列M+65）
    - 列38(全部验收/项目验收状态): VLOOKUP(A2, 签约!M:BO, 55, FALSE)
      → 用销售合同编号查找项目验收状态（列67=列M+55）

    Args:
        abnormal_df: 异常项目原始数据（含"销售合同编号"列）
        sign_formula_df: 签约公式列结果（含"销售合同编号"和公式列）

    Returns:
        添加了 2 个公式列的 DataFrame
    """
    df = abnormal_df.copy()

    # 建立 销售合同编号 → 签约公式列 的映射（取第一条匹配）
    sign_map = {}
    for _, row in sign_formula_df.iterrows():
        contract_id = str(row.get("销售合同编号", "")) if pd.notna(row.get("销售合同编号")) else ""
        if contract_id and contract_id not in sign_map:
            sign_map[contract_id] = {
                "项目经理所属部门": row.get("项目经理所属部门"),
                "项目验收状态": row.get("项目验收状态"),
            }

    # VLOOKUP 等价
    def vlookup(contract_id, field):
        key = str(contract_id) if pd.notna(contract_id) else ""
        match = sign_map.get(key)
        if match:
            val = match.get(field)
            if val is not None and pd.notna(val):
                return val
        return None

    df["项目经理团队"] = df["销售合同编号"].apply(lambda x: vlookup(x, "项目经理所属部门"))
    df["项目验收状态_异常"] = df["销售合同编号"].apply(lambda x: vlookup(x, "项目验收状态"))

    return df


def init_abnormal_formula_table(conn=None):
    """初始化异常项目公式列表。"""
    from .db import get_connection

    close_after = conn is None
    if conn is None:
        conn = get_connection()

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS abnormal_formula_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            销售合同编号 TEXT NOT NULL,
            报告日期 TEXT NOT NULL,
            项目经理团队 TEXT,
            项目验收状态_异常 TEXT,
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(销售合同编号, 报告日期)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_afc_contract
        ON abnormal_formula_columns (销售合同编号)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_afc_report_date
        ON abnormal_formula_columns (报告日期)
    """)
    conn.commit()

    if close_after:
        conn.close()


def save_abnormal_formula_columns(df, report_date, conn=None):
    """保存异常项目公式列到数据库。"""
    from .db import get_connection

    close_after = conn is None
    if conn is None:
        conn = get_connection()

    init_abnormal_formula_table(conn)

    cursor = conn.cursor()
    cursor.execute("DELETE FROM abnormal_formula_columns WHERE 报告日期 = ?", (str(report_date),))

    records = []
    for _, row in df.iterrows():
        contract_id = str(row.get("销售合同编号", "")) if pd.notna(row.get("销售合同编号")) else ""
        pm_team = row.get("项目经理团队")
        inspect_status = row.get("项目验收状态_异常")
        records.append((
            contract_id,
            str(report_date),
            str(pm_team) if pm_team is not None and pd.notna(pm_team) else None,
            str(inspect_status) if inspect_status is not None and pd.notna(inspect_status) else None,
        ))

    cursor.executemany(
        "INSERT INTO abnormal_formula_columns (销售合同编号, 报告日期, 项目经理团队, 项目验收状态_异常) VALUES (?, ?, ?, ?)",
        records,
    )
    conn.commit()

    count = len(records)
    if close_after:
        conn.close()

    return count



# ============================================================
# POC 公式列（列41-84，AO-CF）
# ============================================================

POC_FORMULA_COLUMNS_DB = [
    # 列名, 类型
    ("项目编号", "TEXT"),
    ("统计项目编号", "TEXT"),
    ("统计合同编号", "TEXT"),
    ("合同归档年度", "INTEGER"),
    ("cnt_实施未开始", "INTEGER"),
    ("cnt_义务已拆分", "INTEGER"),
    ("cnt_实施进行中", "INTEGER"),
    ("cnt_实施已完成", "INTEGER"),
    ("cnt_交付邮件交接中", "INTEGER"),
    ("cnt_交付邮件已归档", "INTEGER"),
    ("cnt_验收文件交接中", "INTEGER"),
    ("cnt_验收文件已归档", "INTEGER"),
    ("履约项合计", "INTEGER"),
    ("校验_状态", "INTEGER"),
    ("项目统计状态", "TEXT"),
    ("履约项统计状态", "TEXT"),
    ("cnt_1正常交付", "INTEGER"),
    ("cnt_2应交未交", "INTEGER"),
    ("cnt_3交付异常", "INTEGER"),
    ("cnt_4正常验收", "INTEGER"),
    ("cnt_5应验未验", "INTEGER"),
    ("cnt_6验收异常", "INTEGER"),
    ("cnt_7正常服务", "INTEGER"),
    ("cnt_8应结未结", "INTEGER"),
    ("cnt_9已结项", "INTEGER"),
    ("统计校验", "INTEGER"),
    ("项目验收状态", "TEXT"),
    ("基线_预估结项日期_计算", "TEXT"),
    ("交付计划准确率_差异", "INTEGER"),
    ("交付计划准确率_提前延后", "TEXT"),
    ("交付计划准确率_是否跨月", "TEXT"),
    ("交付计划准确率_考核扣分", "REAL"),
    ("按时交付率_差异", "INTEGER"),
    ("按时交付率_提前延后", "TEXT"),
    ("按时交付率_是否跨月", "TEXT"),
    ("按时交付率_考核扣分", "REAL"),
    ("项目经理所属部门", "TEXT"),
    ("销售团队_统计", "TEXT"),
    ("提前实施持续周期_天", "INTEGER"),
    ("提前实施持续周期_统计", "TEXT"),
    ("提前实施是否已关联合同", "TEXT"),
    ("关联合同归档日期", "TEXT"),
    ("统计所属项目", "TEXT"),
    ("POC项目工时合计", "REAL"),
]


def _poc_has_stat_project(row) -> bool:
    """判断该行是否为项目统计行（统计项目编号非空）。"""
    val = row.get("统计项目编号")
    return val is not None and pd.notna(val) and str(val).strip() != ""


def _poc_compute_status_counts(df: pd.DataFrame) -> dict:
    """POC版本：各状态履约项计数（按项目编号聚合）。"""
    result = {}
    project_col = "项目编号"
    stat_col = "统计项目编号"

    for status_name, _, _ in STATUS_COLUMNS:
        status_mask = df["状态"] == status_name
        counts = df[status_mask].groupby(project_col).size()
        series = pd.Series(0, index=df.index, dtype=int)
        for idx, row in df.iterrows():
            if _poc_has_stat_project(row):
                proj = row[project_col]
                series.at[idx] = int(counts.get(proj, 0))
        result[status_name] = series
    return result


def _poc_compute_delivery_status_counts(df: pd.DataFrame, delivery_stat: pd.Series) -> dict:
    """POC版本：各履约项统计状态计数（按项目聚合）。"""
    result = {}
    project_col = "项目编号"

    temp_df = df.copy()
    temp_df["_ds"] = delivery_stat

    for status_name, _, _ in DELIVERY_STATUS_LIST:
        status_mask = temp_df["_ds"] == status_name
        counts = temp_df[status_mask].groupby(project_col).size()
        series = pd.Series(0, index=df.index, dtype=int)
        for idx, row in df.iterrows():
            if _poc_has_stat_project(row):
                proj = row[project_col]
                series.at[idx] = int(counts.get(proj, 0))
        result[status_name] = series
    return result


def _poc_col_total_items(df: pd.DataFrame, status_counts: dict) -> pd.Series:
    """POC列53：履约项合计。"""
    series = pd.Series(0, index=df.index, dtype=int)
    status_names = [s[0] for s in STATUS_COLUMNS]
    for idx, row in df.iterrows():
        if _poc_has_stat_project(row):
            total = sum(int(status_counts[s][idx]) for s in status_names)
            series.at[idx] = total
    return series


def _poc_col_check(df: pd.DataFrame, status_counts: dict, total_items: pd.Series) -> pd.Series:
    """POC列54：校验（履约项合计 vs 各状态计数之和）。"""
    series = pd.Series(0, index=df.index, dtype=int)
    status_names = [s[0] for s in STATUS_COLUMNS]
    for idx, row in df.iterrows():
        if _poc_has_stat_project(row):
            s = sum(int(status_counts[sname][idx]) for sname in status_names)
            series.at[idx] = 1 if s == int(total_items[idx]) else 0
    return series


def _poc_col_stat_check(df: pd.DataFrame, delivery_counts: dict, total_items: pd.Series) -> pd.Series:
    """POC列66：统计校验。"""
    series = pd.Series(0, index=df.index, dtype=int)
    status_names = [s[0] for s in DELIVERY_STATUS_LIST]
    for idx, row in df.iterrows():
        if _poc_has_stat_project(row):
            s = sum(int(delivery_counts[sname][idx]) for sname in status_names)
            series.at[idx] = 1 if s == int(total_items[idx]) else 0
    return series


def _poc_col_79_early_duration(
    df: pd.DataFrame,
    sign_contract_archive_map: dict,
) -> pd.Series:
    """POC列79：提前实施项目持续周期（天）。

    公式逻辑：
    =IF(H3="POC","",IFS(
        AND(I3="已归档",LEN(M3)>0), MIN(L3-J3, CD3-J3),
        LEN(M3)>0, CD3-J3,
        I3="已归档", L3-J3,
        TRUE, ""
    ))
    - H=项目类型(概览), I=项目状态, L=合同结束日期, J=立项日期,
    - M=销售合同编号, CD=关联合同归档日期
    """
    calc = []
    for _, row in df.iterrows():
        proj_type = str(row.get("项目类型(概览)", ""))
        if proj_type == "POC":
            calc.append(None)
            continue

        proj_status = str(row.get("项目状态", "")) if pd.notna(row.get("项目状态")) else ""
        contract_id = str(row.get("销售合同编号", "")) if pd.notna(row.get("销售合同编号")) else ""
        has_contract = bool(contract_id and contract_id.strip() != "")

        j_date = _parse_date(row.get("立项日期"))
        l_date = _parse_date(row.get("合同结束日期"))
        cd_date = None
        if has_contract and contract_id in sign_contract_archive_map:
            cd_date = _parse_date(sign_contract_archive_map[contract_id])

        # 条件1：已归档 且 有关联合同
        if proj_status == "已归档" and has_contract and cd_date is not None and j_date is not None and l_date is not None:
            dur1 = (l_date - j_date).days
            dur2 = (cd_date - j_date).days
            calc.append(min(dur1, dur2))
            continue

        # 条件2：有关联合同（未归档）
        if has_contract and cd_date is not None and j_date is not None:
            calc.append((cd_date - j_date).days)
            continue

        # 条件3：已归档
        if proj_status == "已归档" and j_date is not None and l_date is not None:
            calc.append((l_date - j_date).days)
            continue

        calc.append(None)

    return pd.Series(calc, index=df.index)


def _poc_col_80_duration_stat(duration: pd.Series) -> pd.Series:
    """POC列80：持续周期-统计。

    分段：1个月内(<=30), 3个月内(31-90), 6个月内(91-180), 1年内(181-365), 1年以上(>365)
    """
    def categorize(d):
        if d is None or pd.isna(d):
            return None
        days = int(d)
        if days <= 30:
            return "1个月内"
        elif days <= 90:
            return "3个月内"
        elif days <= 180:
            return "6个月内"
        elif days <= 365:
            return "1年内"
        else:
            return "1年以上"
    return duration.apply(categorize)


def _poc_col_81_contract_linked(df: pd.DataFrame) -> pd.Series:
    """POC列81：提前实施项目是否已关联合同。

    =IF(AND(LEN(M3)>0,H3="提前实施"),"已关联","未关联")
    """
    def check(row):
        proj_type = str(row.get("项目类型(概览)", ""))
        contract_id = row.get("销售合同编号")
        has_contract = contract_id is not None and pd.notna(contract_id) and str(contract_id).strip() != ""
        if has_contract and proj_type == "提前实施":
            return "已关联"
        return "未关联"
    return df.apply(check, axis=1)


def _poc_col_82_linked_contract_archive(
    df: pd.DataFrame,
    sign_contract_archive_map: dict,
) -> pd.Series:
    """POC列82：关联合同归档日期。

    =VLOOKUP(M3, 签约!M:P, 4, FALSE)
    → 从签约 Sheet 查找合同归档日期
    """
    def lookup(row):
        contract_id = row.get("销售合同编号")
        if contract_id is None or pd.isna(contract_id):
            return None
        key = str(contract_id).strip()
        if not key:
            return None
        return sign_contract_archive_map.get(key)
    return df.apply(lookup, axis=1)


def compute_poc_formula_columns(
    df: pd.DataFrame,
    report_date: date,
    legend_df: pd.DataFrame,
    sign_contract_archive_map: dict | None = None,
) -> pd.DataFrame:
    """计算 POC Sheet 的 44 个公式列（列41-84）。

    Args:
        df: POC 数据 DataFrame（ONES CSV 导出格式）。
            必须包含以下列：
            - 所属项目（用于提取项目编号）
            - 销售合同编号
            - 合同归档日期
            - 状态
            - 履约项异常/变更备注
            - 项目状态
            - 项目类型(概览)
            - 预估交付完成日期
            - 预算-预估交付完成日期
            - 交付邮件发送日期
            - 实际服务/授权结束日期
            - 预算-预估验收完成日期
            - 基线-预估结项日期
            - 负责人
            - 责任销售所属团队
            - 立项日期
            - 合同结束日期
        report_date: 报告日期
        legend_df: 图例 Sheet 数据 DataFrame
        sign_contract_archive_map: 签约合同编号→合同归档日期 映射（用于 VLOOKUP）

    Returns:
        添加了公式列的 DataFrame。
    """
    if sign_contract_archive_map is None:
        sign_contract_archive_map = {}

    result = df.copy()

    # --------------------------------------------------------
    # 预处理：提取项目编号 & 统计项目编号 & 统计合同编号
    # --------------------------------------------------------
    # 列41(AO): 项目编号 = 从所属项目提取
    if "项目编号" not in result.columns:
        result["项目编号"] = result["所属项目"].apply(_extract_project_code)
        result["项目编号"] = result.apply(
            lambda r: r["项目编号"] if pd.notna(r["项目编号"]) and r["项目编号"] != ""
            else (str(r["所属项目"]).strip() if pd.notna(r["所属项目"]) else np.nan),
            axis=1
        )

    # 列42(AP): 统计项目编号（去重，首次出现显示）
    if "统计项目编号" not in result.columns:
        result["统计项目编号"] = pd.Series([np.nan] * len(result), dtype="object")
        seen = set()
        for idx, row in result.iterrows():
            proj = row.get("项目编号")
            if proj and pd.notna(proj) and str(proj).strip() != "" and proj not in seen:
                seen.add(proj)
                result.at[idx, "统计项目编号"] = proj

    # 列43(AQ): 统计合同编号（销售合同编号去重）
    result["统计合同编号"] = pd.Series([np.nan] * len(result), dtype="object")
    seen_contracts = set()
    for idx, row in result.iterrows():
        cid = row.get("销售合同编号")
        if cid and pd.notna(cid) and str(cid).strip() != "" and cid not in seen_contracts:
            seen_contracts.add(cid)
            result.at[idx, "统计合同编号"] = cid

    # --------------------------------------------------------
    # 预处理：构建图例映射
    # --------------------------------------------------------
    # 负责人 → 部门（图例!A:B）
    pm_dept_map = {}
    if legend_df is not None and len(legend_df.columns) >= 2:
        for i in range(1, len(legend_df)):
            pm = legend_df.iloc[i, 0]
            dept = legend_df.iloc[i, 1]
            if pm is not None and not (isinstance(pm, float) and np.isnan(pm)):
                pm_dept_map[str(pm).strip()] = dept if dept is not None else "#N/A"

    # 状态 → 状态类别（图例!M:N）
    status_category_map = {}
    if legend_df is not None and len(legend_df.columns) >= 14:
        for i in range(1, len(legend_df)):
            status = legend_df.iloc[i, 12]
            category = legend_df.iloc[i, 13]
            if status is not None and not (isinstance(status, float) and np.isnan(status)):
                status_category_map[str(status).strip()] = str(category).strip() if category is not None else ""

    # 责任销售所属团队 → 销售团队-统计（图例!AA:AB）
    sales_team_map = {}
    if legend_df is not None and len(legend_df.columns) >= 28:
        for i in range(1, len(legend_df)):
            team = legend_df.iloc[i, 26]
            stat_team = legend_df.iloc[i, 27]
            if team is not None and not (isinstance(team, float) and np.isnan(team)):
                sales_team_map[str(team).strip()] = stat_team if stat_team is not None else "#N/A"

    # --------------------------------------------------------
    # 列44(AR): 合同归档年度
    # --------------------------------------------------------
    result["合同归档年度"] = _col_44_contract_archive_year(result)

    # --------------------------------------------------------
    # 列45-52(AS-AZ): 各状态履约项计数
    # --------------------------------------------------------
    status_counts = _poc_compute_status_counts(result)
    for status_name, _, _ in STATUS_COLUMNS:
        result[f"cnt_{status_name}"] = status_counts[status_name]

    # --------------------------------------------------------
    # 列53(BA): 履约项合计
    # --------------------------------------------------------
    result["履约项合计"] = _poc_col_total_items(result, status_counts)

    # --------------------------------------------------------
    # 列54(BB): 校验
    # --------------------------------------------------------
    result["校验_状态"] = _poc_col_check(result, status_counts, result["履约项合计"])

    # --------------------------------------------------------
    # 列55(BC): 项目统计状态
    # --------------------------------------------------------
    result["项目统计状态"] = _col_55_project_stat_status(result, status_counts, result["履约项合计"])

    # --------------------------------------------------------
    # 列56(BD): 履约项统计状态
    # --------------------------------------------------------
    result["履约项统计状态"] = _col_56_delivery_stat_status(result, report_date)

    # --------------------------------------------------------
    # 列57-65(BE-BM): 各履约项统计状态计数
    # --------------------------------------------------------
    delivery_counts = _poc_compute_delivery_status_counts(result, result["履约项统计状态"])
    for status_name, _, _ in DELIVERY_STATUS_LIST:
        result[f"cnt_{status_name}"] = delivery_counts[status_name]

    # --------------------------------------------------------
    # 列66(BN): 统计校验
    # --------------------------------------------------------
    result["统计校验"] = _poc_col_stat_check(result, delivery_counts, result["履约项合计"])

    # --------------------------------------------------------
    # 列67(BO): 项目验收状态
    # --------------------------------------------------------
    result["项目验收状态"] = _col_67_project_acceptance_status(result, delivery_counts, result["履约项合计"])

    # --------------------------------------------------------
    # 列68(BP): 基线-预估结项日期（计算后反填）
    # --------------------------------------------------------
    result["基线_预估结项日期_计算"] = _col_68_baseline_end_date(result, result["项目验收状态"])

    # --------------------------------------------------------
    # 列69-72(BQ-BT): 交付计划准确率
    # --------------------------------------------------------
    bq = _col_69_delivery_plan_diff(result)
    br = _col_70_delivery_plan_advance_delay(bq)
    bs = _col_71_delivery_plan_cross_month(result, bq)
    bt = _col_72_delivery_plan_score(br, bs, bq)

    result["交付计划准确率_差异"] = bq
    result["交付计划准确率_提前延后"] = br
    result["交付计划准确率_是否跨月"] = bs
    result["交付计划准确率_考核扣分"] = bt

    # --------------------------------------------------------
    # 列73-76(BU-BX): 按时交付率
    # --------------------------------------------------------
    bu = _col_73_ontime_delivery_diff(result, status_category_map)
    bv = _col_74_ontime_delivery_advance_delay(bu)
    bw = _col_75_ontime_delivery_cross_month(result, bu)
    bx = _col_76_ontime_delivery_score(bv, bw, bu)

    result["按时交付率_差异"] = bu
    result["按时交付率_提前延后"] = bv
    result["按时交付率_是否跨月"] = bw
    result["按时交付率_考核扣分"] = bx

    # --------------------------------------------------------
    # 列77(BY): 项目经理所属部门
    # --------------------------------------------------------
    # POC用"负责人"作为项目经理查找
    def _poc_pm_dept(row):
        pm = row.get("负责人")
        if pm is None or pd.isna(pm):
            return "#N/A"
        key = str(pm).strip()
        if not key:
            return "#N/A"
        return pm_dept_map.get(key, "#N/A")
    result["项目经理所属部门"] = result.apply(_poc_pm_dept, axis=1)

    # --------------------------------------------------------
    # 列78(BZ): 销售团队-统计
    # --------------------------------------------------------
    result["销售团队_统计"] = _col_79_sales_team_stat(result, sales_team_map)

    # --------------------------------------------------------
    # 列79(CA): 提前实施项目持续周期（天）
    # --------------------------------------------------------
    result["提前实施持续周期_天"] = _poc_col_79_early_duration(result, sign_contract_archive_map)

    # --------------------------------------------------------
    # 列80(CB): 持续周期-统计
    # --------------------------------------------------------
    result["提前实施持续周期_统计"] = _poc_col_80_duration_stat(result["提前实施持续周期_天"])

    # --------------------------------------------------------
    # 列81(CC): 提前实施是否已关联合同
    # --------------------------------------------------------
    result["提前实施是否已关联合同"] = _poc_col_81_contract_linked(result)

    # --------------------------------------------------------
    # 列82(CD): 关联合同归档日期
    # --------------------------------------------------------
    result["关联合同归档日期"] = _poc_col_82_linked_contract_archive(result, sign_contract_archive_map)

    # --------------------------------------------------------
    # 列83(CE): 统计所属项目（去重）
    # --------------------------------------------------------
    result["统计所属项目"] = pd.Series([np.nan] * len(result), dtype="object")
    seen_proj_names = set()
    for idx, row in result.iterrows():
        pname = row.get("所属项目")
        if pname and pd.notna(pname) and str(pname).strip() != "" and pname not in seen_proj_names:
            seen_proj_names.add(pname)
            result.at[idx, "统计所属项目"] = pname

    # --------------------------------------------------------
    # 列84(CF): POC项目工时合计
    # --------------------------------------------------------
    result["POC项目工时合计"] = 0.0

    return result


def init_poc_formula_table(conn=None):
    """创建 poc_formula_columns 表。"""
    from .db import get_connection

    close_after = conn is None
    if conn is None:
        conn = get_connection()
    cursor = conn.cursor()

    col_defs = ", ".join([f"{name} {dtype}" for name, dtype in POC_FORMULA_COLUMNS_DB])

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS poc_formula_columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            报告日期 DATE,
            BI履约ID TEXT,
            {col_defs},
            导入时间 TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poc_fc_project ON poc_formula_columns(项目编号)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poc_fc_stat_project ON poc_formula_columns(统计项目编号)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poc_fc_report_date ON poc_formula_columns(报告日期)")

    conn.commit()
    if close_after:
        conn.close()


def save_poc_formula_columns(df: pd.DataFrame, report_date: date, conn=None) -> int:
    """保存 POC 公式列到数据库。"""
    from .db import get_connection

    close_after = conn is None
    if conn is None:
        conn = get_connection()

    init_poc_formula_table(conn)

    cursor = conn.cursor()
    cursor.execute("DELETE FROM poc_formula_columns WHERE 报告日期 = ?", (str(report_date),))

    col_names = [name for name, _ in POC_FORMULA_COLUMNS_DB]
    placeholders = ", ".join(["?"] * (len(col_names) + 2))
    col_sql = ", ".join(["报告日期", "BI履约ID"] + col_names)

    records = []
    for _, row in df.iterrows():
        record = [str(report_date)]
        # BI履约ID
        bi_id = row.get("BI履约ID")
        record.append(str(bi_id) if bi_id is not None and pd.notna(bi_id) else None)
        # 各公式列
        for col in col_names:
            val = row.get(col)
            if val is None or pd.isna(val):
                record.append(None)
            elif isinstance(val, (int, float, np.integer, np.floating)):
                record.append(val)
            else:
                record.append(str(val))
        records.append(tuple(record))

    cursor.executemany(
        f"INSERT INTO poc_formula_columns ({col_sql}) VALUES ({placeholders})",
        records
    )
    conn.commit()

    count = len(records)
    if close_after:
        conn.close()

    return count


if __name__ == "__main__":
    # 简单测试
    print("公式列计算引擎已加载")
    print(f"共 {len(FORMULA_COLUMNS_DB)} 个公式列")
    print(f"异常项目公式列: 2 个（项目经理团队、项目验收状态）")
