#!/usr/bin/env python3
"""
BDMS 交付月报 V2 — 生成器入口

版本：v2.0 (重新设计)
设计文档：docs/architecture/components/l4-delivery-center-v2/
"""

import sys
from pathlib import Path
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

# 业务引擎
sys.path.insert(0, str(Path(__file__).parent / "engines"))
from status_engine import add_status_columns
from scoring_engine import add_scoring_columns
from mapping_engine import (
    add_mapping_columns,
    add_simple_computed_columns,
    add_exception_lookup_columns
)
from exception_engine import build_exception_df
from handover_engine import build_revenue_handover_df, build_acceptance_handover_df
# 统计Sheet生成器
sys.path.insert(0, str(Path(__file__).parent / "generators"))
from build_stat_sheets import (
    build_sign_stats, build_poc_stats, build_abnormal_stats,
    build_product_stats, build_poc_dept_stats, build_abnormal_dept_stats,
    build_handover_stats, build_abnormal_ledger, build_legend
)
# utils
sys.path.insert(0, str(Path(__file__).parent / "utils"))
from poc_hours import get_poc_project_hours
# 精确格式配置（从参考表提取）
sys.path.insert(0, str(Path(__file__).parent / "config"))
from sheet_formats import SHEET_FORMAT_MAP

# 统一样式常量，精确匹配参考表（从手工报表styles.xml提取）
# 表头字体：微软雅黑 10号 加粗 白色
HEADER_FONT = Font(name="微软雅黑", bold=True, size=10, color="FFFFFF")
# 表头底色：精确 FF2D73BA（蓝色）
HEADER_FILL = PatternFill(start_color="FF2D73BA", end_color="FF2D73BA", fill_type="solid")
# 数据字体：微软雅黑 10号 普通 黑色
DATA_FONT = Font(name="微软雅黑", size=10, color="FF000000")
# 细边框
THIN_BORDER = Border(
    left=Side(style='thin', color="FF000000"),
    right=Side(style='thin', color="FF000000"),
    top=Side(style='thin', color="FF000000"),
    bottom=Side(style='thin', color="FF000000")
)
# 表头对齐：居中
HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
# 数据对齐：左对齐
DATA_ALIGN = Alignment(horizontal="left", vertical="center")

# ============================================================
# 常量
# ============================================================

# 报告截止日期（参考模板中第1行的日期）
# 报告截止日期：报告月份最后一天（在 main 中按 report_month 计算）
REPORT_DATE = "2026-06-30"
REPORT_MONTH = "202606"

# 数据源目录
ONES_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
# HANDOVER_DIR 按 report_month 动态构建（见 load_handover_* 函数）
REF_BASE_DIR = Path("/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告")
REPORT_OUTPUT_DIR = Path.home() / ".openclaw" / "data" / "reports"

# Sheet 名称（按顺序）
SHEET_ORDER = [
    "交付效率统计",
    "签约统计",
    "产品-授权&维保统计",
    "签约",
    "POC&提前实施统计",
    "提前实施分事业部统计",
    "POC&提前实施",
    "异常统计",
    "异常台账",
    "交付异常分事业部统计",
    "异常项目",
    "交接统计",
    "确收交接",
    "验收交接",
    "图例",
]


def load_ones_sign_contracts(report_month: str = None) -> pd.DataFrame:
    """加载 ONES 签约项目统计 CSV
    优先按月份查找 {report_month}周报-签约项目统计.csv，否则用默认签约项目统计.csv
    """
    if report_month:
        monthly_path = ONES_DIR / f"{report_month}周报-签约项目统计.csv"
        if monthly_path.exists():
            csv_path = monthly_path
        else:
            csv_path = ONES_DIR / "签约项目统计.csv"
    else:
        csv_path = ONES_DIR / "签约项目统计.csv"
    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
    # 列名对齐：ONES 导出列名和模板列名的差异
    col_rename = {
        "履约项异常/变更备注": "履约项异常/变更类型",  # ONES 叫备注，模板叫类型，同一个东西
        "合同开始日期": "合同起始日期",  # ONES 叫开始日期，模板叫起始日期
    }
    df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})
    print(f"📊 签约项目统计: {len(df)} 行, {len(df.columns)} 列")
    return df


def load_ones_poc(report_month: str = None) -> pd.DataFrame:
    """加载 ONES POC&提前实施统计 CSV
    优先按月份查找 {report_month}周报-POC&提前实施统计.csv，否则用默认 poc_提前实施.csv
    """
    if report_month:
        monthly_path = ONES_DIR / f"{report_month}周报-POC&提前实施统计.csv"
        if monthly_path.exists():
            csv_path = monthly_path
        else:
            csv_path = ONES_DIR / "poc_提前实施.csv"
    else:
        csv_path = ONES_DIR / "poc_提前实施.csv"
    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
    col_rename = {
        "履约项异常/变更备注": "履约项异常/变更类型",
        "合同开始日期": "合同起始日期",
    }
    df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})
    print(f"📊 POC&提前实施统计: {len(df)} 行, {len(df.columns)} 列")
    return df


def load_ones_exceptions(report_month: str = None) -> pd.DataFrame:
    """加载 ONES 异常项目处置 CSV（优先用 55 列完整版，含异常详情字段）"""
    # 优先按月份查找完整版
    if report_month:
        full_path = ONES_DIR / f"{report_month}-签约项目异常处置.csv"
    else:
        full_path = ONES_DIR / "202606-签约项目异常处置.csv"
    if full_path.exists():
        df = pd.read_csv(full_path, dtype=str, encoding="utf-8")
        # 如果有异常影响情况等关键字段，说明是完整版
        if "异常影响情况" in df.columns:
            col_rename = {
                "履约项异常/变更备注": "履约项异常/变更类型",
                "合同开始日期": "合同起始日期",
            }
            df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})
            print(f"📊 异常项目处置（完整版）: {len(df)} 行, {len(df.columns)} 列")
            return df
    
    # 回退：标准版（40 列）
    csv_path = ONES_DIR / "异常处置.csv"
    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
    col_rename = {
        "履约项异常/变更备注": "履约项异常/变更类型",
        "合同开始日期": "合同起始日期",
    }
    df = df.rename(columns={k: v for k, v in col_rename.items() if k in df.columns})
    print(f"📊 异常项目处置: {len(df)} 行, {len(df.columns)} 列")
    return df


def load_handover_revenue(report_month: str = "202606") -> pd.DataFrame:
    """加载企业微信确收交接 CSV"""
    csv_path = REF_BASE_DIR / report_month / f"{report_month}确收凭证交接-确收.csv"
    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
    # 根据 Rex 审核修正验收第 10 列列名
    if "深圳分公司-营销" in df.columns:
        df.rename(columns={"深圳分公司-营销": "销售部门"}, inplace=True)
    
    # 去掉全空列（Rex 要求：忽略 "情况" "0" 等全部为空的列）
    df = df.dropna(axis=1, how="all")
    
    print(f"📊 确收交接: {len(df)} 行 × {len(df.columns)} 列")
    return df


def load_handover_acceptance(report_month: str = "202606") -> pd.DataFrame:
    """加载企业微信验收交接 CSV"""
    csv_path = REF_BASE_DIR / report_month / f"{report_month}确收凭证交接-验收.csv"
    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
    # 根据 Rex 审核修正验收第 10 列列名
    if "深圳分公司-营销" in df.columns:
        df.rename(columns={"深圳分公司-营销": "销售部门"}, inplace=True)
    print(f"📊 验收交接: {len(df)} 行 × {len(df.columns)} 列")
    return df


def _write_df_to_sheet(ws, df: pd.DataFrame, sheet_name: str = None, start_row: int = 1, start_col: int = 1):
    """把 DataFrame 写到指定 worksheet
    格式精确匹配参考手工报表（从 SHEET_FORMAT_MAP 读取精确值）：
    - 表头：微软雅黑 10号 加粗 白色字 + FF2D73BA 蓝色底色 + 居中 + 细边框
    - 数据：微软雅黑 10号 黑色字 + 左对齐 + 细边框
    - 列宽、行高、冻结窗格：全部从参考表精确提取
    """
    from openpyxl.utils import get_column_letter
    
    # 获取该 sheet 的精确格式配置
    fmt = SHEET_FORMAT_MAP.get(sheet_name, None) if sheet_name else None
    
    # 列宽：优先用精确配置，否则自动计算
    column_widths = []
    if fmt and fmt.get('widths'):
        for i in range(len(df.columns)):
            if i < len(fmt['widths']):
                column_widths.append(fmt['widths'][i])
            else:
                column_widths.append(10.83203125)
    else:
        for i, col in enumerate(df.columns):
            if len(df) > 0:
                col_str = df.iloc[:, i].astype(str)
                lengths = col_str.map(lambda x: sum(2 if ord(c) > 127 else 1 for c in str(x)) if x is not None and not pd.isna(x) else 3)
                max_len = max(lengths.max(), len(str(col)))
            else:
                max_len = len(str(col))
            width = max_len + 2 if max_len + 2 >= 8 else 8
            column_widths.append(width)
    
    # 写入表头（带样式）
    for col_idx, (col_name, width) in enumerate(zip(df.columns, column_widths), start_col):
        cell = ws.cell(row=start_row, column=col_idx, value=col_name)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(col_idx)].width = width
    
    # 行高：优先用精确配置
    if fmt and fmt.get('row_heights'):
        for row_num, height in fmt['row_heights'].items():
            ws.row_dimensions[row_num].height = height
    else:
        ws.row_dimensions[start_row].height = 20
    
    # 写入数据（带边框和字体）
    for row_idx, row in enumerate(df.itertuples(index=False), start_row + 1):
        for col_idx, (value, width) in enumerate(zip(row, column_widths), start_col):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = DATA_FONT
            cell.alignment = DATA_ALIGN
            cell.border = THIN_BORDER
    
    # 冻结窗格：精确位置
    if fmt and fmt.get('freeze'):
        ws.freeze_panes = fmt['freeze']
    else:
        ws.freeze_panes = f"A{start_row + 1}"


def build_sign_sheet_df(df_sign_raw: pd.DataFrame, df_exc: pd.DataFrame) -> pd.DataFrame:
    """构建签约 Sheet 完整 DataFrame（83 列）"""
    df = df_sign_raw.copy()
    # Rename 履约项异常/变更备注 → 履约项异常/变更类型 对齐参考表
    if "履约项异常/变更备注" in df.columns:
        df = df.rename(columns={"履约项异常/变更备注": "履约项异常/变更类型"})

    # 对齐人工基准 c38 备注：纯数字+冒号格式（如 "1231："）在人工 Excel 中被解析为
    # 时长（[h]:mm:ss，1231 小时 → timedelta(days=51, seconds=25200)）
    # 仅转换匹配 ^\d+：$ 的值，其余备注原样保留
    if "备注" in df.columns:
        import re as _re
        _hour_re = _re.compile(r'^(\d+)：$')
        def _note_convert(v):
            if isinstance(v, str):
                m = _hour_re.match(v.strip())
                if m:
                    hours = int(m.group(1))
                    from datetime import timedelta as _td
                    return _td(hours=hours)
            return v
        df["备注"] = df["备注"].map(_note_convert)


    # 列 41-44：简单计算列
    df = add_simple_computed_columns(df, sheet_type="sign")

    # 列 45-67：状态相关列
    df = add_status_columns(df, REPORT_DATE)

    # 列 68-76：考核相关列
    df = add_scoring_columns(df)

    # 列 77-79：映射相关列
    df = add_mapping_columns(df)

    # 列 80-83：异常关联列
    df = add_exception_lookup_columns(df, df_exc)

    # 确保列顺序正确（和参考报表一致）
    expected_cols = [
        # 原始 40 列
        "BI履约ID", "最终用户名称", "客户名称", "责任销售（履约项）", "责任销售所属团队",
        "负责人", "所属项目", "项目类型(概览)", "项目状态", "立项日期",
        "基线-预估结项日期", "实际结项日期", "销售合同编号", "合同名称", "直签或代理",
        "合同归档日期", "合同起始日期", "合同结束日期", "交付服务开始日期", "交付服务结束日期",
        "合同验收条款", "验收时点", "验收方式", "标题", "标准产品/服务序号",
        "履约类型", "所属产线", "状态", "履约项异常/变更类型", "履约项优先级",
        "预估交付完成日期", "预算-预估交付完成日期", "交付邮件发送日期",
        "实际服务/授权开始日期", "实际服务/授权结束日期",
        "预估验收完成日期", "预算-预估验收完成日期", "备注", "PMO备注", "ID",
        # 简单计算列 (41-44)
        "项目编号", "统计项目编号", "统计合同编号", "合同归档年度",
        # 状态标记列 (45-54)
        "实施未开始", "义务已拆分", "实施进行中", "实施已完成",
        "交付邮件交接中", "交付邮件已归档", "验收文件交接中", "验收文件已归档",
        "履约项合计", "校验",
        # 统计状态列 (55-67)
        "项目统计状态", "履约项统计状态（即，财报-交付/确收状态）",
        "1：正常交付", "2：应交未交", "3：交付异常", "4：正常验收",
        "5：应验未验", "6：验收异常", "7：正常服务", "8：应结未结", "9：已结项",
        "统计校验", "项目验收状态（即，财报-验收状态）",
        # 考核列 (68-76)
        "基线-预估结项日期（计算后反填）",
        "交付计划准确率“差异”", "交付计划准确率“提前/延后”",
        "交付计划准确率“是否跨月”", "交付计划准确率-考核扣分",
        "按时交付率“差异”", "按时交付率“提前/延后”",
        "按时交付率“是否跨月”", "按时交付率-考核扣分",
        # 映射列 (77-79)
        "项目经理", "项目经理所属部门", "销售团队-统计",
        # 异常关联列 (80-83)
        "异常项目对比", "异常处置状态", "异常影响情况", "交付说明",
    ]

    # 过滤存在的列（有些列可能因为数据缺失没有）
    actual_cols = [c for c in expected_cols if c in df.columns]
    df = df[actual_cols]

    return df


def add_poc_computed_columns(df: pd.DataFrame, df_sign: pd.DataFrame = None, report_date: str = None) -> pd.DataFrame:
    """
    给 POC Sheet 添加计算列，对齐人工基准公式语义（202606 黄金基准）：

      c79 提前实施项目持续周期（天） =IF(H3="POC","",IFS(
            AND(I3="已归档",LEN(M3)>0), MIN(L3-J3, CD3-J3),   # 已归档且有合同：min(实际结项-立项, 关联归档-立项)
            LEN(M3)>0,              CD3-J3,                    # 有合同：关联归档-立项
            I3="已归档",            L3-J3,                     # 已归档：实际结项-立项
            LEN(M3)=0,              $A$1-J3)                    # 无合同：月末-立项
        )，结果 <0 取 0
        H=项目类型(概览) I=项目状态 M=销售合同编号 J=立项日期 L=实际结项日期 CD=c82
      c80 提前实施项目持续周期-统计 =IFS(<=30→1个月内; <=90→3个月内; <=180→6个月内; <=365→1年内; >365→超过1年)
      c81 提前实施项目是否已关联合同 =IF(AND(LEN(M3)>0,H3="提前实施"),"已关联","未关联")
      c82 关联合同归档日期 =VLOOKUP(M3,签约!M:P,4,FALSE)  （销售合同编号→签约表合同归档日期）
      c83 统计所属项目 =IF(COUNTIF(G$2:G2,G3)>0,"",G3)  （所属项目去重）
    """
    from datetime import datetime

    # c82：关联合同归档日期（从签约表按销售合同编号 VLOOKUP）
    if "关联合同归档日期" not in df.columns:
        if df_sign is not None and "销售合同编号" in df_sign.columns and "合同归档日期" in df_sign.columns:
            lookup = df_sign.set_index("销售合同编号")["合同归档日期"]
            # 销售合同编号可能重复，取第一个
            lookup = lookup[~lookup.index.duplicated(keep="first")]
            # 转换为 datetime（因为 pandas 构造 df 时把 datetime 转成字符串了）
            def _parse_dt(v):
                if not v or pd.isna(v):
                    return v
                try:
                    return pd.to_datetime(str(v)[:10])
                except:
                    return v
            lookup = lookup.apply(_parse_dt)
            # 人工语义：空销售合同编号 → #N/A（VLOOKUP 空 criteria）；有合同未命中 → #N/A
            df["关联合同归档日期"] = df["销售合同编号"].map(
                lambda x: (lookup.get(x, "#N/A") if x in lookup.index else "#N/A")
                if pd.notna(x) and str(x).strip() != "" else "#N/A"
            )
        else:
            df["关联合同归档日期"] = "#N/A"

    # c79：提前实施项目持续周期（天）
    def _parse_dt(v):
        if not v or pd.isna(v):
            return None
        try:
            return datetime.strptime(str(v)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    def _calc_duration(row):
        proj_type = str(row.get("项目类型(概览)", "") or "")
        # POC 类型项目 c79 为空，所以 return None
        if proj_type == "POC":
            return None
        proj_status = str(row.get("项目状态", "") or "")
        contract = str(row.get("销售合同编号", "") or "")
        cd_raw = row.get("关联合同归档日期", "")
        # 对齐人工语义：销售合同编号非空，但关联合同归档日期是 #N/A → 结果也是 #N/A
        if contract and str(cd_raw) == "#N/A":
            return "#N/A"
        j_dt = _parse_dt(row.get("立项日期", ""))
        l_dt = _parse_dt(row.get("实际结项日期", ""))
        cd_dt = _parse_dt(cd_raw)
        if report_date:
            a1_dt = _parse_dt(report_date)
        else:
            a1_dt = None
        # 逐个 IFS 分支
        if proj_status == "已归档" and contract:
            cands = []
            if l_dt:
                cands.append((l_dt - j_dt).days if j_dt else None)
            if cd_dt:
                cands.append((cd_dt - j_dt).days if j_dt else None)
            days = min([c for c in cands if c is not None]) if cands else None
        elif contract:
            days = (cd_dt - j_dt).days if (cd_dt and j_dt) else None
        elif proj_status == "已归档":
            days = (l_dt - j_dt).days if (l_dt and j_dt) else None
        else:
            days = (a1_dt - j_dt).days if (a1_dt and j_dt) else None
        if days is None:
            return ""
        return max(days, 0)

    df["提前实施项目持续周期（天）"] = df.apply(_calc_duration, axis=1)

    # c80：分档
    def _duration_bucket(days):
        # 对齐人工语义：如果 days 是 #N/A，返回 #N/A
        if str(days) == "#N/A":
            return "#N/A"
        # Excel 对空值比较，空 > 365 恒真，所以空值返回"超过1年"对齐人工
        if days is None or pd.isna(days) or (isinstance(days, str) and days == ""):
            return "超过1年"
        try:
            d = int(float(days))
        except (ValueError, TypeError):
            return "超过1年"
        if d <= 30:
            return "1个月内"
        elif d <= 90:
            return "3个月内"
        elif d <= 180:
            return "6个月内"
        elif d <= 365:
            return "1年内"
        else:
            return "超过1年"

    df["提前实施项目持续周期-统计"] = df["提前实施项目持续周期（天）"].apply(
        lambda x: _duration_bucket(x)
    )

    # c81：IF(AND(LEN(销售合同编号)>0, 项目类型=提前实施), "已关联", "未关联")
    def _linked(row):
        contract = str(row.get("销售合同编号", "") or "")
        proj_type = str(row.get("项目类型(概览)", "") or "")
        if len(contract) > 0 and proj_type == "提前实施":
            return "已关联"
        return "未关联"

    df["提前实施项目是否已关联合同"] = df.apply(_linked, axis=1)

    # c83：统计所属项目 —— 所属项目去重（上方已出现则空）
    seen = set()
    dedup = []
    for v in df["所属项目"]:
        sv = str(v) if pd.notna(v) else ""
        if sv and sv in seen:
            dedup.append("")
        else:
            dedup.append(v)
            if sv:
                seen.add(sv)
    df["统计所属项目"] = dedup

    return df


def build_poc_sheet_df(df_poc_raw: pd.DataFrame, df_exc: pd.DataFrame,
                       df_sign: pd.DataFrame = None) -> pd.DataFrame:
    """构建 POC&提前实施 Sheet 完整 DataFrame（84 列）"""
    df = df_poc_raw.copy()
    # Rename 履约项异常/变更备注 → 履约项异常/变更类型 对齐参考表
    if "履约项异常/变更备注" in df.columns:
        df = df.rename(columns={"履约项异常/变更备注": "履约项异常/变更类型"})


    # 列 41-44：简单计算列
    df = add_simple_computed_columns(df, sheet_type="poc")

    # POC 增加计算列（c79-83，需签约表 VLOOKUP 关联合同归档日期）
    df = add_poc_computed_columns(df, df_sign, REPORT_DATE)

    # 列 45-67：状态相关列
    df = add_status_columns(df, REPORT_DATE)

    # 列 68-76：考核相关列
    df = add_scoring_columns(df)

    # 列 77-78：映射列（项目经理所属部门、销售团队-统计）
    df = add_mapping_columns(df)

    # c84 POC 工时合计：按统计所属项目（完整【SSXM-...】名称）匹配工时文件
    # 人工语义：=IF(LEN(CE3)>0,IF(ISNA(VLOOKUP(CE3,按项目汇总!A:B,2,FALSE)),0,VLOOKUP(...)),"")
    #   → 统计所属项目为空 → ""；有项目未命中 → 0；命中 → 工时数
    poc_hours = get_poc_project_hours()
    if not poc_hours.empty:
        # 避免 merge 时 left 的「项目编号」被 pandas 重命名为 项目编号_x
        hr = poc_hours.rename(columns={"项目编号": "工时项目编号"})
        df = df.merge(hr, left_on="统计所属项目", right_on="工时项目编号", how="left")
        df = df.drop(columns=["工时项目编号"], errors="ignore")
        if "POC项目工时合计（小时）" not in df.columns:
            df["POC项目工时合计（小时）"] = ""
        # 统计所属项目为空 → ""；未命中（merge 后 NaN）→ 0
        hours = df["POC项目工时合计（小时）"]
        proj = df["统计所属项目"]
        df["POC项目工时合计（小时）"] = [
            "" if (pd.isna(p) or str(p).strip() == "") else (0 if pd.isna(h) else h)
            for p, h in zip(proj, hours)
        ]
    else:
        df["POC项目工时合计（小时）"] = ""

    # 确保列顺序正确（和参考报表一致）
    expected_cols = [
        # 原始 40 列
        "BI履约ID", "最终用户名称", "客户名称", "责任销售（履约项）", "责任销售所属团队",
        "负责人", "所属项目", "项目类型(概览)", "项目状态", "立项日期",
        "基线-预估结项日期", "实际结项日期", "销售合同编号", "合同名称", "直签或代理",
        "合同归档日期", "合同起始日期", "合同结束日期", "交付服务开始日期", "交付服务结束日期",
        "合同验收条款", "验收时点", "验收方式", "标题", "标准产品/服务序号",
        "履约类型", "所属产线", "状态", "履约项异常/变更类型", "履约项优先级",
        "预估交付完成日期", "预算-预估交付完成日期", "交付邮件发送日期",
        "实际服务/授权开始日期", "实际服务/授权结束日期",
        "预估验收完成日期", "预算-预估验收完成日期", "备注", "PMO备注", "ID",
        # 简单计算列 (41-44)
        "项目编号", "统计项目编号", "统计合同编号", "合同归档年度",
        # 状态标记列 (45-53)
        "实施未开始", "义务已拆分", "实施进行中", "实施已完成",
        "交付邮件交接中", "交付邮件已归档", "验收文件交接中", "验收文件已归档",
        "履约项合计", "校验",
        # 统计状态列 (55-67)
        "项目统计状态", "履约项统计状态（即，财报-交付/确收状态）",
        "1：正常交付", "2：应交未交", "3：交付异常", "4：正常验收",
        "5：应验未验", "6：验收异常", "7：正常服务", "8：应结未结", "9：已结项",
        "统计校验", "项目验收状态（即，财报-验收状态）",
        # 考核列 (68-76)
        "基线-预估结项日期（计算后反填）",
        "交付计划准确率“差异”", "交付计划准确率“提前/延后”",
        "交付计划准确率“是否跨月”", "交付计划准确率-考核扣分",
        "按时交付率“差异”", "按时交付率“提前/延后”",
        "按时交付率“是否跨月”", "按时交付率-考核扣分",
        # 计算列 (77-83) + POC 工时 (84)，对齐人工基准顺序
        "项目经理所属部门",
        "销售团队-统计",
        "提前实施项目持续周期（天）",
        "提前实施项目持续周期-统计",
        "提前实施项目是否已关联合同",
        "关联合同归档日期",
        "统计所属项目",
        # POC 工时
        "POC项目工时合计（小时）",
    ]

    # 过滤存在的列（有些列可能因为数据缺失没有）
    actual_cols = [c for c in expected_cols if c in df.columns]
    df = df[actual_cols]

    return df


def generate_delivery_report(period: str = "202606") -> Path:
    """生成完整交付月报"""
    global REPORT_DATE, REPORT_MONTH
    report_month = period
    REPORT_MONTH = report_month
    
    # 计算报告月份最后一天作为截止日期
    year = int(report_month[:4])
    month = int(report_month[4:])
    if month == 12:
        next_month = pd.Timestamp(year=year+1, month=1, day=1)
    else:
        next_month = pd.Timestamp(year=year, month=month+1, day=1)
    REPORT_DATE = (next_month - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"\n🚀 开始生成交付月报: {report_month} (截止 {REPORT_DATE})")
    print("=" * 60)

    # 1. 加载原始数据
    print("\n[1/5] 加载原始数据...")
    df_sign = load_ones_sign_contracts(report_month)
    df_poc = load_ones_poc(report_month)
    df_exc = load_ones_exceptions(report_month)
    df_rev = load_handover_revenue(report_month)
    df_acc = load_handover_acceptance(report_month)

    # 2. 创建工作簿
    print("\n[2/5] 创建工作簿...")
    wb = Workbook()
    wb.remove(wb.active)  # 删除默认 sheet

    # 3. 生成明细 Sheet（带完整计算列）
    print("\n[3/5] 生成明细 Sheet (5个)...")

    # --- 签约（83 列）---
    print("  📝 签约: 构建完整 83 列...")
    df_sign_full = build_sign_sheet_df(df_sign, df_exc)
    ws_sign = wb.create_sheet("签约")
    ws_sign.cell(row=1, column=1, value=REPORT_DATE)
    _write_df_to_sheet(ws_sign, df_sign_full, sheet_name="签约", start_row=2)
    print(f"  ✅ 签约: {len(df_sign_full)} 行 × {len(df_sign_full.columns)} 列")

    # --- POC&提前实施（84 列）---
    print("  📝 POC&提前实施: 构建完整 84 列...")
    df_poc_full = build_poc_sheet_df(df_poc, df_exc)
    ws_poc = wb.create_sheet("POC&提前实施")
    ws_poc.cell(row=1, column=1, value=REPORT_DATE)
    _write_df_to_sheet(ws_poc, df_poc_full, sheet_name="POC&提前实施", start_row=2)
    print(f"  ✅ POC&提前实施: {len(df_poc_full)} 行 × {len(df_poc_full.columns)} 列")

    # --- 异常项目 ---
    print("  📝 异常项目: 构建完整 38 列...")
    df_exc_full = build_exception_df(df_exc, df_sign_full)
    ws_exc = wb.create_sheet("异常项目")
    _write_df_to_sheet(ws_exc, df_exc_full, sheet_name="异常项目", start_row=1)
    print(f"  ✅ 异常项目: {len(df_exc_full)} 行 × {len(df_exc_full.columns)} 列")

    # --- 确收交接 ---
    print("  📝 确收交接: 转换 CSV → 23 列...")
    df_rev_full = build_revenue_handover_df(df_rev, period)
    ws_rev = wb.create_sheet("确收交接")
    _write_df_to_sheet(ws_rev, df_rev_full, sheet_name="确收交接", start_row=1)
    print(f"  ✅ 确收交接: {len(df_rev_full)} 行 × {len(df_rev_full.columns)} 列")

    # --- 验收交接 ---
    print("  📝 验收交接: 转换 CSV → 27 列...")
    df_acc_full = build_acceptance_handover_df(df_acc, period)
    ws_acc = wb.create_sheet("验收交接")
    _write_df_to_sheet(ws_acc, df_acc_full, sheet_name="验收交接", start_row=1)
    # 第22列（索引从1开始）列名原来是 "截至目前全部/部分验收.1"，要改成和第16列一样的 "截至目前全部/部分验收"
    # 参考表里两列同名
    ws_acc.cell(row=1, column=22, value="截至目前全部/部分验收")
    print(f"  ✅ 验收交接: {len(df_acc_full)} 行 × {len(df_acc_full.columns)} 列")

    # 4. 统计 Sheet 九个
    print("\n[4/5] 生成统计 Sheet (9个)...")
    
    # 九个统计 Sheet，按参考报表顺序创建
    # 参考报表 Sheet 顺序：
    # 1.交付效率统计  2.签约统计  3.产品-授权&维保统计  4.签约  5.POC&提前实施统计
    # 6.提前实施分事业部统计  7.POC&提前实施  8.异常统计  9.异常台账  10.交付异常分事业部统计
    # 11.异常项目  12.交接统计  13.确收交接  14.验收交接  15.图例
    stat_builders = [
        ("交付效率统计", build_sign_stats),
        ("签约统计", build_sign_stats),
        ("产品-授权&维保统计", build_product_stats),
        ("签约", None),  # 明细已经生成，跳过
        ("POC&提前实施统计", build_poc_stats),
        ("提前实施分事业部统计", build_poc_dept_stats),
        ("POC&提前实施", None),
        ("异常统计", build_abnormal_stats),
        ("异常台账", build_abnormal_ledger),
        ("交付异常分事业部统计", build_abnormal_dept_stats),
        ("异常项目", None),
        ("交接统计", build_handover_stats),
        ("确收交接", None),
        ("验收交接", None),
        ("图例", build_legend),
    ]
    
    for sheet_name, builder in stat_builders:
        if builder is None:
            continue  # 跳过已经生成的明细
        print(f"  📝 生成统计 Sheet: {sheet_name}")
        ws = wb.create_sheet(sheet_name)
        builder(ws)
        print(f"  ✅ {sheet_name}: 已生成")

    # 重排 Sheet 顺序，对齐参考报表
    ref_order = [
        "交付效率统计",
        "签约统计",
        "产品-授权&维保统计",
        "签约",
        "POC&提前实施统计",
        "提前实施分事业部统计",
        "POC&提前实施",
        "异常统计",
        "异常台账",
        "交付异常分事业部统计",
        "异常项目",
        "交接统计",
        "确收交接",
        "验收交接",
        "图例",
    ]
    wb._sheets.sort(key=lambda ws: ref_order.index(ws.title))

    # 5. 保存
    print("\n[5/5] 保存文件...")
    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_OUTPUT_DIR / f"交付月报-{period}-v2.xlsx"
    wb.save(output_path)
    print(f"✅ 已保存到: {output_path}")

    return output_path


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "202606"
    generate_delivery_report(period)
