#!/usr/bin/env python3
"""
交接明细 Sheet 构建引擎
将确收/验收 CSV 转换为与参考报表完全一致的 23/27 列结构

公式列实现：
- 项目经理所属区域：VLOOKUP(项目经理, 图例!A:B, 2, FALSE)
- 跨月交接：IF(ISERROR(FIND("是", 交付邮件是否跨月)), "否", "是")
- 跨月交接原因：空值
- 是否合格：IF(ISERROR(FIND("是", 财务是否接收)), "否", "是")
"""
import pandas as pd
import numpy as np
import json
from pathlib import Path

# 图例路径（复用旧版配置）
LEGEND_PATH = Path(__file__).parent.parent / "delivery_center" / "config" / "legend_pm_dept.json"


def _load_pm_dept_map():
    """加载项目经理 → 所属区域映射"""
    if LEGEND_PATH.exists():
        return json.loads(LEGEND_PATH.read_text(encoding="utf-8"))
    return {}


def build_revenue_handover_df(df_raw: pd.DataFrame, period: str = "202606") -> pd.DataFrame:
    """
    构建确收交接 Sheet DataFrame（23 列，与参考表完全一致）
    
    Args:
        df_raw: 原始确收 CSV DataFrame（25列有效列）
        period: 期间，如 "202606"
    
    Returns:
        23 列 DataFrame，列顺序与参考表完全一致
    """
    df = df_raw.copy()
    
    # 预期列顺序（23 列）
    expected_cols = [
        "月份",
        "标题",
        "ID",
        "BI履约ID",
        "合同编号1",
        "邮件编号",
        "合同编号",
        "客户名称",
        "销售部门",
        "项目经理",
        "备注",
        "交接日期",
        "财务接收人",
        "财务是否接收",
        "财务反馈",
        "交付邮件是否跨月",
        "PMO提交人",
        "PMO反馈",
        "是否修改ONES状态",
        "项目经理所属区域",  # 公式：VLOOKUP
        "跨月交接",          # 公式：IF(ISERROR(FIND("是",P2)),"否","是")
        "跨月交接原因",      # 空值
        "是否合格",          # 公式：IF(ISERROR(FIND("是",N2)),"否","是")
    ]
    
    # 1. 月份
    df["月份"] = period
    
    # 2-11. 直接映射（标题 ~ 备注）
    direct_map = {
        "标题": "标题",
        "ID": "ID",
        "BI履约ID": "BI履约ID",
        "合同编号1": "合同编号1",
        "邮件编号": "邮件编号",
        "合同编号": "合同编号",
        "客户名称": "客户名称",
        "销售部门": "销售部门",
        "项目经理": "项目经理",
        "备注": "备注",
    }
    for new_col, old_col in direct_map.items():
        if old_col in df.columns:
            df[new_col] = df[old_col]
        else:
            df[new_col] = ""
    
    # 12. 交接日期
    if "交接日期" in df.columns:
        df["交接日期"] = pd.to_datetime(df["交接日期"], errors="coerce")
    
    # 13. 财务接收人 ← 财务
    if "财务" in df.columns:
        df["财务接收人"] = df["财务"]
    else:
        df["财务接收人"] = ""
    
    # 14. 财务是否接收 ← 是否接收
    if "是否接收" in df.columns:
        df["财务是否接收"] = df["是否接收"]
    else:
        df["财务是否接收"] = ""
    
    # 15. 财务反馈
    if "财务反馈" not in df.columns:
        df["财务反馈"] = ""
    
    # 16. 交付邮件是否跨月
    if "交付邮件是否跨月" not in df.columns:
        df["交付邮件是否跨月"] = ""
    
    # 17. PMO提交人 ← PMO
    if "PMO" in df.columns:
        df["PMO提交人"] = df["PMO"]
    else:
        df["PMO提交人"] = ""
    
    # 18. PMO反馈 ← PMO备注
    if "PMO备注" in df.columns:
        df["PMO反馈"] = df["PMO备注"]
    else:
        df["PMO反馈"] = ""
    
    # 19. 是否修改ONES状态
    if "是否修改ones状态" in df.columns:
        df["是否修改ONES状态"] = df["是否修改ones状态"]
    else:
        df["是否修改ONES状态"] = ""
    
    # 20. 项目经理所属区域（公式：VLOOKUP(项目经理, 图例!A:B, 2, FALSE)）
    pm_dept_map = _load_pm_dept_map()
    df["项目经理所属区域"] = df["项目经理"].map(pm_dept_map).fillna("#N/A")
    
    # 21. 跨月交接（公式：IF(ISERROR(FIND("是",交付邮件是否跨月)),"否","是")）
    def compute_cross_month(val):
        if pd.isna(val) or val == "" or val is None:
            return "否"
        return "是" if "是" in str(val) else "否"
    
    df["跨月交接"] = df["交付邮件是否跨月"].apply(compute_cross_month)
    
    # 22. 跨月交接原因（空值）
    df["跨月交接原因"] = ""
    
    # 23. 是否合格（公式：IF(ISERROR(FIND("是",财务是否接收)),"否","是")）
    def compute_qualified(val):
        if pd.isna(val) or val == "" or val is None:
            return "否"
        return "是" if "是" in str(val) else "否"
    
    df["是否合格"] = df["财务是否接收"].apply(compute_qualified)
    
    # 按报告日期过滤（交接日期 ≤ period 最后一天）
    end_date = pd.Timestamp(f"{period[:4]}-{period[4:]}-01") + pd.offsets.MonthEnd(0)
    if "交接日期" in df.columns and df["交接日期"].dtype == "datetime64[ns]":
        df = df[df["交接日期"].fillna(pd.Timestamp("2099-12-31")) <= end_date]
    
    # 按预期列顺序返回
    return df[expected_cols]


def build_acceptance_handover_df(df_raw: pd.DataFrame, period: str = "202606") -> pd.DataFrame:
    """
    构建验收交接 Sheet DataFrame（27 列，与参考表完全一致）
    
    Args:
        df_raw: 原始验收 CSV DataFrame
        period: 期间，如 "202606"
    
    Returns:
        27 列 DataFrame，列顺序与参考表完全一致
    """
    df = df_raw.copy()
    
    # 预期列顺序（27 列）
    expected_cols = [
        "月份",
        "合同名称",
        "标题",
        "ID",
        "BI履约ID",
        "验收单编号-财务端",
        "合同编号1",
        "验收单编号",        # 原始CSV第7列，列名是空格
        "合同编号",
        "客户名称",
        "销售部门",
        "项目经理",
        "备注",
        "交接日期",
        "验收方式",
        "截至目前全部/部分验收",       # 第16列
        "是否为渠道",        # 原始CSV列名含换行：是否\n为渠道
        "财务接收人",        # ← 财务
        "是否接收",          # ← 财务是否接收
        "实际验收方式",
        "财务反馈",
        "截至目前全部/部分验收",  # 第22列，同样的列名第二个（参考表里两列同名，不加.1后缀）
        "PMO提交人",         # ← PMO
        "PMO反馈",           # ← PMO备注
        "是否修改ones及OA状态",
        "项目经理所属区域",   # 公式：VLOOKUP
        "是否合格",          # 公式：IF(ISERROR(FIND("是",S2)),"否","是")
    ]
    
    # 1. 月份
    df["月份"] = period
    
    # 2-6. 直接映射
    direct_map = {
        "合同名称": "合同名称",
        "标题": "标题",
        "ID": "ID",
        "BI履约ID": "BI履约ID",
        "验收单编号-财务端": "验收单编号-财务端",
        "合同编号1": "合同编号1",
        "合同编号": "合同编号",
        "客户名称": "客户名称",
        "项目经理": "项目经理",
        "备注": "备注",
        "验收方式": "验收方式",
        "实际验收方式": "实际验收方式",
        "财务反馈": "财务反馈",
        "是否修改ones及OA状态": "是否修改ones及OA状态",
    }
    for new_col, old_col in direct_map.items():
        if old_col in df.columns:
            df[new_col] = df[old_col]
        else:
            df[new_col] = ""
    
    # 7. 销售部门 ← 深圳分公司-营销（第10列）
    if "深圳分公司-营销" in df.columns:
        df["销售部门"] = df["深圳分公司-营销"]
    elif "销售部门" in df.columns:
        df["销售部门"] = df["销售部门"]
    else:
        df["销售部门"] = ""
    
    # 8. 验收单编号 ← 第7列（列名是空格 " "）
    # 先找列名是空格的列
    space_cols = [c for c in df.columns if str(c).strip() == "" and str(c) != ""]
    if space_cols:
        df["验收单编号"] = df[space_cols[0]]
    else:
        # 找第7列（索引6）
        if len(df.columns) > 6:
            df["验收单编号"] = df.iloc[:, 6]
        else:
            df["验收单编号"] = ""
    
    # 9. 交接日期
    if "交接日期" in df.columns:
        df["交接日期"] = pd.to_datetime(df["交接日期"], errors="coerce")
    else:
        df["交接日期"] = pd.NaT
    
    # 10. 截至目前全部/部分验收（第一个）
    if "截至目前全部/部分验收" in df.columns:
        df["截至目前全部/部分验收"] = df["截至目前全部/部分验收"]
    else:
        df["截至目前全部/部分验收"] = ""
    
    # 11. 是否为渠道 ← 列名含换行 "是否\n为渠道"
    channel_cols = [c for c in df.columns if "是否" in str(c) and "渠道" in str(c)]
    if channel_cols:
        df["是否为渠道"] = df[channel_cols[0]]
    else:
        df["是否为渠道"] = ""
    
    # 12. 财务接收人 ← 财务
    if "财务" in df.columns:
        df["财务接收人"] = df["财务"]
    else:
        df["财务接收人"] = ""
    
    # 13. 是否接收 ← 财务是否接收
    if "财务是否接收" in df.columns:
        df["是否接收"] = df["财务是否接收"]
    else:
        df["是否接收"] = ""
    
    # 14. 截至目前全部/部分验收.1（第二个）
    if "截至目前全部/部分验收.1" in df.columns:
        df["截至目前全部/部分验收.1"] = df["截至目前全部/部分验收.1"]
    else:
        df["截至目前全部/部分验收.1"] = ""
    
    # 15. PMO提交人 ← PMO
    if "PMO" in df.columns:
        df["PMO提交人"] = df["PMO"]
    else:
        df["PMO提交人"] = ""
    
    # 16. PMO反馈 ← PMO备注
    if "PMO备注" in df.columns:
        df["PMO反馈"] = df["PMO备注"]
    else:
        df["PMO反馈"] = ""
    
    # 17. 项目经理所属区域（公式：VLOOKUP(L2,图例!A:B,2,FALSE)）
    pm_dept_map = _load_pm_dept_map()
    df["项目经理所属区域"] = df["项目经理"].map(pm_dept_map).fillna("#N/A")
    
    # 18. 是否合格（公式：IF(ISERROR(FIND("是",S2)),"否","是")）
    # S2 = 第19列 = 是否接收
    def compute_qualified(val):
        if pd.isna(val) or val == "" or val is None:
            return "否"
        return "是" if "是" in str(val) else "否"
    
    df["是否合格"] = df["是否接收"].apply(compute_qualified)
    
    # 按报告日期过滤（交接日期 ≤ period 最后一天）
    end_date = pd.Timestamp(f"{period[:4]}-{period[4:]}-01") + pd.offsets.MonthEnd(0)
    if "交接日期" in df.columns and df["交接日期"].dtype == "datetime64[ns]":
        df = df[df["交接日期"].fillna(pd.Timestamp("2099-12-31")) <= end_date]
    
    # 按预期列顺序返回
    return df[expected_cols]
