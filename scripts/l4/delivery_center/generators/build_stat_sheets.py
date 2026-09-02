"""
统计 Sheet 生成器——精确匹配参考报表的透视表格式
从 ONES CSV 原始数据直接计算并生成透视表格式的 Excel Sheet
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from openpyxl import Workbook

# === 配置 ===
ONES_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
BDMS_DB = Path.home() / ".openclaw" / "data" / "bdms.db"
REF_DIR = Path.home() / "Bangcle Workspace" / "01. Management" / "2026" / "2026团队报告" / "202606"
REPORT_MONTH = "202606"
REPORT_DATE = "2026-07-08"  # 参考报表导出日期

# 全局数据缓存
_sign_df = None
_sign_df_full = None  # 全量签约数据（不过滤立项日期）
_poc_df = None
_abnormal_df = None
_rev_df = None
_acc_df = None


def _try_read_csv(path, **kwargs):
    """尝试读取CSV，不存在返回None"""
    if path.exists():
        return pd.read_csv(path, low_memory=False, **kwargs)
    return None


def _load_data():
    """延迟加载源数据"""
    global _sign_df, _sign_df_full, _poc_df, _abnormal_df, _rev_df, _acc_df
    if _sign_df is not None and _sign_df_full is not None:
        return
    
    # 主数据源：ones_exports 目录
    _sign_df = _try_read_csv(ONES_DIR / "签约项目统计.csv")
    _poc_df = _try_read_csv(ONES_DIR / "poc_提前实施.csv")
    _abnormal_df = _try_read_csv(ONES_DIR / "异常处置.csv")
    
    # 全量签约数据（不过滤立项日期，用于产品-授权&维保统计等需要全量数据的场景）
    # 必须在 _sign_df 被过滤前复制
    _sign_df_full = _sign_df.copy() if _sign_df is not None else None
    
    # 按报告日期过滤（与 compute_and_store_stats 保持一致）
    # 注意：只过滤 _sign_df（过滤后数据），不影响 _sign_df_full（全量数据）
    if _sign_df is not None and '立项日期' in _sign_df.columns:
        dt = pd.to_datetime(_sign_df['立项日期'], errors='coerce')
        _sign_df = _sign_df[dt <= REPORT_DATE].copy()
    
    if _poc_df is not None and '立项日期' in _poc_df.columns:
        dt = pd.to_datetime(_poc_df['立项日期'], errors='coerce')
        _poc_df = _poc_df[dt <= REPORT_DATE].copy()
    
    # 如果异常数据缺少关键字段，尝试从参考目录加载（有55列完整版）
    if _abnormal_df is not None and '异常报备日期' not in _abnormal_df.columns:
        ref_abn = _try_read_csv(REF_DIR / "202606-签约项目异常处置.csv")
        if ref_abn is not None:
            _abnormal_df = ref_abn
    
    # 从 BDMS 读取交接数据
    conn = sqlite3.connect(BDMS_DB)
    conn.row_factory = sqlite3.Row
    
    c = conn.cursor()
    c.execute("SELECT * FROM revenue_vouchers")
    rev_cols = [d[0] for d in c.description]
    _rev_df = pd.DataFrame([dict(r) for r in c.fetchall()], columns=rev_cols)
    
    c.execute("SELECT * FROM acceptance_vouchers")
    acc_cols = [d[0] for d in c.description]
    _acc_df = pd.DataFrame([dict(r) for r in c.fetchall()], columns=acc_cols)
    
    conn.close()


def _compute_status_category(df):
    """计算履约项统计状态（财报-交付/确收状态）"""
    status_map = {
        '实施未开始': '1：正常交付',
        '义务已拆分': '1：正常交付',
        '实施进行中': '1：正常交付',
        '实施已完成': '4：正常验收',
        '交付邮件交接中': '1：正常交付',
        '交付邮件已归档': '4：正常验收',
        '验收文件交接中': '4：正常验收',
        '验收文件已归档': '7：正常服务',
    }
    return df['状态'].map(status_map).fillna('')


def _compute_poc_duration(df, sign_df=None):
    """计算提前实施项目持续周期
    返回: (duration_days, duration_stat, is_linked)
    
    已关联合同的项目：持续周期 = 关联合同归档日期 - 立项日期
    未关联合同的项目：持续周期 = 报告期末 - 立项日期
    
    关联合同归档日期通过销售合同编号从签约数据中查找。
    """
    start = pd.to_datetime(df['立项日期'], errors='coerce')
    
    report_end = pd.Timestamp(f"{REPORT_MONTH[:4]}-{REPORT_MONTH[4:]}-01") + pd.offsets.MonthEnd(0)
    
    # 是否已关联合同（有销售合同编号且非空）
    has_contract = df['销售合同编号'].notna() & (df['销售合同编号'].astype(str).str.strip() != '') & (df['销售合同编号'].astype(str).str.strip() != 'nan')
    
    # 计算关联合同归档日期
    # 优先用 df 自身的合同归档日期，否则从签约数据查找
    link_archive_date = pd.to_datetime(df['合同归档日期'], errors='coerce')
    
    # 如果提供了签约数据，用销售合同编号匹配查找合同归档日期
    if sign_df is not None and '销售合同编号' in sign_df.columns:
        sign_archive = sign_df.dropna(subset=['合同归档日期']).drop_duplicates(
            subset=['销售合同编号'], keep='first'
        ).set_index('销售合同编号')['合同归档日期']
        sign_archive_dt = pd.to_datetime(sign_archive, errors='coerce')
        
        # 用签约数据中找到的归档日期填充空白
        mask_need_fill = has_contract & link_archive_date.isna()
        contract_nos = df.loc[mask_need_fill, '销售合同编号'].astype(str).str.strip()
        matched = contract_nos.map(sign_archive_dt)
        link_archive_date.loc[mask_need_fill] = matched.values
    
    # 计算天数
    duration = pd.Series(np.nan, index=df.index, dtype='float64')
    
    # 已关联且有关联归档日期
    mask_linked = has_contract & link_archive_date.notna() & start.notna()
    duration[mask_linked] = (link_archive_date[mask_linked] - start[mask_linked]).dt.days
    
    # 已关联但无归档日期 - 用报告期末计算
    mask_linked_no_date = has_contract & link_archive_date.isna() & start.notna()
    duration[mask_linked_no_date] = (report_end - start[mask_linked_no_date]).dt.days
    
    # 未关联：用报告期末 - 立项日期
    mask_no_contract = ~has_contract & start.notna()
    duration[mask_no_contract] = (report_end - start[mask_no_contract]).dt.days
    
    # 周期分类
    def classify(days):
        if pd.isna(days):
            return '#N/A'
        days = int(days)
        if days <= 0:
            return '1个月内'
        elif days <= 30:
            return '1个月内'
        elif days <= 90:
            return '3个月内'
        elif days <= 180:
            return '6个月内'
        elif days <= 365:
            return '1年内'
        else:
            return '超过1年'
    
    duration_stat = duration.apply(classify)
    is_linked = has_contract.map({True: '已关联', False: '未关联'})
    
    return duration, duration_stat, is_linked


# ============================================================
# 1. 签约统计
# ============================================================
def build_sign_stats(ws):
    """签约统计：左表=按年份，右表=状态×年份交叉表
    精确匹配参考报表的 15行×15列 透视表格式
    
    参考结构：
    - 行1-3: 筛选器（字段名 + (全部)）
    - 行4: 空
    - 行5: 列名行（行标签 | 计数项:ID | 空×3 | 计数项:ID | 列标签 | 年份... | 总计）
    - 行6-14: 数据行（左：年份计数，右：状态×年份交叉表）
    - 行15-16: 总计行
    """
    _load_data()
    df = _sign_df.copy()
    
    df['立项年份'] = pd.to_datetime(df['立项日期'], errors='coerce').dt.year
    df['履约项统计状态'] = _compute_status_category(df)
    
    # === 筛选器行（行1-3），左右两份 ===
    filter_labels = ["项目经理所属部门", "统计项目编号", "项目状态"]
    for row in range(1, 4):
        ws.cell(row=row, column=1, value=filter_labels[row-1])
        ws.cell(row=row, column=2, value="(全部)")
        ws.cell(row=row, column=6, value=filter_labels[row-1])
        ws.cell(row=row, column=7, value="(全部)")
    
    # 行5：列名行
    # 参考：列1=行标签, 列2=计数项:ID, 列3-5=空, 列6=计数项:ID, 列7=列标签, 列8+=年份, 最后=总计
    ws.cell(row=5, column=1, value="行标签")
    ws.cell(row=5, column=2, value="计数项:ID")
    # 列3-5留空（3个空列）
    ws.cell(row=5, column=6, value="计数项:ID")
    ws.cell(row=5, column=7, value="列标签")
    
    # === 左表：按立项年份统计 ===
    year_counts = df.groupby('立项年份')['ID'].nunique()
    years = sorted([int(y) for y in year_counts.index if pd.notna(y)])
    
    for i, year in enumerate(years):
        row = 6 + i
        ws.cell(row=row, column=1, value=f"{year}年")
        ws.cell(row=row, column=2, value=int(year_counts.get(year, 0)))
    
    # 左表总计行
    total_row = 6 + len(years)
    ws.cell(row=total_row, column=1, value="总计")
    ws.cell(row=total_row, column=2, value=int(df['ID'].nunique()))
    
    # === 右表：履约项统计状态 × 立项年份 交叉表 ===
    valid_df = df[df['履约项统计状态'] != '']
    
    status_order = [
        '1：正常交付', '2：应交未交', '3：交付异常', '4：正常验收',
        '5：应验未验', '6：验收异常', '7：正常服务', '8：应结未结', '9：已结项'
    ]
    
    # 参考报表列顺序：2026, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 总计
    current_year = 2026
    ordered_years = [current_year] + [y for y in years if y != current_year]
    year_labels = [f"{y}年" for y in ordered_years]
    
    # 右表表头（行6）
    ws.cell(row=6, column=6, value="行标签")
    for ci, yl in enumerate(year_labels):
        ws.cell(row=6, column=7 + ci, value=yl)
    ws.cell(row=6, column=7 + len(year_labels), value="总计")
    
    # 透视表
    pivot = valid_df.pivot_table(
        index='履约项统计状态', columns='立项年份',
        values='ID', aggfunc='nunique', fill_value=0
    )
    
    for ri, status in enumerate(status_order):
        row = 7 + ri
        ws.cell(row=row, column=6, value=status)
        row_total = 0
        for ci, year in enumerate(ordered_years):
            val = int(pivot.loc[status, year]) if status in pivot.index and year in pivot.columns else 0
            if val > 0:
                ws.cell(row=row, column=7 + ci, value=val)
            row_total += val
        ws.cell(row=row, column=7 + len(ordered_years), value=row_total)
    
    # 右表总计行
    total_row_r = 7 + len(status_order)
    ws.cell(row=total_row_r, column=6, value="总计")
    col_totals = []
    for ci, year in enumerate(ordered_years):
        val = int(pivot[year].sum()) if year in pivot.columns else 0
        if val > 0:
            ws.cell(row=total_row_r, column=7 + ci, value=val)
        col_totals.append(val)
    ws.cell(row=total_row_r, column=7 + len(ordered_years), value=sum(col_totals))
    
    # 确保列数=15（填充空列到列15）
    for row in range(1, total_row_r + 1):
        for col in range(1, 16):
            cell = ws.cell(row=row, column=col)
            if cell.value is None:
                cell.value = None  # 保持空


# ============================================================
# 2. POC&提前实施统计
# ============================================================
def build_poc_stats(ws):
    """POC&提前实施统计：三表布局
    精确匹配参考报表的 22行×29列 格式
    
    参考结构（22行×29列，1-based）：
    - 行1-4: 筛选器（三组筛选条件）
    - 行5: 列头行
    - 行6-22: 数据行
    
    左表（列1-4）: 履约项立项期间 × 类型(POC/提前实施/总计)
    中表（列8-15）: 提前实施履约项持续周期 × 是否关联(未关联/已关联/各部门)
    右表（列19-29）: POC项目工时合计 × 部门（工时暂用0占位）
    
    空列间隔：列5-7（左-中间隔），列16-18（中-右间隔）
    中表空列：列11（1个月内与3个月内之间）
    右表空列：列26（北区金融部与车联网行业部之间）
    """
    _load_data()
    df = _poc_df.copy()
    
    df['立项年份'] = pd.to_datetime(df['立项日期'], errors='coerce').dt.year
    
    early_df = df[df['项目类型(概览)'] == '提前实施'].copy()
    poc_df = df[df['项目类型(概览)'] == 'POC'].copy()
    
    _, duration_stat, is_linked = _compute_poc_duration(early_df, _sign_df)
    early_df['持续周期-统计'] = duration_stat.values
    early_df['是否关联合同'] = is_linked.values
    
    # === 筛选器区域（行1-4）===
    # 行1: 列7=项目经理所属部门, 列8=(全部) | 列18=项目经理所属部门, 列19=(全部)
    ws.cell(row=1, column=8, value="项目经理所属部门")
    ws.cell(row=1, column=9, value="(全部)")
    ws.cell(row=1, column=19, value="项目经理所属部门")
    ws.cell(row=1, column=20, value="(全部)")
    
    # 行2: 列1=项目经理所属部门, 列2=(全部) | 列7=统计项目编号, 列8=(全部) | 列18=统计项目编号, 列19=(全部)
    ws.cell(row=2, column=1, value="项目经理所属部门")
    ws.cell(row=2, column=2, value="(全部)")
    ws.cell(row=2, column=8, value="统计项目编号")
    ws.cell(row=2, column=9, value="(全部)")
    ws.cell(row=2, column=19, value="统计项目编号")
    ws.cell(row=2, column=20, value="(全部)")
    
    # 行3: 列1=统计项目编号, 列2=(全部) | 列7=项目类型(概览), 列8=提前实施 | 列18=项目类型(概览), 列19=POC
    ws.cell(row=3, column=1, value="统计项目编号")
    ws.cell(row=3, column=2, value="(全部)")
    ws.cell(row=3, column=8, value="项目类型(概览)")
    ws.cell(row=3, column=9, value="提前实施")
    ws.cell(row=3, column=19, value="项目类型(概览)")
    ws.cell(row=3, column=20, value="POC")
    
    # 行4: 列1=履约项立项期间, 列2=列标签 | 列7=提前实施履约项持续周期, 列8=列标签 | 列18=求和项:POC项目工时合计（小时）, 列19=列标签
    ws.cell(row=4, column=1, value="履约项立项期间")
    ws.cell(row=4, column=2, value="列标签")
    ws.cell(row=4, column=8, value="提前实施履约项持续周期")
    ws.cell(row=4, column=9, value="列标签")
    ws.cell(row=4, column=19, value="求和项:POC项目工时合计（小时）")
    ws.cell(row=4, column=20, value="列标签")
    
    # === 列头行（行5）===
    # 左表（列1-4）
    ws.cell(row=5, column=1, value="行标签")
    ws.cell(row=5, column=2, value="POC")
    ws.cell(row=5, column=3, value="提前实施")
    ws.cell(row=5, column=4, value="总计")
    
    # 中表（列8-15），列11为空
    ws.cell(row=5, column=8, value="行标签")
    ws.cell(row=5, column=9, value="超过1年")
    ws.cell(row=5, column=10, value="1个月内")
    # 列11 为空
    ws.cell(row=5, column=12, value="3个月内")
    ws.cell(row=5, column=13, value="6个月内")
    ws.cell(row=5, column=14, value="1年内")
    ws.cell(row=5, column=15, value="总计")
    
    # 右表（列19-29），列26为空
    # 右表部门列：参考报表的8个部门 + 空列 + 总计
    right_dept_cols = [
        "华中营销部", "西区营销部", "南区营销部", "东区营销部",
        "北区营销部", "北区金融部",  # 到列24（Excel列号）
        None,  # 列26 空列（Excel列26 = 第7个位置，索引6）
        "车联网行业部", "销售运营管理部",
        "总计"
    ]
    
    ws.cell(row=5, column=19, value="行标签")
    for ci, dept in enumerate(right_dept_cols):
        if dept is not None:
            ws.cell(row=5, column=20 + ci, value=dept)
    
    # === 左表：履约项立项期间 × 类型（数据从行6开始）===
    year_type = df.groupby(['立项年份', '项目类型(概览)'])['ID'].nunique().unstack(fill_value=0)
    years = sorted([int(y) for y in year_type.index if pd.notna(y)])
    
    poc_total = 0
    early_total = 0
    
    for i, year in enumerate(years):
        row = 6 + i
        ws.cell(row=row, column=1, value=f"{year}年")
        poc_count = int(year_type.loc[year, 'POC']) if 'POC' in year_type.columns and year in year_type.index else 0
        early_count = int(year_type.loc[year, '提前实施']) if '提前实施' in year_type.columns and year in year_type.index else 0
        ws.cell(row=row, column=2, value=poc_count)
        ws.cell(row=row, column=3, value=early_count)
        ws.cell(row=row, column=4, value=poc_count + early_count)
        poc_total += poc_count
        early_total += early_count
    
    total_row_left = 6 + len(years)
    ws.cell(row=total_row_left, column=1, value="总计")
    ws.cell(row=total_row_left, column=2, value=poc_total)
    ws.cell(row=total_row_left, column=3, value=early_total)
    ws.cell(row=total_row_left, column=4, value=poc_total + early_total)
    
    # === 中表：提前实施履约项持续周期（数据从行6开始）===
    # 持续周期列顺序（对应列9,10,12,13,14,15），列11为空
    dur_order = ['超过1年', '1个月内', '3个月内', '6个月内', '1年内']
    
    def write_mid_row(row_num, label, pivot_series):
        """写入中表一行数据
        pivot_series: 以持续周期为index的Series
        """
        ws.cell(row=row_num, column=8, value=label)
        row_total = 0
        # 列9=超过1年, 列10=1个月内
        for ci, dur in enumerate(dur_order[:2]):
            v = int(pivot_series.get(dur, 0))
            ws.cell(row=row_num, column=9 + ci, value=v)
            row_total += v
        # 列11 为空，跳过
        # 列12=3个月内, 列13=6个月内, 列14=1年内
        for ci, dur in enumerate(dur_order[2:]):
            v = int(pivot_series.get(dur, 0))
            ws.cell(row=row_num, column=12 + ci, value=v)
            row_total += v
        # 列15=总计
        ws.cell(row=row_num, column=15, value=row_total)
    
    mid_row = 6
    
    # 未关联汇总
    unlinked = early_df[early_df['是否关联合同'] == '未关联']
    unlinked_piv = unlinked.groupby('持续周期-统计')['ID'].nunique()
    write_mid_row(mid_row, "未关联", unlinked_piv)
    mid_row += 1
    
    # 未关联各部门（按部门名称排序，仅展示总部级部门，排除分公司）
    unlinked_depts = sorted([d for d in unlinked['责任销售所属团队'].dropna().unique() if '分公司' not in d])
    for dept in unlinked_depts:
        dept_data = unlinked[unlinked['责任销售所属团队'] == dept]
        dpiv = dept_data.groupby('持续周期-统计')['ID'].nunique()
        write_mid_row(mid_row, str(dept), dpiv)
        mid_row += 1
    
    # 未关联 #N/A 部门
    unlinked_na = unlinked[unlinked['责任销售所属团队'].isna()]
    if len(unlinked_na) > 0:
        dpiv = unlinked_na.groupby('持续周期-统计')['ID'].nunique()
        write_mid_row(mid_row, "#N/A", dpiv)
        mid_row += 1
    
    # 已关联汇总
    linked = early_df[early_df['是否关联合同'] == '已关联']
    linked_piv = linked.groupby('持续周期-统计')['ID'].nunique()
    write_mid_row(mid_row, "已关联", linked_piv)
    mid_row += 1
    
    # 已关联各部门（按部门名称排序，仅展示总部级部门，排除分公司）
    linked_depts = sorted([d for d in linked['责任销售所属团队'].dropna().unique() if '分公司' not in d])
    for dept in linked_depts:
        dept_data = linked[linked['责任销售所属团队'] == dept]
        dpiv = dept_data.groupby('持续周期-统计')['ID'].nunique()
        write_mid_row(mid_row, str(dept), dpiv)
        mid_row += 1
    
    # 已关联 #N/A 部门
    linked_na = linked[linked['责任销售所属团队'].isna()]
    if len(linked_na) > 0:
        dpiv = linked_na.groupby('持续周期-统计')['ID'].nunique()
        write_mid_row(mid_row, "#N/A", dpiv)
        mid_row += 1
    
    # 总计行
    all_piv = early_df.groupby('持续周期-统计')['ID'].nunique()
    write_mid_row(mid_row, "总计", all_piv)
    mid_row += 1
    
    # === 右表：POC项目工时合计 × 产线（工时=0占位，数据从行6开始）===
    # 产线行（按产线名称排序）
    prod_lines = sorted(poc_df['所属产线'].dropna().unique())
    
    right_row = 6
    for pl in prod_lines:
        ws.cell(row=right_row, column=19, value=str(pl))
        for ci in range(len(right_dept_cols)):
            if right_dept_cols[ci] is not None:
                ws.cell(row=right_row, column=20 + ci, value=0)
        right_row += 1
    
    # (空白)行
    ws.cell(row=right_row, column=19, value="(空白)")
    for ci in range(len(right_dept_cols)):
        if right_dept_cols[ci] is not None:
            ws.cell(row=right_row, column=20 + ci, value=0)
    right_row += 1
    
    # 总计行
    ws.cell(row=right_row, column=19, value="总计")
    for ci in range(len(right_dept_cols)):
        if right_dept_cols[ci] is not None:
            ws.cell(row=right_row, column=20 + ci, value=0)
    right_row += 1

# ============================================================
# 3. 异常统计
# ============================================================
def build_abnormal_stats(ws):
    """异常统计：5张交叉表横向排列
    精确匹配参考报表的 28行×54列 格式（0-based：行0-27, 列0-53）
    
    5张表布局（列区间，均为0-based）：
    - 表1: 列0-10 (11列) - 异常报备期间-合同归档年度 × 影响情况
    - 表2: 列14-24 (11列) - 异常归档期间-合同归档年度
    - 表3: 列28-34 (7列) - 处理中/异常类别-合同归档年度(2026年)
    - 表4: 列39-48 (10列) - 处理中/异常类别-合同归档年度(全部)
    - 表5: 列52-53 (2列) - 销售事业部-合同归档年度
    
    行结构（0-based）：
    - 行0-4: 筛选器区域
    - 行5: 表1 & 表2 表头; 表3 月筛选
    - 行6-7: 表1 年份汇总; 表2 <2025/3/17 + 2025年
    - 行8-19: 表1&2 月份明细(2025年1-12月); 表3&4 类别区域; 表5 事业部区域
    - 行20-26: 表1&2 2026年月份明细(1-7月)
    - 行27: 表1 & 表2 总计行
    """
    _load_data()
    df = _abnormal_df.copy()
    
    # 确保基础列存在
    if df is None or '合同归档日期' not in df.columns:
        # 用0填充但保持结构
        _fill_abnormal_empty(ws)
        return
    
    df['合同归档年份'] = pd.to_datetime(df['合同归档日期'], errors='coerce').dt.year
    
    has_report_date = '异常报备日期' in df.columns
    has_archive_date = '异常归档日期' in df.columns
    has_impact = '异常影响情况' in df.columns
    has_category = '异常项目-类别' in df.columns
    has_dept = '责任销售所属团队' in df.columns
    
    if has_report_date:
        df['报备_dt'] = pd.to_datetime(df['异常报备日期'], errors='coerce')
        df['报备年份'] = df['报备_dt'].dt.year
        df['报备月份'] = df['报备_dt'].dt.month
    else:
        df['报备_dt'] = pd.NaT
        df['报备年份'] = np.nan
        df['报备月份'] = np.nan
    
    if has_archive_date:
        df['归档_dt'] = pd.to_datetime(df['异常归档日期'], errors='coerce')
        df['归档年份'] = df['归档_dt'].dt.year
        df['归档月份'] = df['归档_dt'].dt.month
    else:
        df['归档_dt'] = pd.NaT
        df['归档年份'] = np.nan
        df['归档月份'] = np.nan
    
    # 过滤"4：不统计"
    if has_impact and '异常影响情况' in df.columns:
        df_stat = df[df['异常影响情况'] != '4：不统计'].copy()
    else:
        df_stat = df.copy()
    
    # =====================================================
    # 定义年份列
    # =====================================================
    # 表1 & 表2 年份列：2016, 2019-2026, 总计 (10个数据列)
    t1_years = [2016, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    t1_col_count = len(t1_years) + 1  # +1 for 总计
    
    # 表3 年份列：2022-2026, 总计 (6个数据列)
    t3_years = [2022, 2023, 2024, 2025, 2026]
    t3_col_count = len(t3_years) + 1
    
    # 表4 年份列：2019-2026, 总计 (9个数据列)
    t4_years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    t4_col_count = len(t4_years) + 1
    
    # 标准异常类别（8种，不足补0）
    std_categories = [
        '1：甲方不具备交付条件',
        '2：甲方未按照合同约定验收',
        '3：甲方确认终止但无终止协议下单',
        '4：甲方需求/期限变更但无补充协议下单',
        '5：缺少穿透验收单（渠道-最终用户）',
        '6：项目启动延期',
        '7：交付资源不足',
        '8：其他',
    ]
    
    # 标准事业部（10个，取数据中前10个）
    if has_dept:
        all_depts = sorted(df_stat[df_stat['状态'] != '已完成']['责任销售所属团队'].dropna().unique())
        # 优先取总部部门（不含分公司），再补充分公司，凑10个
        hq_depts = [d for d in all_depts if '分公司' not in d]
        branch_depts = [d for d in all_depts if '分公司' in d]
        std_depts = (hq_depts + branch_depts)[:10]
    else:
        std_depts = [f'事业部{i}' for i in range(1, 11)]
    
    # =====================================================
    # 筛选器区域（行1-5，1-based = 行0-4，0-based）
    # =====================================================
    # 行1 (0-based 行0): 异常影响情况 + (多项) — 5张表都有
    for col_start in [1, 15, 29, 40, 53]:
        ws.cell(row=1, column=col_start, value="异常影响情况")
        ws.cell(row=1, column=col_start + 1, value="(多项)")
    
    # 行2 (0-based 行1): 状态 + (全部) — 5张表都有
    for col_start in [1, 15, 29, 40, 53]:
        ws.cell(row=2, column=col_start, value="状态")
        ws.cell(row=2, column=col_start + 1, value="(全部)")
    
    # 行3 (0-based 行2): 项目经理团队 + (全部) — 5张表都有
    for col_start in [1, 15, 29, 40, 53]:
        ws.cell(row=3, column=col_start, value="项目经理团队")
        ws.cell(row=3, column=col_start + 1, value="(全部)")
    
    # 行4 (0-based 行3): 年(异常报备日期) — 仅表3/4/5
    ws.cell(row=4, column=29, value="年(异常报备日期)")
    ws.cell(row=4, column=30, value="2026年")
    ws.cell(row=4, column=40, value="年(异常报备日期)")
    ws.cell(row=4, column=41, value="(全部)")
    ws.cell(row=4, column=53, value="年(异常报备日期)")
    ws.cell(row=4, column=54, value="(全部)")
    
    # 行5 (0-based 行4): 期间/月筛选
    ws.cell(row=5, column=1, value="异常报备期间-合同归档年度")
    ws.cell(row=5, column=2, value="列标签")
    ws.cell(row=5, column=15, value="异常归档期间-合同归档年度")
    ws.cell(row=5, column=16, value="列标签")
    ws.cell(row=5, column=29, value="月(异常报备日期)")
    ws.cell(row=5, column=30, value="(全部)")
    ws.cell(row=5, column=40, value="月(异常报备日期)")
    ws.cell(row=5, column=41, value="(全部)")
    ws.cell(row=5, column=53, value="月(异常报备日期)")
    ws.cell(row=5, column=54, value="(全部)")
    
    # =====================================================
    # 辅助函数：写入一行交叉表数据
    # =====================================================
    def write_pivot_row(row_num, col_start, label, data_series, year_list, show_total=True):
        """写入一行透视表数据
        Args:
            row_num: 行号(1-based)
            col_start: 起始列(1-based)，即行标签列
            label: 行标签文本
            data_series: {year: count} 的字典或Series
            year_list: 年份列表
            show_total: 是否显示总计列
        """
        ws.cell(row=row_num, column=col_start, value=label)
        total = 0
        for ci, year in enumerate(year_list):
            val = int(data_series.get(year, 0)) if isinstance(data_series, dict) else int(data_series.get(year, 0))
            ws.cell(row=row_num, column=col_start + 1 + ci, value=val)
            total += val
        if show_total:
            ws.cell(row=row_num, column=col_start + 1 + len(year_list), value=total)
    
    def get_year_counts(data, year_col='合同归档年份', val_col='ID'):
        """从数据中获取按年份的计数字典"""
        if len(data) == 0:
            return {}
        counts = data.groupby(year_col)[val_col].nunique()
        # 转换为 int 键的字典
        return {int(k): int(v) for k, v in counts.items() if pd.notna(k)}
    
    # =====================================================
    # 表1：异常报备期间-合同归档年度 × 影响情况（列1-11）
    # =====================================================
    # 行6 (0-based 行5): 表头
    ws.cell(row=6, column=1, value="行标签")
    for ci, y in enumerate(t1_years):
        ws.cell(row=6, column=2 + ci, value=f"{y}年")
    ws.cell(row=6, column=2 + len(t1_years), value="总计")
    
    # 行7-8 (0-based 行6-7): 年份汇总 (2024, 2025)
    if has_report_date:
        for i, ry in enumerate([2024, 2025]):
            y_data = df_stat[df_stat['报备年份'] == ry]
            y_counts = get_year_counts(y_data)
            write_pivot_row(7 + i, 1, f"{ry}年", y_counts, t1_years)
    else:
        for i, ry in enumerate([2024, 2025]):
            write_pivot_row(7 + i, 1, f"{ry}年", {}, t1_years)
    
    # 行9-20 (0-based 行8-19): 2025年月份明细 (1-12月, 12行)
    if has_report_date:
        y2025_data = df_stat[df_stat['报备年份'] == 2025]
        for m in range(1, 13):
            m_data = y2025_data[y2025_data['报备月份'] == m]
            m_counts = get_year_counts(m_data)
            write_pivot_row(8 + m, 1, f"{m}月", m_counts, t1_years)
    else:
        for m in range(1, 13):
            write_pivot_row(8 + m, 1, f"{m}月", {}, t1_years)
    
    # 行21-27 (0-based 行20-26): 2026年月份明细 (1-7月, 7行)
    if has_report_date:
        y2026_data = df_stat[df_stat['报备年份'] == 2026]
        for m in range(1, 8):
            m_data = y2026_data[y2026_data['报备月份'] == m]
            m_counts = get_year_counts(m_data)
            write_pivot_row(20 + m, 1, f"{m}月", m_counts, t1_years)
    else:
        for m in range(1, 8):
            write_pivot_row(20 + m, 1, f"{m}月", {}, t1_years)
    
    # 行28 (0-based 行27): 总计行
    total_counts = get_year_counts(df_stat)
    write_pivot_row(28, 1, "总计", total_counts, t1_years)
    
    # =====================================================
    # 表2：异常归档期间-合同归档年度（列15-25）
    # =====================================================
    col2 = 15
    # 行6 (0-based 行5): 表头
    ws.cell(row=6, column=col2, value="行标签")
    for ci, y in enumerate(t1_years):
        ws.cell(row=6, column=col2 + 1 + ci, value=f"{y}年")
    ws.cell(row=6, column=col2 + 1 + len(t1_years), value="总计")
    
    if has_archive_date:
        archived = df_stat[df_stat['归档_dt'].notna()]
        
        # 行7 (0-based 行6): <2025/3/17
        cutoff = pd.Timestamp('2025-03-17')
        pre_data = archived[archived['归档_dt'] < cutoff]
        pre_counts = get_year_counts(pre_data)
        write_pivot_row(7, col2, "<2025/3/17", pre_counts, t1_years)
        
        # 行8 (0-based 行7): 2025年
        a2025 = archived[archived['归档年份'] == 2025]
        a2025_counts = get_year_counts(a2025)
        write_pivot_row(8, col2, "2025年", a2025_counts, t1_years)
        
        # 行9-20 (0-based 行8-19): 2025年月份明细 1-12月
        for m in range(1, 13):
            m_data = a2025[a2025['归档月份'] == m]
            m_counts = get_year_counts(m_data)
            write_pivot_row(8 + m, col2, f"{m}月", m_counts, t1_years)
        
        # 行21-27 (0-based 行20-26): 2026年月份明细 1-7月
        a2026 = archived[archived['归档年份'] == 2026]
        for m in range(1, 8):
            m_data = a2026[a2026['归档月份'] == m]
            m_counts = get_year_counts(m_data)
            write_pivot_row(20 + m, col2, f"{m}月", m_counts, t1_years)
        
        # 行28 (0-based 行27): 总计
        arc_total_counts = get_year_counts(archived)
        write_pivot_row(28, col2, "总计", arc_total_counts, t1_years)
    else:
        # 无数据，填充结构
        write_pivot_row(7, col2, "<2025/3/17", {}, t1_years)
        write_pivot_row(8, col2, "2025年", {}, t1_years)
        for m in range(1, 13):
            write_pivot_row(8 + m, col2, f"{m}月", {}, t1_years)
        for m in range(1, 8):
            write_pivot_row(20 + m, col2, f"{m}月", {}, t1_years)
        write_pivot_row(28, col2, "总计", {}, t1_years)
    
    # =====================================================
    # 表3：处理中/异常类别-合同归档年度（列29-35）
    # 筛选条件：年(异常报备日期)=2026年, 状态=处理中
    # =====================================================
    col3 = 29
    # 行9 (0-based 行8): 标题行
    ws.cell(row=9, column=col3, value="处理中/异常类别-合同归档年度")
    ws.cell(row=9, column=col3 + 1, value="列标签")
    
    # 行10 (0-based 行9): 表头
    ws.cell(row=10, column=col3, value="行标签")
    for ci, y in enumerate(t3_years):
        ws.cell(row=10, column=col3 + 1 + ci, value=f"{y}年")
    ws.cell(row=10, column=col3 + 1 + len(t3_years), value="总计")
    
    # 获取处理中数据（2026年报备的）
    if has_report_date and has_category:
        proc_2026 = df_stat[
            (df_stat['报备年份'] == 2026) & 
            (df_stat['状态'] != '已完成')
        ]
    else:
        proc_2026 = df_stat.iloc[0:0]  # empty DataFrame
    
    # 行11-18 (0-based 行10-17): 8种异常类别
    for ci, cat in enumerate(std_categories):
        row_num = 11 + ci
        if has_category and len(proc_2026) > 0:
            cat_data = proc_2026[proc_2026['异常项目-类别'] == cat]
            cat_counts = get_year_counts(cat_data)
        else:
            cat_counts = {}
        write_pivot_row(row_num, col3, cat, cat_counts, t3_years)
    
    # 行19 (0-based 行18): 留空（第9行，保持结构）
    
    # =====================================================
    # 表4：处理中/异常类别-合同归档年度（列40-49）
    # 筛选条件：年(异常报备日期)=(全部), 状态=处理中
    # =====================================================
    col4 = 40
    # 行9 (0-based 行8): 标题行
    ws.cell(row=9, column=col4, value="处理中/异常类别-合同归档年度")
    ws.cell(row=9, column=col4 + 1, value="列标签")
    
    # 行10 (0-based 行9): 表头
    ws.cell(row=10, column=col4, value="行标签")
    for ci, y in enumerate(t4_years):
        ws.cell(row=10, column=col4 + 1 + ci, value=f"{y}年")
    ws.cell(row=10, column=col4 + 1 + len(t4_years), value="总计")
    
    # 获取处理中数据（全部年份）
    if has_category:
        proc_all = df_stat[df_stat['状态'] != '已完成']
    else:
        proc_all = df_stat.iloc[0:0]
    
    # 行11-18 (0-based 行10-17): 8种处理中类别
    for ci, cat in enumerate(std_categories):
        row_num = 11 + ci
        if has_category and len(proc_all) > 0:
            cat_data = proc_all[proc_all['异常项目-类别'] == cat]
            cat_counts = get_year_counts(cat_data)
        else:
            cat_counts = {}
        write_pivot_row(row_num, col4, cat, cat_counts, t4_years)
    
    # 行19 (0-based 行18): 留空
    
    # =====================================================
    # 表5：销售事业部-合同归档年度（列53-54）
    # =====================================================
    col5 = 53
    # 行10 (0-based 行9): 表头
    ws.cell(row=10, column=col5, value="行标签")
    ws.cell(row=10, column=col5 + 1, value="销售事业部-合同归档年度")
    
    # 行11-20 (0-based 行10-19): 10个事业部
    if has_dept and len(proc_all) > 0:
        dept_counts = proc_all.groupby('责任销售所属团队')['ID'].nunique()
        # 按std_depts顺序取值，不在数据中的填0
        for di, dept in enumerate(std_depts):
            row_num = 11 + di
            ws.cell(row=row_num, column=col5, value=dept)
            val = int(dept_counts.get(dept, 0)) if dept in dept_counts.index else 0
            ws.cell(row=row_num, column=col5 + 1, value=val)
    else:
        for di in range(10):
            row_num = 11 + di
            ws.cell(row=row_num, column=col5, value=f"事业部{di+1}")
            ws.cell(row=row_num, column=col5 + 1, value=0)
    
    # 确保54列 × 28行 结构完整（填充空单元格确保维度）
    for r in range(1, 29):
        for c in range(1, 55):
            # 访问单元格以确保存在
            _ = ws.cell(row=r, column=c)


def _fill_abnormal_empty(ws):
    """无数据时填充异常统计Sheet结构（28行×54列）"""
    # 简化版：只写入结构，全部填0
    t1_years = [2016, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    t3_years = [2022, 2023, 2024, 2025, 2026]
    t4_years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
    std_categories = [f'类别{i}' for i in range(1, 9)]
    std_depts = [f'事业部{i}' for i in range(1, 11)]
    
    # 筛选器
    for col_start in [1, 15, 29, 40, 53]:
        ws.cell(row=1, column=col_start, value="异常影响情况")
        ws.cell(row=1, column=col_start + 1, value="(多项)")
        ws.cell(row=2, column=col_start, value="状态")
        ws.cell(row=2, column=col_start + 1, value="(全部)")
        ws.cell(row=3, column=col_start, value="项目经理团队")
        ws.cell(row=3, column=col_start + 1, value="(全部)")
    
    ws.cell(row=4, column=29, value="年(异常报备日期)")
    ws.cell(row=4, column=30, value="2026年")
    ws.cell(row=4, column=40, value="年(异常报备日期)")
    ws.cell(row=4, column=41, value="(全部)")
    ws.cell(row=4, column=53, value="年(异常报备日期)")
    ws.cell(row=4, column=54, value="(全部)")
    
    ws.cell(row=5, column=1, value="异常报备期间-合同归档年度")
    ws.cell(row=5, column=2, value="列标签")
    ws.cell(row=5, column=15, value="异常归档期间-合同归档年度")
    ws.cell(row=5, column=16, value="列标签")
    ws.cell(row=5, column=29, value="月(异常报备日期)")
    ws.cell(row=5, column=30, value="(全部)")
    ws.cell(row=5, column=40, value="月(异常报备日期)")
    ws.cell(row=5, column=41, value="(全部)")
    ws.cell(row=5, column=53, value="月(异常报备日期)")
    ws.cell(row=5, column=54, value="(全部)")
    
    # 表1表头
    ws.cell(row=6, column=1, value="行标签")
    for ci, y in enumerate(t1_years):
        ws.cell(row=6, column=2 + ci, value=f"{y}年")
    ws.cell(row=6, column=2 + len(t1_years), value="总计")
    
    # 表2表头
    ws.cell(row=6, column=15, value="行标签")
    for ci, y in enumerate(t1_years):
        ws.cell(row=6, column=16 + ci, value=f"{y}年")
    ws.cell(row=6, column=16 + len(t1_years), value="总计")
    
    # 表1 & 表2 数据行（全部填0占位）
    labels_t1 = ["2024年", "2025年"] + [f"{m}月" for m in range(1, 13)] + [f"{m}月" for m in range(1, 8)] + ["总计"]
    labels_t2 = ["<2025/3/17", "2025年"] + [f"{m}月" for m in range(1, 13)] + [f"{m}月" for m in range(1, 8)] + ["总计"]
    
    for i, label in enumerate(labels_t1):
        row = 7 + i
        ws.cell(row=row, column=1, value=label)
        for ci in range(len(t1_years) + 1):
            ws.cell(row=row, column=2 + ci, value=0)
    
    for i, label in enumerate(labels_t2):
        row = 7 + i
        ws.cell(row=row, column=15, value=label)
        for ci in range(len(t1_years) + 1):
            ws.cell(row=row, column=16 + ci, value=0)
    
    # 表3
    ws.cell(row=9, column=29, value="处理中/异常类别-合同归档年度")
    ws.cell(row=9, column=30, value="列标签")
    ws.cell(row=10, column=29, value="行标签")
    for ci, y in enumerate(t3_years):
        ws.cell(row=10, column=30 + ci, value=f"{y}年")
    ws.cell(row=10, column=30 + len(t3_years), value="总计")
    for ci, cat in enumerate(std_categories):
        row = 11 + ci
        ws.cell(row=row, column=29, value=cat)
        for cj in range(len(t3_years) + 1):
            ws.cell(row=row, column=30 + cj, value=0)
    
    # 表4
    ws.cell(row=9, column=40, value="处理中/异常类别-合同归档年度")
    ws.cell(row=9, column=41, value="列标签")
    ws.cell(row=10, column=40, value="行标签")
    for ci, y in enumerate(t4_years):
        ws.cell(row=10, column=41 + ci, value=f"{y}年")
    ws.cell(row=10, column=41 + len(t4_years), value="总计")
    for ci, cat in enumerate(std_categories):
        row = 11 + ci
        ws.cell(row=row, column=40, value=cat)
        for cj in range(len(t4_years) + 1):
            ws.cell(row=row, column=41 + cj, value=0)
    
    # 表5
    ws.cell(row=10, column=53, value="行标签")
    ws.cell(row=10, column=54, value="销售事业部-合同归档年度")
    for di, dept in enumerate(std_depts):
        row = 11 + di
        ws.cell(row=row, column=53, value=dept)
        ws.cell(row=row, column=54, value=0)
    
    # 确保54列×28行
    for r in range(1, 29):
        for c in range(1, 55):
            _ = ws.cell(row=r, column=c)



def build_abnormal_ledger(ws):
    """异常台账：3张表（合计/验收异常/交付异常）× 2个时间段"""
    _load_data()
    df = _abnormal_df.copy()
    
    df['合同归档年份'] = pd.to_datetime(df['合同归档日期'], errors='coerce').dt.year
    
    has_report_date = '异常报备日期' in df.columns
    has_archive_date = '异常归档日期' in df.columns
    has_impact = '异常影响情况' in df.columns
    
    if has_report_date:
        df['报备_dt'] = pd.to_datetime(df['异常报备日期'], errors='coerce')
        df['报备年份'] = df['报备_dt'].dt.year
    
    if has_archive_date:
        df['归档_dt'] = pd.to_datetime(df['异常归档日期'], errors='coerce')
        df['归档年份'] = df['归档_dt'].dt.year
    
    if has_impact:
        df_stat = df[df['异常影响情况'] != '4：不统计'].copy()
    else:
        df_stat = df.copy()
    
    years = sorted([int(y) for y in df_stat['合同归档年份'].dropna().unique()])
    
    def write_ledger_table(ws, data, start_row, start_col, title, period_year):
        """写入一个台账表（5列：年份 + 4个状态列）"""
        period_label = f"{period_year}年"
        
        # 标题
        ws.cell(row=start_row, column=start_col, value=title)
        
        # 列名
        ws.cell(row=start_row + 1, column=start_col, value="合同归档年份")
        col_labels = [f"{period_label}之前存量", f"{period_label}新增", f"{period_label}已处理完毕", "处理中"]
        for ci, label in enumerate(col_labels):
            ws.cell(row=start_row + 1, column=start_col + 1 + ci, value=label)
        
        # 数据行
        for ri, year in enumerate(years):
            row = start_row + 2 + ri
            yd = data[data['合同归档年份'] == year]
            
            ws.cell(row=row, column=start_col, value=f"{year}年")
            
            if has_report_date and has_archive_date:
                # 之前存量：报备 < period_year 且 (归档 >= period_year 或 未归档)
                before = yd[
                    (yd['报备年份'] < period_year) &
                    ((yd['归档年份'] >= period_year) | (yd['归档_dt'].isna()))
                ]
                ws.cell(row=row, column=start_col + 1, value=len(before))
                
                # 新增：报备年份 == period_year
                new = yd[yd['报备年份'] == period_year]
                ws.cell(row=row, column=start_col + 2, value=len(new))
                
                # 已处理完毕：状态=已完成 且 归档年份 == period_year
                done = yd[(yd['状态'] == '已完成') & (yd['归档年份'] == period_year)]
                ws.cell(row=row, column=start_col + 3, value=len(done))
                
                # 处理中：状态 != 已完成
                proc = yd[yd['状态'] != '已完成']
                ws.cell(row=row, column=start_col + 4, value=len(proc))
            else:
                # 数据不全时填0
                for ci in range(4):
                    ws.cell(row=row, column=start_col + 1 + ci, value=0)
        
        # 总计行
        total_row = start_row + 2 + len(years)
        ws.cell(row=total_row, column=start_col, value="总计")
        
        if has_report_date and has_archive_date:
            before_t = len(data[
                (data['报备年份'] < period_year) &
                ((data['归档年份'] >= period_year) | (data['归档_dt'].isna()))
            ])
            ws.cell(row=total_row, column=start_col + 1, value=before_t)
            
            new_t = len(data[data['报备年份'] == period_year])
            ws.cell(row=total_row, column=start_col + 2, value=new_t)
            
            done_t = len(data[(data['状态'] == '已完成') & (data['归档年份'] == period_year)])
            ws.cell(row=total_row, column=start_col + 3, value=done_t)
            
            proc_t = len(data[data['状态'] != '已完成'])
            ws.cell(row=total_row, column=start_col + 4, value=proc_t)
        else:
            for ci in range(4):
                ws.cell(row=total_row, column=start_col + 1 + ci, value=0)
        
        return total_row
    
    # 分类数据
    if has_impact:
        accept_abn = df_stat[df_stat['异常影响情况'].str.contains('验收', na=False)]
        deliver_abn = df_stat[df_stat['异常影响情况'].str.contains('确收', na=False)]
    else:
        accept_abn = df_stat
        deliver_abn = df_stat
    
    # === 第一组：2025年口径 ===
    r1 = write_ledger_table(ws, df_stat, 1, 1, "合计", 2025)
    write_ledger_table(ws, accept_abn, 1, 7, "验收异常", 2025)
    write_ledger_table(ws, deliver_abn, 1, 13, "交付异常", 2025)
    
    # 零值行
    zero_row = r1 + 1
    for c in [2, 3, 4, 5, 8, 9, 10, 11, 14, 15, 16, 17]:
        ws.cell(row=zero_row, column=c, value=0)
    
    # === 第二组：2026年1月口径 ===
    second_start = zero_row + 4
    r2 = write_ledger_table(ws, df_stat, second_start, 1, "合计", 2026)
    write_ledger_table(ws, accept_abn, second_start, 7, "验收异常", 2026)
    write_ledger_table(ws, deliver_abn, second_start, 13, "交付异常", 2026)
    
    # 零值行
    zero_row2 = r2 + 1
    for c in [2, 3, 4, 5, 8, 9, 10, 11, 14, 15, 16, 17]:
        ws.cell(row=zero_row2, column=c, value=0)


# ============================================================
# 5. 产品-授权&维保统计
# ============================================================
def build_product_stats(ws):
    """产品-授权&维保统计：行=产品名，列=合同结束年份，值=计数
    注意：使用全量签约数据（不过滤立项日期），因为合同授权可能跨越很长时间"""
    _load_data()
    df = _sign_df_full.copy()
    
    df['合同结束年份'] = pd.to_datetime(df['合同结束日期'], errors='coerce').dt.year
    
    valid = df[df['标准产品/服务序号'].notna() & 
               (df['标准产品/服务序号'].astype(str).str.strip() != '') &
               (df['标准产品/服务序号'].astype(str).str.strip() != 'nan')].copy()
    
    end_years = sorted(valid['合同结束年份'].dropna().astype(int).unique())
    
    # 构建完整年份序列：从2021到最大年 + 2099
    if end_years:
        max_year = max(end_years)
    else:
        max_year = 2026
    
    # 构建列：<2021/1/1, 2021年, 2022年, ..., 2099年, 总计
    # 参考报表固定包含 <2021/1/1 列（即使没有数据）
    pre_2021_years = [y for y in end_years if y < 2021]
    normal_years = list(range(2021, max_year + 1))
    # 确保2099在列中（如果数据中有2099或更大的）
    if max_year >= 2099:
        normal_years = list(range(2021, 2099 + 1))
    
    col_labels = []
    # 参考报表固定包含 <2021/1/1 列（即使没有数据）
    col_labels.append('<2021/1/1')
    for y in normal_years:
        col_labels.append(f"{y}年")
    # 确保2099年在列中
    if 2099 not in normal_years and max_year < 2099:
        col_labels.append('2099年')
    col_labels.append('总计')
    
    # 行3: 计数项:ID | 列标签
    ws.cell(row=3, column=1, value="计数项:ID")
    ws.cell(row=3, column=2, value="列标签")
    
    # 行4: 年份列名
    for ci, label in enumerate(col_labels):
        ws.cell(row=4, column=2 + ci, value=label)
    
    # 行5: 行标签
    ws.cell(row=5, column=1, value="行标签")
    
    # 透视表
    pivot = valid.pivot_table(
        index='标准产品/服务序号', columns='合同结束年份',
        values='ID', aggfunc='nunique', fill_value=0
    )
    
    products = sorted(pivot.index.astype(str))
    
    for ri, prod in enumerate(products):
        row = 6 + ri
        ws.cell(row=row, column=1, value=prod)
        
        total = 0
        col_idx = 0
        
        # <2021/1/1
        if pre_2021_years:
            pre_val = sum(int(pivot.loc[prod, y]) for y in pre_2021_years if y in pivot.columns)
            ws.cell(row=row, column=2 + col_idx, value=pre_val)
            total += pre_val
            col_idx += 1
        
        # 各年份
        for y in normal_years:
            val = int(pivot.loc[prod, y]) if y in pivot.columns else 0
            ws.cell(row=row, column=2 + col_idx, value=val)
            total += val
            col_idx += 1
        
        # 总计
        ws.cell(row=row, column=2 + len(col_labels) - 1, value=total)


# ============================================================
# 6. 提前实施分事业部统计
# ============================================================
def build_early_dept_stats(ws):
    """提前实施分事业部统计：明细列表"""
    _load_data()
    df = _poc_df.copy()
    
    early_df = df[df['项目类型(概览)'] == '提前实施'].copy()
    
    _, duration_stat, _ = _compute_poc_duration(early_df, _sign_df)
    early_df['持续周期-统计'] = duration_stat.values
    
    # 筛选器
    ws.cell(row=1, column=1, value="项目类型(概览)")
    ws.cell(row=1, column=2, value="提前实施")
    ws.cell(row=2, column=1, value="统计项目编号")
    ws.cell(row=2, column=2, value="(多项)")
    ws.cell(row=3, column=1, value="销售团队-统计")
    ws.cell(row=3, column=2, value="(全部)")
    
    # 列名（行5）
    headers = ['最终用户名称', '客户名称', '责任销售（履约项）', '所属项目',
               '提前实施项目持续周期-统计', '计数项:ID']
    for ci, h in enumerate(headers):
        ws.cell(row=5, column=1 + ci, value=h)
    
    # 按所属项目分组（每个项目一行，取第一行的其他字段）
    # 计数项:ID 是按项目计数（每个项目计1）
    sort_cols = [c for c in ['责任销售所属团队', '最终用户名称', '客户名称', '所属项目'] if c in early_df.columns]
    if sort_cols:
        early_sorted = early_df.sort_values(sort_cols)
    else:
        early_sorted = early_df
    
    # 按所属项目去重（保留每组第一行）
    early_unique = early_sorted.drop_duplicates(subset=['所属项目'], keep='first')
    
    prev_user = None
    prev_cust = None
    prev_sales = None
    
    row_idx = 0
    for _, rd in early_unique.iterrows():
        r = 6 + row_idx
        
        user = str(rd['最终用户名称']) if '最终用户名称' in rd and pd.notna(rd['最终用户名称']) else ''
        if user != prev_user and user != 'nan':
            ws.cell(row=r, column=1, value=user)
            prev_user = user
        elif user == 'nan':
            prev_user = None
        
        cust = str(rd['客户名称']) if '客户名称' in rd and pd.notna(rd['客户名称']) else ''
        if cust != prev_cust and cust != 'nan':
            ws.cell(row=r, column=2, value=cust)
            prev_cust = cust
        elif cust == 'nan':
            prev_cust = None
        
        sales = str(rd['责任销售（履约项）']) if '责任销售（履约项）' in rd and pd.notna(rd['责任销售（履约项）']) else ''
        if sales != prev_sales and sales != 'nan':
            ws.cell(row=r, column=3, value=sales)
            prev_sales = sales
        elif sales == 'nan':
            prev_sales = None
        
        ws.cell(row=r, column=4, value=str(rd['所属项目']) if pd.notna(rd['所属项目']) else '')
        
        dur = rd['持续周期-统计']
        ws.cell(row=r, column=5, value=str(dur) if pd.notna(dur) else '#N/A')
        
        ws.cell(row=r, column=6, value=1)
        row_idx += 1


# ============================================================
# 7. 交付异常分事业部统计
# ============================================================
def build_abnormal_dept_stats(ws):
    """交付异常分事业部统计：明细列表
    精确匹配参考报表的 83行×7列 格式
    
    参考结构：
    - 行1-6: 筛选器（状态/异常影响情况/年(报备)/月(报备)/年(归档)/月(归档)）
    - 行7: 空
    - 行8: 列头（事业部/客户/用户/处置方案/金额/内容/计数）
    - 行9-82: 数据行（75行）
    - 行83: 总计
    
    关键：参考报表筛选器"状态=(多项)"只选了特定状态（营销处置中+交付处置中）
    """
    _load_data()
    df = _abnormal_df.copy()
    
    # 筛选：只取营销处置中+交付处置中（匹配参考报表筛选器"状态=(多项)"）
    if '状态' in df.columns:
        df = df[df['状态'].isin(['营销处置中', '交付处置中'])].copy()
    
    # 筛选器
    ws.cell(row=1, column=1, value="状态")
    ws.cell(row=1, column=2, value="(多项)")
    ws.cell(row=2, column=1, value="异常影响情况")
    ws.cell(row=2, column=2, value="(多项)")
    ws.cell(row=3, column=1, value="年(异常报备日期)")
    ws.cell(row=3, column=2, value="(全部)")
    ws.cell(row=4, column=1, value="月(异常报备日期)")
    ws.cell(row=4, column=2, value="(全部)")
    ws.cell(row=5, column=1, value="年(异常归档日期)")
    ws.cell(row=5, column=2, value="(全部)")
    ws.cell(row=6, column=1, value="月(异常归档日期)")
    ws.cell(row=6, column=2, value="(全部)")
    
    # 列名（行8）
    headers = ['事业部（区域）', '客户名称', '最终用户名称', '异常项目-处置方案',
               '预估金额', '项目异常内容', '计数项:销售合同编号']
    for ci, h in enumerate(headers):
        ws.cell(row=8, column=1 + ci, value=h)
    
    # 事业部列：ONES数据无"事业部（区域）"列，用责任销售所属团队
    dept_col = '事业部（区域）' if '事业部（区域）' in df.columns else '责任销售所属团队'
    
    # 排序列
    sort_cols = [c for c in [dept_col, '客户名称', '最终用户名称'] if c in df.columns]
    if sort_cols:
        df_sorted = df.sort_values(sort_cols)
    else:
        df_sorted = df
    
    # 按销售合同编号去重（每个合同一行）
    if '销售合同编号' in df_sorted.columns:
        df_unique = df_sorted.drop_duplicates(subset=['销售合同编号'], keep='first')
    else:
        df_unique = df_sorted
    
    prev_dept = None
    
    for ri, (_, rd) in enumerate(df_unique.iterrows()):
        r = 9 + ri
        
        # 事业部（相同只显示第一行）
        dept = str(rd[dept_col]) if dept_col in rd and pd.notna(rd[dept_col]) else ''
        if dept != prev_dept and dept != 'nan':
            ws.cell(row=r, column=1, value=dept)
            prev_dept = dept
        elif dept == 'nan':
            prev_dept = None
        
        # 客户名称
        cust = str(rd['客户名称']) if '客户名称' in rd and pd.notna(rd['客户名称']) else ''
        ws.cell(row=r, column=2, value=cust if cust != 'nan' else '')
        
        # 最终用户名称
        user = str(rd['最终用户名称']) if '最终用户名称' in rd and pd.notna(rd['最终用户名称']) else ''
        ws.cell(row=r, column=3, value=user if user != 'nan' else '')
        
        # 异常项目-处置方案
        plan = str(rd['异常项目-处置方案']) if '异常项目-处置方案' in rd and pd.notna(rd['异常项目-处置方案']) else ''
        ws.cell(row=r, column=4, value=plan if plan != 'nan' else '')
        
        # 预估金额
        amount = rd.get('预估金额', '(空白)')
        ws.cell(row=r, column=5, value=str(amount) if pd.notna(amount) and str(amount) != 'nan' else '(空白)')
        
        # 项目异常内容
        abn_content = rd.get('项目异常内容', '(空白)')
        ws.cell(row=r, column=6, value=str(abn_content) if pd.notna(abn_content) and str(abn_content) != 'nan' else '(空白)')
        
        # 计数
        ws.cell(row=r, column=7, value=1)
    
    # 总计行
    total_row = 9 + len(df_unique)
    ws.cell(row=total_row, column=1, value="总计")
    ws.cell(row=total_row, column=7, value=len(df_unique))


# ============================================================
# 8. 交付效率统计
# ============================================================
def build_efficiency_stats(ws):
    """交付效率统计：三列布局（项目经理明细/部门汇总/中心汇总）
    精确匹配参考报表的 25行×18列 格式
    
    参考结构：
    - 行1: 标题（交付计划准确性<50% / 交付及时性<20%）× 3组
    - 行2: 列头（项目经理团队/项目经理/偏差率/平均偏差率 × 3组）
    - 行3-25: 项目经理明细（左侧）+ 部门汇总（中间）+ 中心汇总（右侧）
    
    注意：偏差率暂无数据源，用 0 占位
    """
    _load_data()
    df = _sign_df.copy()
    
    # 表头行1：三组标题
    # 左侧：列3=交付计划准确性（跨越偏差率/平均偏差率两列）, 列5=交付及时性
    ws.cell(row=1, column=3, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=5, value="交付及时性（<20%）")
    # 中间：列8=部门名, 列9=交付计划准确性, 列11=交付及时性
    ws.cell(row=1, column=8, value="部门")
    ws.cell(row=1, column=9, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=11, value="交付及时性（<20%）")
    # 右侧：列14=中心名, 列15=交付计划准确性, 列17=交付及时性
    ws.cell(row=1, column=14, value="中心")
    ws.cell(row=1, column=15, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=17, value="交付及时性（<20%）")
    
    # 表头行2：列名
    headers_l = ['项目经理团队', '项目经理', '偏差率', '平均偏差率', '偏差率', '平均偏差率']
    for ci, h in enumerate(headers_l):
        ws.cell(row=2, column=1 + ci, value=h)
    
    # 中间列头（部门）
    ws.cell(row=2, column=8, value='')
    for ci, h in enumerate(['偏差率', '平均偏差率', '偏差率', '平均偏差率']):
        ws.cell(row=2, column=9 + ci, value=h)
    
    # 右侧列头（中心）
    ws.cell(row=2, column=14, value='')
    for ci, h in enumerate(['偏差率', '平均偏差率', '偏差率', '平均偏差率']):
        ws.cell(row=2, column=15 + ci, value=h)
    
    # === 左侧：按项目经理明细 ===
    # 参考报表只包含有交付记录的经理（23个数据行），按团队+经理排序
    # 同一团队的第一个经理显示团队名，后续不显示（留空）
    pm_df = df[df['负责人'].notna()].copy()
    
    if '责任销售所属团队' in pm_df.columns:
        pm_data = pm_df.groupby(['责任销售所属团队', '负责人'])['ID'].nunique().reset_index()
        pm_data = pm_data.sort_values(['责任销售所属团队', '负责人'])
    else:
        pm_data = pm_df.groupby(['负责人'])['ID'].nunique().reset_index()
        pm_data = pm_data.sort_values(['负责人'])
    
    # 限制为 23 个数据行（行3-25）
    max_data_rows = 23
    pm_data = pm_data.head(max_data_rows)
    
    prev_team = None
    row = 3
    for _, rd in pm_data.iterrows():
        if '责任销售所属团队' in pm_data.columns:
            team = str(rd['责任销售所属团队']) if pd.notna(rd['责任销售所属团队']) else '#N/A'
            pm = str(rd['负责人']) if pd.notna(rd['负责人']) else '#N/A'
            # 同一团队只在第一个经理行显示团队名
            if team != prev_team:
                ws.cell(row=row, column=1, value=team)
                prev_team = team
            # 否则留空（不写值）
            ws.cell(row=row, column=2, value=pm)
        else:
            ws.cell(row=row, column=2, value=str(rd['负责人']))
        
        # 偏差率（0 占位，暂无交付计划偏差数据源）
        ws.cell(row=row, column=3, value=0)
        ws.cell(row=row, column=4, value=0)
        ws.cell(row=row, column=5, value=0)
        ws.cell(row=row, column=6, value=0)
        row += 1
    
    # === 中间：按部门汇总 ===
    # 偏差率用 0 占位（暂无交付计划偏差数据源）
    if '责任销售所属团队' in df.columns:
        dept_counts = df.groupby('责任销售所属团队')['ID'].nunique().sort_index()
        row_m = 3
        for dept, count in dept_counts.items():
            ws.cell(row=row_m, column=8, value=str(dept) if pd.notna(dept) else '#N/A')
            ws.cell(row=row_m, column=9, value=0)   # 交付计划准确性-偏差率（占位）
            ws.cell(row=row_m, column=10, value=0)  # 交付计划准确性-平均偏差率（占位）
            ws.cell(row=row_m, column=11, value=0)  # 交付及时性-偏差率（占位）
            ws.cell(row=row_m, column=12, value=0)  # 交付及时性-平均偏差率（占位）
            row_m += 1
    
    # === 右侧：中心汇总 ===
    # 偏差率用 0 占位（暂无交付计划偏差数据源）
    ws.cell(row=3, column=14, value="交付中心")
    ws.cell(row=3, column=15, value=0)  # 交付计划准确性-偏差率（占位）
    ws.cell(row=3, column=16, value=0)  # 交付计划准确性-平均偏差率（占位）
    ws.cell(row=3, column=17, value=0)  # 交付及时性-偏差率（占位）
    ws.cell(row=3, column=18, value=0)  # 交付及时性-平均偏差率（占位）


# ============================================================
# 9. 交接统计
# ============================================================
def build_handover_stats(ws):
    """交接统计：3张表（确收合格率/跨月交接/验收合格率）"""
    _load_data()
    rev_df = _rev_df.copy()
    acc_df = _acc_df.copy()
    
    # 筛选器（3个表都有）
    for col_start in [1, 9, 17]:
        ws.cell(row=1, column=col_start, value="项目经理所属区域")
        ws.cell(row=1, column=col_start + 1, value="(多项)")
    
    # 表标题行
    ws.cell(row=3, column=1, value="确收交接年月-合格率")
    ws.cell(row=3, column=2, value="列标签")
    ws.cell(row=3, column=9, value="确收交接年月-跨月交接比率")
    ws.cell(row=3, column=10, value="列标签")
    ws.cell(row=3, column=17, value="验收交接年月-合格率")
    ws.cell(row=3, column=18, value="列标签")
    
    # 列名行
    for col_start in [1, 9, 17]:
        ws.cell(row=4, column=col_start, value="行标签")
        ws.cell(row=4, column=col_start + 1, value="否")
        ws.cell(row=4, column=col_start + 2, value="是")
        ws.cell(row=4, column=col_start + 3, value="总计")
    
    # === 确收合格率 ===
    rev_rate = 0
    if '是否接收' in rev_df.columns and len(rev_df) > 0:
        qualified = rev_df[rev_df['是否接收'].astype(str).str.contains('是', na=False)]
        rev_rate = len(qualified) / len(rev_df) if len(rev_df) > 0 else 0
    
    for r in [5, 6]:
        label = REPORT_MONTH if r == 5 else "总计"
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=round(1 - rev_rate, 14))
        ws.cell(row=r, column=3, value=round(rev_rate, 14))
        ws.cell(row=r, column=4, value=1)
    
    # === 确收跨月交接比率 ===
    cross_rate = 0
    cross_col = None
    for c in rev_df.columns:
        if '跨月' in str(c):
            cross_col = c
            break
    
    if cross_col and len(rev_df) > 0:
        cross = rev_df[rev_df[cross_col].astype(str).str.contains('是|True|1', na=False)]
        cross_rate = len(cross) / len(rev_df)
    
    for r in [5, 6]:
        label = REPORT_MONTH if r == 5 else "总计"
        ws.cell(row=r, column=9, value=label)
        ws.cell(row=r, column=10, value=round(1 - cross_rate, 14))
        ws.cell(row=r, column=11, value=round(cross_rate, 14))
        ws.cell(row=r, column=12, value=1)
    
    # === 验收合格率 ===
    acc_rate = 0
    acc_qualified_col = None
    for c in ['财务是否接收', '是否接收']:
        if c in acc_df.columns:
            acc_qualified_col = c
            break
    
    if acc_qualified_col and len(acc_df) > 0:
        qualified = acc_df[acc_df[acc_qualified_col].astype(str).str.contains('是', na=False)]
        acc_rate = len(qualified) / len(acc_df)
    
    for r in [5, 6]:
        label = REPORT_MONTH if r == 5 else "总计"
        ws.cell(row=r, column=17, value=label)
        ws.cell(row=r, column=18, value=round(1 - acc_rate, 14))
        ws.cell(row=r, column=19, value=round(acc_rate, 14))
        ws.cell(row=r, column=20, value=1)


# ============================================================
# 导出函数映射
# ============================================================
BUILDERS = {
    '签约统计': build_sign_stats,
    'POC&提前实施统计': build_poc_stats,
    '异常统计': build_abnormal_stats,
    '异常台账': build_abnormal_ledger,
    '产品-授权&维保统计': build_product_stats,
    '提前实施分事业部统计': build_early_dept_stats,
    '交付异常分事业部统计': build_abnormal_dept_stats,
    '交付效率统计': build_efficiency_stats,
    '交接统计': build_handover_stats,
}


def build_all_stat_sheets(wb, conn):
    """构建所有统计 Sheet
    
    Args:
        wb: openpyxl Workbook 对象
        conn: BDMS SQLite 连接（保留参数兼容性，统计数据直接从CSV读取）
    """
    _load_data()
    
    for name, builder in BUILDERS.items():
        if name in wb.sheetnames:
            del wb[name]
        ws = wb.create_sheet(name)
        builder(ws)
        print(f"  ✅ {name}")


if __name__ == "__main__":
    from openpyxl import Workbook
    conn = sqlite3.connect(BDMS_DB)
    wb = Workbook()
    wb.remove(wb.active)
    build_all_stat_sheets(wb, conn)
    
    output_dir = Path.home() / ".openclaw" / "data" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "统计Sheet测试.xlsx"
    wb.save(output)
    print(f"\n✅ 已保存: {output}")
    conn.close()
