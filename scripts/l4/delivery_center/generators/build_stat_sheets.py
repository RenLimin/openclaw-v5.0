"""
统计 Sheet 生成器——精确匹配参考报表的透视表格式
从 BDMS report_statistics 表读取统计结果，生成透视表格式的 Excel Sheet
"""
import sqlite3
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

BDMS_DB = Path.home() / ".openclaw" / "data" / "bdms.db"
REPORT_MONTH = "202606"

HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT_WHITE = Font(bold=True, size=10, color="FFFFFF")
THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)


def read_stat(conn, month, sheet_name, stat_type):
    c = conn.cursor()
    c.execute('''SELECT row_key, col_key, value_num, value_text
        FROM report_statistics 
        WHERE report_month=? AND sheet_name=? AND stat_type=?
        ORDER BY row_key, col_key''',
        (month, sheet_name, stat_type))
    rows = c.fetchall()
    data = {}
    for row_key, col_key, val_num, val_text in rows:
        if row_key not in data:
            data[row_key] = {}
        data[row_key][col_key] = val_num if val_num is not None else val_text
    return data


def write_pivot_table(ws, data, title_row, title_col, start_row=1, start_col=1):
    """写入透视表格式数据"""
    if not data:
        ws.cell(row=start_row, column=start_col, value="无数据")
        return
    
    # 获取所有列
    all_cols = sorted(set(col for row in data.values() for col in row.keys()))
    
    # 写入标题行
    ws.cell(row=start_row, column=start_col, value=title_row)
    ws.cell(row=start_row, column=start_col + 1, value=title_col)
    for ci, col in enumerate(all_cols, start_col + 2):
        ws.cell(row=start_row, column=ci, value=col)
    
    # 写入数据行
    for ri, (row_key, row_data) in enumerate(sorted(data.items()), start_row + 1):
        ws.cell(row=ri, column=start_col, value=row_key)
        for ci, col in enumerate(all_cols, start_col + 2):
            val = row_data.get(col, 0)
            ws.cell(row=ri, column=ci, value=val if val else 0)


def build_sign_stats(ws, conn):
    """签约统计：左表=按年份，右表=状态×年份交叉表"""
    # 行0-2：筛选器标题
    ws.cell(row=1, column=1, value="项目经理所属部门")
    ws.cell(row=1, column=2, value="(全部)")
    ws.cell(row=2, column=1, value="统计项目编号")
    ws.cell(row=2, column=2, value="(全部)")
    ws.cell(row=3, column=1, value="项目状态")
    ws.cell(row=3, column=2, value="(全部)")
    
    # 行4：列名
    ws.cell(row=5, column=1, value="行标签")
    ws.cell(row=5, column=2, value="计数项:ID")
    ws.cell(row=5, column=6, value="计数项:ID")
    ws.cell(row=5, column=7, value="列标签")
    
    # 左表：按签约年份统计
    year_data = read_stat(conn, REPORT_MONTH, '签约统计', 'by_year')
    for ri, (year, counts) in enumerate(sorted(year_data.items()), 6):
        ws.cell(row=ri, column=1, value=year)
        ws.cell(row=ri, column=2, value=counts.get('项目数', 0))
    
    # 右表：按项目状态×年份交叉表
    status_year_data = read_stat(conn, REPORT_MONTH, '签约统计', 'status_year')
    # 重组为 {状态: {年份: 数}}
    pivot = {}
    for key, val in status_year_data.items():
        # key 是 "状态|年份" 格式
        parts = key.split('|') if '|' in str(key) else [key, '']
        # 实际上 read_stat 返回的是 {row_key: {col_key: value}}
        pass
    
    # 重新读取交叉表数据
    c = conn.cursor()
    c.execute('''SELECT row_key, col_key, value_num
        FROM report_statistics 
        WHERE report_month=? AND sheet_name='签约统计' AND stat_type='status_year'
        ORDER BY row_key, col_key''',
        (REPORT_MONTH,))
    rows = c.fetchall()
    
    pivot = {}
    for row_key, col_key, val_num in rows:
        if row_key not in pivot:
            pivot[row_key] = {}
        pivot[row_key][col_key] = int(val_num) if val_num else 0
    
    # 写入右表
    all_years = sorted(set(y for s in pivot.values() for y in s.keys()))
    ws.cell(row=5, column=7, value="列标签")
    for ci, year in enumerate(all_years, 8):
        ws.cell(row=5, column=ci, value=year)
    
    for ri, (status, year_data) in enumerate(sorted(pivot.items()), 6):
        ws.cell(row=ri, column=6, value=status)
        for ci, year in enumerate(all_years, 8):
            ws.cell(row=ri, column=ci, value=year_data.get(year, 0))


def build_poc_stats(ws, conn):
    """POC&提前实施统计"""
    ws.cell(row=1, column=8, value="项目经理所属部门")
    ws.cell(row=1, column=9, value="(全部)")
    ws.cell(row=2, column=1, value="项目经理所属部门")
    ws.cell(row=2, column=2, value="(全部)")
    ws.cell(row=2, column=8, value="统计项目编号")
    ws.cell(row=2, column=9, value="(全部)")
    ws.cell(row=3, column=1, value="统计项目编号")
    ws.cell(row=3, column=2, value="(全部)")
    ws.cell(row=3, column=8, value="项目类型(概览)")
    ws.cell(row=3, column=9, value="提前实施")
    ws.cell(row=4, column=1, value="履约项立项期间")
    ws.cell(row=4, column=2, value="列标签")
    ws.cell(row=4, column=8, value="提前实施履约项持续周期")
    ws.cell(row=4, column=9, value="列标签")
    
    # 读取数据
    c = conn.cursor()
    c.execute('''SELECT row_key, col_key, value_num
        FROM report_statistics 
        WHERE report_month=? AND sheet_name='POC&提前实施统计' AND stat_type='year_type'
        ORDER BY row_key, col_key''',
        (REPORT_MONTH,))
    rows = c.fetchall()
    
    poc_by_year = {}
    early_by_year = {}
    for row_key, col_key, val_num in rows:
        val = int(val_num) if val_num else 0
        if 'POC' in str(col_key):
            poc_by_year[str(row_key)] = val
        elif '提前' in str(col_key):
            early_by_year[str(row_key)] = val
    
    # 写入左表
    ws.cell(row=5, column=1, value="行标签")
    ws.cell(row=5, column=2, value="POC")
    ws.cell(row=5, column=3, value="提前实施")
    ws.cell(row=5, column=4, value="总计")
    
    all_years = sorted(set(list(poc_by_year.keys()) + list(early_by_year.keys())))
    for ri, year in enumerate(all_years, 6):
        poc_count = poc_by_year.get(year, 0)
        early_count = early_by_year.get(year, 0)
        ws.cell(row=ri, column=1, value=year)
        ws.cell(row=ri, column=2, value=poc_count)
        ws.cell(row=ri, column=3, value=early_count)
        ws.cell(row=ri, column=4, value=poc_count + early_count)
    
    # 总计行
    ri = 6 + len(all_years)
    ws.cell(row=ri, column=1, value="总计")
    ws.cell(row=ri, column=2, value=sum(poc_by_year.values()))
    ws.cell(row=ri, column=3, value=sum(early_by_year.values()))
    ws.cell(row=ri, column=4, value=sum(poc_by_year.values()) + sum(early_by_year.values()))


def build_abnormal_stats(ws, conn):
    """异常统计"""
    ws.cell(row=1, column=1, value="异常影响情况")
    ws.cell(row=1, column=2, value="(多项)")
    ws.cell(row=2, column=1, value="状态")
    ws.cell(row=2, column=2, value="(全部)")
    ws.cell(row=3, column=1, value="项目经理团队")
    ws.cell(row=3, column=2, value="(全部)")
    ws.cell(row=4, column=1, value="异常报备期间-合同归档年度")
    ws.cell(row=4, column=2, value="列标签")
    
    # 按年份统计
    year_data = read_stat(conn, REPORT_MONTH, '异常统计', 'by_year')
    ws.cell(row=5, column=1, value="行标签")
    years = sorted(year_data.keys())
    for ci, year in enumerate(years, 2):
        ws.cell(row=5, column=ci, value=year)
    ws.cell(row=5, column=len(years) + 2, value="总计")
    
    for ri, year in enumerate(years, 6):
        ws.cell(row=ri, column=1, value=year)
        ws.cell(row=ri, column=2, value=year_data.get(year, {}).get('异常数', 0) if isinstance(year_data.get(year), dict) else year_data.get(year, 0))
    
    # 总计行
    ri = 6 + len(years)
    ws.cell(row=ri, column=1, value="总计")
    total = sum(year_data.get(y, {}).get('异常数', 0) if isinstance(year_data.get(y), dict) else year_data.get(y, 0) for y in years)
    ws.cell(row=ri, column=2, value=total)


def build_abnormal_ledger(ws, conn):
    """异常台账"""
    ws.cell(row=1, column=1, value="合计")
    ws.cell(row=1, column=7, value="验收异常")
    ws.cell(row=1, column=13, value="交付异常")
    ws.cell(row=2, column=1, value="合同归档年份")
    ws.cell(row=2, column=2, value="2025年之前存量")
    ws.cell(row=2, column=3, value="2025年新增")
    ws.cell(row=2, column=4, value="2025年已处理完毕")
    ws.cell(row=2, column=5, value="处理中")
    
    year_data = read_stat(conn, REPORT_MONTH, '异常台账', 'by_year')
    years = sorted(year_data.keys())
    for ri, year in enumerate(years, 3):
        ws.cell(row=ri, column=1, value=year)
        val = year_data.get(year, {}).get('合计', 0) if isinstance(year_data.get(year), dict) else year_data.get(year, 0)
        ws.cell(row=ri, column=2, value=val)


def build_handover_stats(ws, conn):
    """交接统计"""
    ws.cell(row=1, column=1, value="项目经理所属区域")
    ws.cell(row=1, column=2, value="(多项)")
    ws.cell(row=1, column=9, value="项目经理所属区域")
    ws.cell(row=1, column=10, value="(多项)")
    ws.cell(row=1, column=17, value="项目经理所属区域")
    ws.cell(row=1, column=18, value="(多项)")
    ws.cell(row=3, column=1, value="确收交接年月-合格率")
    ws.cell(row=3, column=2, value="列标签")
    ws.cell(row=3, column=9, value="确收交接年月-跨月交接比率")
    ws.cell(row=3, column=10, value="列标签")
    ws.cell(row=3, column=17, value="验收交接年月-合格率")
    ws.cell(row=3, column=18, value="列标签")
    ws.cell(row=4, column=1, value="行标签")
    ws.cell(row=4, column=2, value="否")
    ws.cell(row=4, column=3, value="是")
    ws.cell(row=4, column=4, value="总计")
    
    # 读取交接统计数据
    summary = read_stat(conn, REPORT_MONTH, '交接统计', 'summary')
    
    # 确收合格率
    c = conn.cursor()
    c.execute('''SELECT row_key, col_key, value_num
        FROM report_statistics 
        WHERE report_month=? AND sheet_name='交接统计' AND stat_type='确收'
        ORDER BY row_key, col_key''',
        (REPORT_MONTH,))
    rev_rows = {r[1]: r[2] for r in c.fetchall()}
    
    ws.cell(row=5, column=1, value=REPORT_MONTH)
    rate = rev_rows.get('合格率', 0)
    qualified = rev_rows.get('合格数', 0)
    ws.cell(row=5, column=2, value=round(1 - rate, 6) if rate else 0)
    ws.cell(row=5, column=3, value=round(rate, 6) if rate else 0)
    ws.cell(row=5, column=4, value=1)
    
    # 验收合格率
    c.execute('''SELECT row_key, col_key, value_num
        FROM report_statistics 
        WHERE report_month=? AND sheet_name='交接统计' AND stat_type='验收'
        ORDER BY row_key, col_key''',
        (REPORT_MONTH,))
    acc_rows = {r[1]: r[2] for r in c.fetchall()}
    
    ws.cell(row=5, column=17, value=REPORT_MONTH)
    rate = acc_rows.get('合格率', 0)
    qualified = acc_rows.get('合格数', 0)
    ws.cell(row=5, column=18, value=round(1 - rate, 6) if rate else 0)
    ws.cell(row=5, column=19, value=round(rate, 6) if rate else 0)
    ws.cell(row=5, column=20, value=1)
    
    # 总计行
    ws.cell(row=6, column=1, value="总计")
    ws.cell(row=6, column=2, value=round(1 - rev_rows.get('合格率', 0), 6))
    ws.cell(row=6, column=3, value=round(rev_rows.get('合格率', 0), 6))
    ws.cell(row=6, column=4, value=1)
    ws.cell(row=6, column=17, value="总计")
    ws.cell(row=6, column=18, value=round(1 - acc_rows.get('合格率', 0), 6))
    ws.cell(row=6, column=19, value=round(acc_rows.get('合格率', 0), 6))
    ws.cell(row=6, column=20, value=1)


def build_efficiency_stats(ws, conn):
    """交付效率统计"""
    ws.cell(row=1, column=3, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=5, value="交付及时性（<20%）")
    ws.cell(row=1, column=8, value="部门")
    ws.cell(row=1, column=9, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=11, value="交付及时性（<20%）")
    ws.cell(row=1, column=14, value="中心")
    ws.cell(row=1, column=15, value="交付计划准确性（<50%）")
    ws.cell(row=1, column=17, value="交付及时性（<20%）")
    ws.cell(row=2, column=1, value="项目经理团队")
    ws.cell(row=2, column=2, value="项目经理")
    ws.cell(row=2, column=3, value="偏差率")
    ws.cell(row=2, column=4, value="平均偏差率")
    ws.cell(row=2, column=5, value="偏差率")
    ws.cell(row=2, column=6, value="平均偏差率")
    
    # 按项目经理统计
    pm_data = read_stat(conn, REPORT_MONTH, '交付效率统计', 'by_pm')
    dept_data = read_stat(conn, REPORT_MONTH, '交付效率统计', 'by_dept')
    
    # 写入项目经理数据（简化版）
    row = 3
    for pm, vals in sorted(pm_data.items()):
        count = vals.get('项目数', 0) if isinstance(vals, dict) else vals
        ws.cell(row=row, column=1, value="")  # 团队名需要额外映射
        ws.cell(row=row, column=2, value=pm)
        ws.cell(row=row, column=3, value=0)  # 偏差率需要计算
        ws.cell(row=row, column=4, value=0)
        ws.cell(row=row, column=5, value=0)
        ws.cell(row=row, column=6, value=0)
        row += 1
    
    # 按部门汇总
    row = 3
    for dept, vals in sorted(dept_data.items()):
        count = vals.get('项目数', 0) if isinstance(vals, dict) else vals
        ws.cell(row=row, column=8, value=dept)
        ws.cell(row=row, column=9, value=count)
        row += 1


def build_product_stats(ws, conn):
    """产品-授权&维保统计"""
    ws.cell(row=3, column=1, value="计数项:ID")
    ws.cell(row=3, column=2, value="列标签")
    ws.cell(row=4, column=1, value="行标签")
    
    product_data = read_stat(conn, REPORT_MONTH, '产品-授权&维保统计', 'by_product')
    
    # 写入产品数据
    for ri, (prod, vals) in enumerate(sorted(product_data.items()), 5):
        count = vals.get('项目数', 0) if isinstance(vals, dict) else vals
        ws.cell(row=ri, column=1, value=prod)
        ws.cell(row=ri, column=2, value=count)


def build_early_dept_stats(ws, conn):
    """提前实施分事业部统计"""
    ws.cell(row=1, column=1, value="项目类型(概览)")
    ws.cell(row=1, column=2, value="提前实施")
    ws.cell(row=2, column=1, value="统计项目编号")
    ws.cell(row=2, column=2, value="(多项)")
    ws.cell(row=3, column=1, value="销售团队-统计")
    ws.cell(row=3, column=2, value="(全部)")
    ws.cell(row=5, column=1, value="最终用户名称")
    ws.cell(row=5, column=2, value="客户名称")
    ws.cell(row=5, column=3, value="责任销售（履约项）")
    ws.cell(row=5, column=4, value="所属项目")
    ws.cell(row=5, column=5, value="提前实施项目持续周期-统计")
    ws.cell(row=5, column=6, value="计数项:ID")
    
    dept_data = read_stat(conn, REPORT_MONTH, '提前实施分事业部统计', 'by_dept')
    for ri, (dept, vals) in enumerate(sorted(dept_data.items()), 6):
        count = vals.get('项目数', 0) if isinstance(vals, dict) else vals
        ws.cell(row=ri, column=1, value=dept)
        ws.cell(row=ri, column=6, value=count)


def build_abnormal_dept_stats(ws, conn):
    """交付异常分事业部统计"""
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
    ws.cell(row=8, column=1, value="事业部（区域）")
    ws.cell(row=8, column=2, value="客户名称")
    ws.cell(row=8, column=3, value="最终用户名称")
    ws.cell(row=8, column=4, value="异常项目-处置方案")
    ws.cell(row=8, column=5, value="预估金额")
    ws.cell(row=8, column=6, value="项目异常内容")
    ws.cell(row=8, column=7, value="计数项:销售合同编号")
    
    dept_data = read_stat(conn, REPORT_MONTH, '交付异常分事业部统计', 'by_dept')
    for ri, (dept, vals) in enumerate(sorted(dept_data.items()), 9):
        count = vals.get('异常数', 0) if isinstance(vals, dict) else vals
        ws.cell(row=ri, column=1, value=dept)
        ws.cell(row=ri, column=7, value=count)


# 导出函数映射
BUILDERS = {
    '签约统计': build_sign_stats,
    'POC&提前实施统计': build_poc_stats,
    '异常统计': build_abnormal_stats,
    '异常台账': build_abnormal_ledger,
    '交接统计': build_handover_stats,
    '交付效率统计': build_efficiency_stats,
    '产品-授权&维保统计': build_product_stats,
    '提前实施分事业部统计': build_early_dept_stats,
    '交付异常分事业部统计': build_abnormal_dept_stats,
}


def build_all_stat_sheets(wb, conn):
    """构建所有统计 Sheet"""
    for name, builder in BUILDERS.items():
        ws = wb.create_sheet(name)
        builder(ws, conn)
        print(f"  ✅ {name}")


if __name__ == "__main__":
    conn = sqlite3.connect(BDMS_DB)
    wb = Workbook()
    wb.remove(wb.active)
    build_all_stat_sheets(wb, conn)
    output = Path.home() / ".openclaw" / "data" / "reports" / "统计Sheet测试.xlsx"
    wb.save(output)
    print(f"\n✅ 已保存: {output}")
    conn.close()
