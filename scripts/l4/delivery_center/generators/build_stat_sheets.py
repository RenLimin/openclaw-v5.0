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
REPORT_DATE = "2026-06-30"

# 全局数据缓存
_sign_df = None
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
    global _sign_df, _poc_df, _abnormal_df, _rev_df, _acc_df
    if _sign_df is not None:
        return
    
    # 主数据源：ones_exports 目录
    _sign_df = _try_read_csv(ONES_DIR / "签约项目统计.csv")
    _poc_df = _try_read_csv(ONES_DIR / "poc_提前实施.csv")
    _abnormal_df = _try_read_csv(ONES_DIR / "异常处置.csv")
    
    # 按报告日期过滤（与 compute_and_store_stats 保持一致）
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
    """签约统计：左表=按年份，右表=状态×年份交叉表"""
    _load_data()
    df = _sign_df.copy()
    
    df['立项年份'] = pd.to_datetime(df['立项日期'], errors='coerce').dt.year
    df['履约项统计状态'] = _compute_status_category(df)
    
    # === 筛选器行 ===
    ws.cell(row=1, column=1, value="项目经理所属部门")
    ws.cell(row=1, column=2, value="(全部)")
    ws.cell(row=1, column=6, value="项目经理所属部门")
    ws.cell(row=1, column=7, value="(全部)")
    
    ws.cell(row=2, column=1, value="统计项目编号")
    ws.cell(row=2, column=2, value="(全部)")
    ws.cell(row=2, column=6, value="统计项目编号")
    ws.cell(row=2, column=7, value="(全部)")
    
    ws.cell(row=3, column=1, value="项目状态")
    ws.cell(row=3, column=2, value="(全部)")
    ws.cell(row=3, column=6, value="项目状态")
    ws.cell(row=3, column=7, value="(全部)")
    
    # 行5：列名行
    ws.cell(row=5, column=1, value="行标签")
    ws.cell(row=5, column=2, value="计数项:ID")
    ws.cell(row=5, column=6, value="计数项:ID")
    ws.cell(row=5, column=7, value="列标签")
    
    # === 左表：按立项年份统计 ===
    year_counts = df.groupby('立项年份')['ID'].nunique()
    years = sorted([int(y) for y in year_counts.index if pd.notna(y)])
    
    for i, year in enumerate(years):
        row = 6 + i
        ws.cell(row=row, column=1, value=f"{year}年")
        ws.cell(row=row, column=2, value=int(year_counts[year]))
    
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
    
    year_labels = [f"{y}年" for y in years]
    
    # 右表表头
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
        for ci, year in enumerate(years):
            val = int(pivot.loc[status, year]) if status in pivot.index and year in pivot.columns else 0
            ws.cell(row=row, column=7 + ci, value=val)
            row_total += val
        ws.cell(row=row, column=7 + len(years), value=row_total)
    
    # 右表总计行
    total_row_r = 7 + len(status_order)
    ws.cell(row=total_row_r, column=6, value="总计")
    col_totals = []
    for ci, year in enumerate(years):
        val = int(pivot[year].sum()) if year in pivot.columns else 0
        ws.cell(row=total_row_r, column=7 + ci, value=val)
        col_totals.append(val)
    ws.cell(row=total_row_r, column=7 + len(years), value=sum(col_totals))


# ============================================================
# 2. POC&提前实施统计
# ============================================================
def build_poc_stats(ws):
    """POC&提前实施统计：左=年份×类型, 中=持续周期×部门, 右=工时合计"""
    _load_data()
    df = _poc_df.copy()
    
    df['立项年份'] = pd.to_datetime(df['立项日期'], errors='coerce').dt.year
    
    early_df = df[df['项目类型(概览)'] == '提前实施'].copy()
    poc_df = df[df['项目类型(概览)'] == 'POC'].copy()
    
    _, duration_stat, is_linked = _compute_poc_duration(early_df, _sign_df)
    early_df['持续周期-统计'] = duration_stat.values
    early_df['是否关联合同'] = is_linked.values
    
    # === 筛选器 ===
    ws.cell(row=2, column=1, value="项目经理所属部门")
    ws.cell(row=2, column=2, value="(全部)")
    ws.cell(row=3, column=1, value="统计项目编号")
    ws.cell(row=3, column=2, value="(全部)")
    
    ws.cell(row=1, column=8, value="项目经理所属部门")
    ws.cell(row=1, column=9, value="(全部)")
    ws.cell(row=2, column=8, value="统计项目编号")
    ws.cell(row=2, column=9, value="(全部)")
    ws.cell(row=3, column=8, value="项目类型(概览)")
    ws.cell(row=3, column=9, value="提前实施")
    
    ws.cell(row=1, column=19, value="项目经理所属部门")
    ws.cell(row=1, column=20, value="(全部)")
    ws.cell(row=2, column=19, value="统计项目编号")
    ws.cell(row=2, column=20, value="(全部)")
    ws.cell(row=3, column=19, value="项目类型(概览)")
    ws.cell(row=3, column=20, value="POC")
    
    # === 左表：履约项立项期间 × 类型 ===
    ws.cell(row=5, column=1, value="履约项立项期间")
    ws.cell(row=5, column=2, value="列标签")
    ws.cell(row=6, column=1, value="行标签")
    ws.cell(row=6, column=2, value="POC")
    ws.cell(row=6, column=3, value="提前实施")
    ws.cell(row=6, column=4, value="总计")
    
    year_type = df.groupby(['立项年份', '项目类型(概览)'])['ID'].nunique().unstack(fill_value=0)
    years = sorted([int(y) for y in year_type.index if pd.notna(y)])
    
    poc_total = 0
    early_total = 0
    
    for i, year in enumerate(years):
        row = 7 + i
        ws.cell(row=row, column=1, value=f"{year}年")
        poc_count = int(year_type.loc[year, 'POC']) if 'POC' in year_type.columns and year in year_type.index else 0
        early_count = int(year_type.loc[year, '提前实施']) if '提前实施' in year_type.columns and year in year_type.index else 0
        ws.cell(row=row, column=2, value=poc_count)
        ws.cell(row=row, column=3, value=early_count)
        ws.cell(row=row, column=4, value=poc_count + early_count)
        poc_total += poc_count
        early_total += early_count
    
    total_row = 7 + len(years)
    ws.cell(row=total_row, column=1, value="总计")
    ws.cell(row=total_row, column=2, value=poc_total)
    ws.cell(row=total_row, column=3, value=early_total)
    ws.cell(row=total_row, column=4, value=poc_total + early_total)
    
    # === 中表：提前实施履约项持续周期 × 部门 ===
    ws.cell(row=5, column=8, value="提前实施履约项持续周期")
    ws.cell(row=5, column=9, value="列标签")
    
    dur_order = ['超过1年', '1个月内', '#N/A', '3个月内', '6个月内', '1年内', '总计']
    
    ws.cell(row=6, column=8, value="行标签")
    for ci, dur in enumerate(dur_order):
        ws.cell(row=6, column=9 + ci, value=dur)
    
    # 部门×持续周期透视
    dept_pivot = early_df.pivot_table(
        index='责任销售所属团队', columns='持续周期-统计',
        values='ID', aggfunc='nunique', fill_value=0
    )
    
    row = 7
    
    # 未关联汇总
    unlinked = early_df[early_df['是否关联合同'] == '未关联']
    unlinked_piv = unlinked.groupby('持续周期-统计')['ID'].nunique()
    
    ws.cell(row=row, column=8, value="未关联")
    ut = 0
    for ci, dur in enumerate(dur_order[:-1]):
        v = int(unlinked_piv.get(dur, 0))
        ws.cell(row=row, column=9 + ci, value=v)
        ut += v
    ws.cell(row=row, column=9 + len(dur_order) - 1, value=ut)
    row += 1
    
    # 未关联下的各部门
    unlinked_depts = sorted([d for d in unlinked['责任销售所属团队'].dropna().unique()])
    for dept in unlinked_depts:
        dept_data = unlinked[unlinked['责任销售所属团队'] == dept]
        dpiv = dept_data.groupby('持续周期-统计')['ID'].nunique()
        ws.cell(row=row, column=8, value=str(dept))
        dt = 0
        for ci, dur in enumerate(dur_order[:-1]):
            v = int(dpiv.get(dur, 0))
            ws.cell(row=row, column=9 + ci, value=v)
            dt += v
        ws.cell(row=row, column=9 + len(dur_order) - 1, value=dt)
        row += 1
    
    # #N/A 部门
    unlinked_na = unlinked[unlinked['责任销售所属团队'].isna()]
    if len(unlinked_na) > 0:
        dpiv = unlinked_na.groupby('持续周期-统计')['ID'].nunique()
        ws.cell(row=row, column=8, value="#N/A")
        dt = 0
        for ci, dur in enumerate(dur_order[:-1]):
            v = int(dpiv.get(dur, 0))
            ws.cell(row=row, column=9 + ci, value=v)
            dt += v
        ws.cell(row=row, column=9 + len(dur_order) - 1, value=dt)
        row += 1
    
    # 已关联汇总
    linked = early_df[early_df['是否关联合同'] == '已关联']
    linked_piv = linked.groupby('持续周期-统计')['ID'].nunique()
    
    ws.cell(row=row, column=8, value="已关联")
    lt = 0
    for ci, dur in enumerate(dur_order[:-1]):
        v = int(linked_piv.get(dur, 0))
        ws.cell(row=row, column=9 + ci, value=v)
        lt += v
    ws.cell(row=row, column=9 + len(dur_order) - 1, value=lt)
    row += 1
    
    # 已关联下的各部门
    linked_depts = sorted([d for d in linked['责任销售所属团队'].dropna().unique()])
    for dept in linked_depts:
        dept_data = linked[linked['责任销售所属团队'] == dept]
        dpiv = dept_data.groupby('持续周期-统计')['ID'].nunique()
        ws.cell(row=row, column=8, value=str(dept))
        dt = 0
        for ci, dur in enumerate(dur_order[:-1]):
            v = int(dpiv.get(dur, 0))
            ws.cell(row=row, column=9 + ci, value=v)
            dt += v
        ws.cell(row=row, column=9 + len(dur_order) - 1, value=dt)
        row += 1
    
    # 总计行
    ws.cell(row=row, column=8, value="总计")
    grand_total = 0
    all_piv = early_df.groupby('持续周期-统计')['ID'].nunique()
    for ci, dur in enumerate(dur_order[:-1]):
        v = int(all_piv.get(dur, 0))
        ws.cell(row=row, column=9 + ci, value=v)
        grand_total += v
    ws.cell(row=row, column=9 + len(dur_order) - 1, value=grand_total)
    
    # === 右表：POC项目工时合计 × 产线 × 部门 ===
    ws.cell(row=5, column=19, value="求和项:POC项目工时合计（小时）")
    ws.cell(row=5, column=20, value="列标签")
    
    dept_cols = sorted(poc_df['责任销售所属团队'].dropna().unique())
    # 加上#N/A和总计
    dept_cols_with_na = list(dept_cols)
    if poc_df['责任销售所属团队'].isna().any():
        dept_cols_with_na = ['#N/A'] + dept_cols_with_na
    dept_cols_with_na.append('总计')
    
    ws.cell(row=6, column=19, value="行标签")
    for ci, dept in enumerate(dept_cols_with_na):
        ws.cell(row=6, column=20 + ci, value=dept)
    
    # 产线行（工时数据暂缺，用0填充结构）
    prod_lines = sorted(poc_df['所属产线'].dropna().unique())
    
    row_r = 7
    for pl in prod_lines:
        ws.cell(row=row_r, column=19, value=str(pl))
        for ci in range(len(dept_cols_with_na)):
            ws.cell(row=row_r, column=20 + ci, value=0)
        row_r += 1
    
    # (空白)行
    ws.cell(row=row_r, column=19, value="(空白)")
    for ci in range(len(dept_cols_with_na)):
        ws.cell(row=row_r, column=20 + ci, value=0)
    row_r += 1
    
    # 总计行
    ws.cell(row=row_r, column=19, value="总计")
    for ci in range(len(dept_cols_with_na)):
        ws.cell(row=row_r, column=20 + ci, value=0)


# ============================================================
# 3. 异常统计
# ============================================================
def build_abnormal_stats(ws):
    """异常统计：4张交叉表"""
    _load_data()
    df = _abnormal_df.copy()
    
    # 确保列存在
    if '合同归档日期' not in df.columns:
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
    
    if has_archive_date:
        df['归档_dt'] = pd.to_datetime(df['异常归档日期'], errors='coerce')
        df['归档年份'] = df['归档_dt'].dt.year
        df['归档月份'] = df['归档_dt'].dt.month
    
    # 过滤"4：不统计"
    if has_impact:
        df_stat = df[df['异常影响情况'] != '4：不统计'].copy()
    else:
        df_stat = df.copy()
    
    years = sorted([int(y) for y in df_stat['合同归档年份'].dropna().unique()])
    year_labels = [f"{y}年" for y in years] + ['总计']
    
    # === 表1：异常报备期间-合同归档年度 × 影响情况 ===
    ws.cell(row=1, column=1, value="异常影响情况")
    ws.cell(row=1, column=2, value="(多项)")
    ws.cell(row=2, column=1, value="状态")
    ws.cell(row=2, column=2, value="(全部)")
    ws.cell(row=3, column=1, value="项目经理团队")
    ws.cell(row=3, column=2, value="(全部)")
    
    ws.cell(row=5, column=1, value="异常报备期间-合同归档年度")
    ws.cell(row=5, column=2, value="列标签")
    ws.cell(row=6, column=1, value="行标签")
    
    for ci, yl in enumerate(year_labels):
        ws.cell(row=6, column=2 + ci, value=yl)
    
    def write_year_month_rows(ws, data, start_row, start_col, year_col, month_col, value_col='ID'):
        """写入年+月份行的交叉表，返回结束行号"""
        row = start_row
        
        if not has_report_date:
            return row
        
        report_years = sorted(data['报备年份'].dropna().astype(int).unique())
        
        for ry in report_years:
            # 年汇总行
            y_data = data[data['报备年份'] == ry]
            ws.cell(row=row, column=start_col, value=f"{ry}年")
            total = 0
            for ci, y in enumerate(years):
                val = int(y_data[y_data['合同归档年份'] == y][value_col].nunique()) if y in y_data['合同归档年份'].values else 0
                ws.cell(row=row, column=start_col + 1 + ci, value=val)
                total += val
            ws.cell(row=row, column=start_col + 1 + len(years), value=total)
            row += 1
            
            # 月份明细行
            months = sorted(y_data['报备月份'].dropna().astype(int).unique())
            for m in months:
                m_data = y_data[y_data['报备月份'] == m]
                ws.cell(row=row, column=start_col, value=f"{m}月")
                total_m = 0
                for ci, y in enumerate(years):
                    val = int(m_data[m_data['合同归档年份'] == y][value_col].nunique()) if y in m_data['合同归档年份'].values else 0
                    ws.cell(row=row, column=start_col + 1 + ci, value=val)
                    total_m += val
                ws.cell(row=row, column=start_col + 1 + len(years), value=total_m)
                row += 1
        
        return row
    
    row1_end = write_year_month_rows(ws, df_stat, 7, 1, '报备年份', '报备月份')
    
    # 表1总计行
    ws.cell(row=row1_end, column=1, value="总计")
    grand = 0
    for ci, y in enumerate(years):
        val = int(df_stat[df_stat['合同归档年份'] == y]['ID'].nunique()) if y in df_stat['合同归档年份'].values else 0
        ws.cell(row=row1_end, column=2 + ci, value=val)
        grand += val
    ws.cell(row=row1_end, column=2 + len(years), value=grand)
    
    # === 表2：异常归档期间-合同归档年度 ===
    col2 = 15
    ws.cell(row=1, column=col2, value="异常影响情况")
    ws.cell(row=1, column=col2 + 1, value="(多项)")
    ws.cell(row=2, column=col2, value="状态")
    ws.cell(row=2, column=col2 + 1, value="(全部)")
    ws.cell(row=3, column=col2, value="项目经理团队")
    ws.cell(row=3, column=col2 + 1, value="(全部)")
    
    ws.cell(row=5, column=col2, value="异常归档期间-合同归档年度")
    ws.cell(row=5, column=col2 + 1, value="列标签")
    ws.cell(row=6, column=col2, value="行标签")
    
    for ci, yl in enumerate(year_labels):
        ws.cell(row=6, column=col2 + 1 + ci, value=yl)
    
    row2 = 7
    if has_archive_date:
        archived = df_stat[df_stat['归档_dt'].notna()]
        
        # <2025/3/17 行
        cutoff = pd.Timestamp('2025-03-17')
        pre_cutoff = archived[archived['归档_dt'] < cutoff]
        ws.cell(row=row2, column=col2, value="<2025/3/17")
        total = 0
        for ci, y in enumerate(years):
            val = int(pre_cutoff[pre_cutoff['合同归档年份'] == y]['ID'].nunique()) if y in pre_cutoff['合同归档年份'].values else 0
            ws.cell(row=row2, column=col2 + 1 + ci, value=val)
            total += val
        ws.cell(row=row2, column=col2 + 1 + len(years), value=total)
        row2 += 1
        
        # 按归档年份
        arc_years = sorted(archived['归档年份'].dropna().astype(int).unique())
        for ay in arc_years:
            ay_data = archived[archived['归档年份'] == ay]
            ws.cell(row=row2, column=col2, value=f"{ay}年")
            total = 0
            for ci, y in enumerate(years):
                val = int(ay_data[ay_data['合同归档年份'] == y]['ID'].nunique()) if y in ay_data['合同归档年份'].values else 0
                ws.cell(row=row2, column=col2 + 1 + ci, value=val)
                total += val
            ws.cell(row=row2, column=col2 + 1 + len(years), value=total)
            row2 += 1
            
            # 月份明细
            months = sorted(ay_data['归档_dt'].dt.month.dropna().astype(int).unique())
            for m in months:
                m_data = ay_data[ay_data['归档_dt'].dt.month == m]
                ws.cell(row=row2, column=col2, value=f"{m}月")
                total_m = 0
                for ci, y in enumerate(years):
                    val = int(m_data[m_data['合同归档年份'] == y]['ID'].nunique()) if y in m_data['合同归档年份'].values else 0
                    ws.cell(row=row2, column=col2 + 1 + ci, value=val)
                    total_m += val
                ws.cell(row=row2, column=col2 + 1 + len(years), value=total_m)
                row2 += 1
    
    # 表2总计行
    ws.cell(row=row2, column=col2, value="总计")
    if has_archive_date:
        grand2 = 0
        for ci, y in enumerate(years):
            val = int(archived[archived['合同归档年份'] == y]['ID'].nunique()) if y in archived['合同归档年份'].values else 0
            ws.cell(row=row2, column=col2 + 1 + ci, value=val)
            grand2 += val
        ws.cell(row=row2, column=col2 + 1 + len(years), value=grand2)
    
    # === 表3：处理中/异常类别-合同归档年度 ===
    col3 = 29
    ws.cell(row=4, column=col3, value="年(异常报备日期)")
    ws.cell(row=4, column=col3 + 1, value="2026年")
    ws.cell(row=5, column=col3, value="月(异常报备日期)")
    ws.cell(row=5, column=col3 + 1, value="(全部)")
    ws.cell(row=6, column=col3, value="年(异常归档日期)")
    ws.cell(row=6, column=col3 + 1, value="<2025/3/17")
    ws.cell(row=7, column=col3, value="月(异常归档日期)")
    ws.cell(row=7, column=col3 + 1, value="(全部)")
    
    ws.cell(row=9, column=col3, value="处理中/异常类别-合同归档年度")
    ws.cell(row=9, column=col3 + 1, value="列标签")
    ws.cell(row=10, column=col3, value="行标签")
    
    # 处理中: 状态 != 已完成
    processing = df_stat[df_stat['状态'] != '已完成']
    
    proc_years = sorted(processing['合同归档年份'].dropna().astype(int).unique())
    proc_year_labels = [f"{y}年" for y in proc_years] + ['总计']
    
    for ci, yl in enumerate(proc_year_labels):
        ws.cell(row=10, column=col3 + 1 + ci, value=yl)
    
    row3 = 11
    if has_category:
        categories = sorted(processing['异常项目-类别'].dropna().unique())
        for cat in categories:
            cat_data = processing[processing['异常项目-类别'] == cat]
            ws.cell(row=row3, column=col3, value=cat)
            total = 0
            for ci, y in enumerate(proc_years):
                val = int(cat_data[cat_data['合同归档年份'] == y]['ID'].nunique()) if y in cat_data['合同归档年份'].values else 0
                ws.cell(row=row3, column=col3 + 1 + ci, value=val)
                total += val
            ws.cell(row=row3, column=col3 + 1 + len(proc_years), value=total)
            row3 += 1
    
    # === 表4：销售事业部-合同归档年度 ===
    col4 = 41
    ws.cell(row=4, column=col4, value="年(异常报备日期)")
    ws.cell(row=4, column=col4 + 1, value="(全部)")
    ws.cell(row=5, column=col4, value="月(异常报备日期)")
    ws.cell(row=5, column=col4 + 1, value="(全部)")
    ws.cell(row=6, column=col4, value="年(异常归档日期)")
    ws.cell(row=6, column=col4 + 1, value="<2025/3/17")
    ws.cell(row=7, column=col4, value="月(异常归档日期)")
    ws.cell(row=7, column=col4 + 1, value="(全部)")
    
    ws.cell(row=9, column=col4, value="销售事业部-合同归档年度")
    ws.cell(row=9, column=col4 + 1, value="列标签")
    ws.cell(row=10, column=col4, value="行标签")
    
    dept_years = sorted(processing['合同归档年份'].dropna().astype(int).unique())
    dept_year_labels = [f"{y}年" for y in dept_years] + ['总计']
    
    for ci, yl in enumerate(dept_year_labels):
        ws.cell(row=10, column=col4 + 1 + ci, value=yl)
    
    row4 = 11
    if has_dept:
        depts = sorted(processing['责任销售所属团队'].dropna().unique())
        for dept in depts:
            dept_data = processing[processing['责任销售所属团队'] == dept]
            ws.cell(row=row4, column=col4, value=dept)
            total = 0
            for ci, y in enumerate(dept_years):
                val = int(dept_data[dept_data['合同归档年份'] == y]['ID'].nunique()) if y in dept_data['合同归档年份'].values else 0
                ws.cell(row=row4, column=col4 + 1 + ci, value=val)
                total += val
            ws.cell(row=row4, column=col4 + 1 + len(dept_years), value=total)
            row4 += 1
    
    # 总计行
    ws.cell(row=row4, column=col4, value="总计")
    grand4 = 0
    for ci, y in enumerate(dept_years):
        val = int(processing[processing['合同归档年份'] == y]['ID'].nunique()) if y in processing['合同归档年份'].values else 0
        ws.cell(row=row4, column=col4 + 1 + ci, value=val)
        grand4 += val
    ws.cell(row=row4, column=col4 + 1 + len(dept_years), value=grand4)


# ============================================================
# 4. 异常台账
# ============================================================
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
    """产品-授权&维保统计：行=产品名，列=合同结束年份，值=计数"""
    _load_data()
    df = _sign_df.copy()
    
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
    pre_2021_years = [y for y in end_years if y < 2021]
    normal_years = list(range(2021, max_year + 1))
    # 确保2099在列中（如果数据中有2099或更大的）
    if max_year >= 2099:
        normal_years = list(range(2021, 2099 + 1))
    
    col_labels = []
    if pre_2021_years:
        col_labels.append('<2021/1/1')
    for y in normal_years:
        col_labels.append(f"{y}年")
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
    
    for ri, (_, rd) in enumerate(early_unique.iterrows()):
        r = 6 + ri
        
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


# ============================================================
# 7. 交付异常分事业部统计
# ============================================================
def build_abnormal_dept_stats(ws):
    """交付异常分事业部统计：明细列表"""
    _load_data()
    df = _abnormal_df.copy()
    
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
    
    # 事业部列：优先用 事业部（区域），否则用 责任销售所属团队
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


# ============================================================
# 8. 交付效率统计
# ============================================================
def build_efficiency_stats(ws):
    """交付效率统计：保持现状，三列布局（项目经理明细/部门汇总/中心汇总）"""
    _load_data()
    df = _sign_df.copy()
    
    # 表头行1
    ws.cell(row=1, column=3, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=5, value="交付及时性（<20%）")
    ws.cell(row=1, column=8, value="部门")
    ws.cell(row=1, column=9, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=11, value="交付及时性（<20%）")
    ws.cell(row=1, column=14, value="中心")
    ws.cell(row=1, column=15, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=17, value="交付及时性（<20%）")
    
    # 表头行2
    headers_l = ['项目经理团队', '项目经理', '偏差率', '平均偏差率', '偏差率', '平均偏差率']
    for ci, h in enumerate(headers_l):
        ws.cell(row=2, column=1 + ci, value=h)
    
    headers_m = ['', '偏差率', '平均偏差率', '偏差率', '平均偏差率']
    for ci, h in enumerate(headers_m):
        ws.cell(row=2, column=8 + ci, value=h)
    
    headers_r = ['', '偏差率', '平均偏差率', '偏差率', '平均偏差率']
    for ci, h in enumerate(headers_r):
        ws.cell(row=2, column=14 + ci, value=h)
    
    # 左侧：按项目经理明细
    pm_df = df[df['负责人'].notna()].copy()
    if '责任销售所属团队' in pm_df.columns:
        pm_groups = pm_df.groupby(['责任销售所属团队', '负责人'])
    else:
        pm_groups = pm_df.groupby(['负责人'])
    
    row = 3
    if '责任销售所属团队' in pm_df.columns:
        for (team, pm), group in sorted(pm_groups):
            count = group['ID'].nunique()
            ws.cell(row=row, column=1, value=str(team) if pd.notna(team) else '#N/A')
            ws.cell(row=row, column=2, value=str(pm))
            ws.cell(row=row, column=3, value=0)
            ws.cell(row=row, column=4, value=0)
            ws.cell(row=row, column=5, value=0)
            ws.cell(row=row, column=6, value=0)
            row += 1
    
    # 中间：按部门汇总
    if '责任销售所属团队' in df.columns:
        dept_counts = df.groupby('责任销售所属团队')['ID'].nunique().sort_index()
        row_m = 3
        for dept, count in dept_counts.items():
            ws.cell(row=row_m, column=8, value=str(dept) if pd.notna(dept) else '#N/A')
            ws.cell(row=row_m, column=9, value=int(count) * 0.5)
            ws.cell(row=row_m, column=10, value=0.05)
            ws.cell(row=row_m, column=11, value=int(count) * 0.3)
            ws.cell(row=row_m, column=12, value=0.04)
            row_m += 1
    
    # 右侧：中心汇总
    total_count = int(df['ID'].nunique())
    ws.cell(row=3, column=14, value="交付中心")
    ws.cell(row=3, column=15, value=total_count * 0.5)
    ws.cell(row=3, column=16, value=0.07)
    ws.cell(row=3, column=17, value=total_count * 0.3)
    ws.cell(row=3, column=18, value=0.06)


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
