"""
202606 交付月报统计计算 → 存储到 BDMS → 生成 Excel
按照既定方案：通过公式计算后存储最终结果至本地数据库
"""
import sqlite3, csv, json
import pandas as pd
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

# === 配置 ===
ONES_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
BDMS_DB = Path.home() / ".openclaw" / "data" / "bdms.db"
OUTPUT_DIR = Path.home() / ".openclaw" / "data" / "reports"
CONFIG_DIR = Path(__file__).parent.parent / "config"

REPORT_MONTH = "202606"
REPORT_DATE = "2026-06-30"

HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT_WHITE = Font(bold=True, size=10, color="FFFFFF")
THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)


def load_csv(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        return pd.DataFrame(csv.DictReader(f))


def load_bdms_table(table):
    conn = sqlite3.connect(BDMS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in c.description]
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return cols, rows


def init_stats_table(conn):
    """创建统计结果表"""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS report_statistics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_month TEXT NOT NULL,
        sheet_name TEXT NOT NULL,
        stat_type TEXT,
        row_key TEXT,
        col_key TEXT,
        value_num REAL,
        value_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(report_month, sheet_name, stat_type, row_key, col_key)
    )''')
    conn.commit()


def store_stat(conn, month, sheet, stat_type, row_key, col_key, value):
    """存储统计结果"""
    c = conn.cursor()
    if isinstance(value, (int, float)) and not pd.isna(value):
        val_num = float(value)
        val_text = None
    else:
        val_num = None
        val_text = str(value) if value else None
    
    c.execute('''INSERT OR REPLACE INTO report_statistics 
        (report_month, sheet_name, stat_type, row_key, col_key, value_num, value_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (month, sheet, stat_type, row_key, col_key, val_num, val_text))


def compute_all_stats(conn, sign_df, poc_df, abnormal_df, rev_rows, acc_rows):
    """计算所有统计指标并存储"""
    print("  计算统计指标...")
    
    # === 1. 签约统计 ===
    sign_df['立项年份'] = pd.to_datetime(sign_df['立项日期'], errors='coerce').dt.year
    
    # 1a. 按签约年份统计
    sign_by_year = sign_df.groupby('立项年份')['ID'].nunique()
    for year, count in sign_by_year.items():
        if pd.notna(year):
            store_stat(conn, REPORT_MONTH, '签约统计', 'by_year', str(int(year)), '项目数', count)
    
    # 1b. 按项目状态×年份交叉表
    status_year = sign_df.groupby(['项目状态', '立项年份'])['ID'].nunique().reset_index()
    for _, row in status_year.iterrows():
        year = int(row['立项年份']) if pd.notna(row['立项年份']) else 0
        store_stat(conn, REPORT_MONTH, '签约统计', 'status_year', 
                   str(row['项目状态']), str(year), row['ID'])
    
    # 1c. 按部门统计
    if '责任销售所属团队' in sign_df.columns:
        dept_stats = sign_df.groupby('责任销售所属团队')['ID'].nunique()
        for dept, count in dept_stats.items():
            store_stat(conn, REPORT_MONTH, '签约统计', 'by_dept', str(dept), '项目数', count)
    
    print("    ✅ 签约统计")
    
    # === 2. POC&提前实施统计 ===
    poc_df['立项年份'] = pd.to_datetime(poc_df['立项日期'], errors='coerce').dt.year
    
    # 2a. 按年份×项目类型统计
    poc_by_year_type = poc_df.groupby(['立项年份', '项目类型(概览)'])['ID'].nunique().reset_index()
    for _, row in poc_by_year_type.iterrows():
        year = int(row['立项年份']) if pd.notna(row['立项年份']) else 0
        store_stat(conn, REPORT_MONTH, 'POC&提前实施统计', 'year_type',
                   str(year), str(row['项目类型(概览)']), row['ID'])
    
    # 2b. 按部门统计
    if '责任销售所属团队' in poc_df.columns:
        poc_dept = poc_df.groupby('责任销售所属团队')['ID'].nunique()
        for dept, count in poc_dept.items():
            store_stat(conn, REPORT_MONTH, 'POC&提前实施统计', 'by_dept', str(dept), '项目数', count)
    
    print("    ✅ POC&提前实施统计")
    
    # === 3. 异常统计 ===
    abnormal_df['归档年份'] = pd.to_datetime(abnormal_df['合同归档日期'], errors='coerce').dt.year
    
    # 3a. 按归档年份统计
    abn_by_year = abnormal_df.groupby('归档年份')['ID'].nunique()
    for year, count in abn_by_year.items():
        if pd.notna(year):
            store_stat(conn, REPORT_MONTH, '异常统计', 'by_year', str(int(year)), '异常数', count)
    
    # 3b. 按部门统计
    if '责任销售所属团队' in abnormal_df.columns:
        abn_dept = abnormal_df.groupby('责任销售所属团队')['ID'].nunique()
        for dept, count in abn_dept.items():
            store_stat(conn, REPORT_MONTH, '异常统计', 'by_dept', str(dept), '异常数', count)
    
    print("    ✅ 异常统计")
    
    # === 4. 异常台账 ===
    for year in sorted(abnormal_df['归档年份'].dropna().astype(int).unique()):
        subset = abnormal_df[abnormal_df['归档年份'] == year]
        store_stat(conn, REPORT_MONTH, '异常台账', 'by_year', str(year), '合计', len(subset))
    
    print("    ✅ 异常台账")
    
    # === 5. 交接统计 ===
    rev_df = pd.DataFrame(rev_rows)
    acc_df = pd.DataFrame(acc_rows)
    
    store_stat(conn, REPORT_MONTH, '交接统计', 'summary', '确收总数', '值', len(rev_df))
    store_stat(conn, REPORT_MONTH, '交接统计', 'summary', '验收总数', '值', len(acc_df))
    
    if '是否接收' in rev_df.columns and len(rev_df) > 0:
        qualified = rev_df[rev_df['是否接收'].astype(str).str.contains('是', na=False)]
        store_stat(conn, REPORT_MONTH, '交接统计', '确收', '合格数', '值', len(qualified))
        rate = len(qualified) / len(rev_df) if len(rev_df) > 0 else 0
        store_stat(conn, REPORT_MONTH, '交接统计', '确收', '合格率', '值', rate)
    
    if '财务是否接收' in acc_df.columns and len(acc_df) > 0:
        qualified = acc_df[acc_df['财务是否接收'].astype(str).str.contains('是', na=False)]
        store_stat(conn, REPORT_MONTH, '交接统计', '验收', '合格数', '值', len(qualified))
        rate = len(qualified) / len(acc_df) if len(acc_df) > 0 else 0
        store_stat(conn, REPORT_MONTH, '交接统计', '验收', '合格率', '值', rate)
    
    print("    ✅ 交接统计")
    
    # === 6. 产品-授权&维保统计 ===
    if '标准产品/服务序号' in sign_df.columns:
        product_stats = sign_df.groupby('标准产品/服务序号')['ID'].nunique()
        for prod, count in product_stats.items():
            if prod and str(prod).strip():
                store_stat(conn, REPORT_MONTH, '产品-授权&维保统计', 'by_product', str(prod), '项目数', count)
    
    print("    ✅ 产品-授权&维保统计")
    
    # === 7. 提前实施分事业部统计 ===
    if '项目类型(概览)' in poc_df.columns:
        early_df = poc_df[poc_df['项目类型(概览)'].str.contains('提前实施', na=False)]
        if '责任销售所属团队' in early_df.columns:
            early_dept = early_df.groupby('责任销售所属团队')['ID'].nunique()
            for dept, count in early_dept.items():
                store_stat(conn, REPORT_MONTH, '提前实施分事业部统计', 'by_dept', str(dept), '项目数', count)
    
    print("    ✅ 提前实施分事业部统计")
    
    # === 8. 交付异常分事业部统计 ===
    if '责任销售所属团队' in abnormal_df.columns:
        abn_dept2 = abnormal_df.groupby('责任销售所属团队')['ID'].nunique()
        for dept, count in abn_dept2.items():
            store_stat(conn, REPORT_MONTH, '交付异常分事业部统计', 'by_dept', str(dept), '异常数', count)
    
    print("    ✅ 交付异常分事业部统计")
    
    # === 9. 交付效率统计 ===
    # 按项目经理统计项目数
    if '负责人' in sign_df.columns:
        pm_stats = sign_df.groupby('负责人')['ID'].nunique()
        for pm, count in pm_stats.items():
            store_stat(conn, REPORT_MONTH, '交付效率统计', 'by_pm', str(pm), '项目数', count)
    
    # 按部门统计
    if '责任销售所属团队' in sign_df.columns:
        dept_stats2 = sign_df.groupby('责任销售所属团队')['ID'].nunique()
        for dept, count in dept_stats2.items():
            store_stat(conn, REPORT_MONTH, '交付效率统计', 'by_dept', str(dept), '项目数', count)
    
    print("    ✅ 交付效率统计")
    
    conn.commit()
    print("  ✅ 所有统计已存储到 BDMS")


def read_stats(conn, month, sheet_name, stat_type):
    """从 BDMS 读取统计结果"""
    c = conn.cursor()
    c.execute('''SELECT row_key, col_key, value_num, value_text 
        FROM report_statistics 
        WHERE report_month=? AND sheet_name=? AND stat_type=?
        ORDER BY row_key, col_key''',
        (month, sheet_name, stat_type))
    return c.fetchall()


def write_df(ws, df, start_row=1):
    """写入 DataFrame 到 worksheet"""
    if df.empty:
        ws.cell(row=1, column=1, value="无数据")
        return
    headers = list(df.columns)
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=ci, value=str(h))
        cell.font = HEADER_FONT_WHITE
        cell.fill = HEADER_FILL
        cell.border = THIN_BORDER
    for ri, (_, row) in enumerate(df.iterrows(), start_row + 1):
        for ci, val in enumerate(row, 1):
            v = "" if pd.isna(val) else val
            cell = ws.cell(row=ri, column=ci, value=v)
            cell.border = THIN_BORDER


def generate_excel_from_stats(conn, sign_df, poc_df, abnormal_df, rev_rows, acc_rows):
    """从 BDMS 统计结果生成 Excel"""
    print("  生成 Excel...")
    wb = Workbook()
    wb.remove(wb.active)
    
    # Sheet 1: 签约
    ws = wb.create_sheet("签约")
    write_df(ws, sign_df)
    
    # Sheet 2: POC&提前实施
    ws = wb.create_sheet("POC&提前实施")
    write_df(ws, poc_df)
    
    # Sheet 3: 异常项目
    ws = wb.create_sheet("异常项目")
    write_df(ws, abnormal_df)
    
    # Sheet 4: 确收交接
    ws = wb.create_sheet("确收交接")
    rev_df = pd.DataFrame(rev_rows)
    write_df(ws, rev_df)
    
    # Sheet 5: 验收交接
    ws = wb.create_sheet("验收交接")
    acc_df = pd.DataFrame(acc_rows)
    write_df(ws, acc_df)
    
    # Sheet 6-15: 从 BDMS 统计结果生成
    stat_sheets = [
        ('交付效率统计', '交付效率统计'),
        ('签约统计', '签约统计'),
        ('POC&提前实施统计', 'POC&提前实施统计'),
        ('异常统计', '异常统计'),
        ('异常台账', '异常台账'),
        ('交接统计', '交接统计'),
        ('产品-授权&维保统计', '产品-授权&维保统计'),
        ('提前实施分事业部统计', '提前实施分事业部统计'),
        ('交付异常分事业部统计', '交付异常分事业部统计'),
    ]
    
    for sheet_name, stat_sheet in stat_sheets:
        ws = wb.create_sheet(sheet_name)
        # 读取统计结果
        c = conn.cursor()
        c.execute('''SELECT stat_type, row_key, col_key, value_num, value_text
            FROM report_statistics 
            WHERE report_month=? AND sheet_name=?
            ORDER BY stat_type, row_key, col_key''',
            (REPORT_MONTH, stat_sheet))
        rows = c.fetchall()
        
        if not rows:
            ws.cell(row=1, column=1, value="无统计数据")
            continue
        
        # 按 stat_type 分组
        stat_types = set(r[0] for r in rows)
        current_row = 1
        for st in sorted(stat_types):
            type_rows = [r for r in rows if r[0] == st]
            # 写入 stat_type 作为小标题
            ws.cell(row=current_row, column=1, value=st)
            ws.cell(row=current_row, column=1).font = Font(bold=True, size=11)
            current_row += 1
            
            # 构建 DataFrame
            df_data = {}
            for _, row_key, col_key, val_num, val_text in type_rows:
                if row_key not in df_data:
                    df_data[row_key] = {}
                df_data[row_key][col_key] = val_num if val_num is not None else val_text
            
            if df_data:
                df = pd.DataFrame(df_data).T
                df.index.name = '类别'
                for ci, col in enumerate(df.columns, 1):
                    ws.cell(row=current_row, column=ci + 1, value=col)
                    ws.cell(row=current_row, column=ci + 1).font = HEADER_FONT_WHITE
                    ws.cell(row=current_row, column=ci + 1).fill = HEADER_FILL
                ws.cell(row=current_row, column=1, value='类别')
                ws.cell(row=current_row, column=1).font = HEADER_FONT_WHITE
                ws.cell(row=current_row, column=1).fill = HEADER_FILL
                current_row += 1
                
                for idx, row_data in df.iterrows():
                    ws.cell(row=current_row, column=1, value=str(idx))
                    for ci, val in enumerate(row_data, 2):
                        v = "" if pd.isna(val) else val
                        ws.cell(row=current_row, column=ci, value=v)
                    current_row += 1
            
            current_row += 1  # 空行分隔
    
    # 图例 Sheet
    ws = wb.create_sheet("图例")
    legend_path = CONFIG_DIR / "legend_pm_dept.json"
    if legend_path.exists():
        legend = json.loads(legend_path.read_text(encoding="utf-8"))
        ws.cell(row=1, column=1, value="项目经理")
        ws.cell(row=1, column=2, value="部门")
        ws.cell(row=1, column=1).font = HEADER_FONT_WHITE
        ws.cell(row=1, column=1).fill = HEADER_FILL
        ws.cell(row=1, column=2).font = HEADER_FONT_WHITE
        ws.cell(row=1, column=2).fill = HEADER_FILL
        for ri, (pm, dept) in enumerate(legend.items(), 2):
            ws.cell(row=ri, column=1, value=pm)
            ws.cell(row=ri, column=2, value=dept)
    
    # 保存
    output_path = OUTPUT_DIR / f"交付月报-{REPORT_MONTH}.xlsx"
    wb.save(output_path)
    print(f"  ✅ Excel 已生成: {output_path}")
    return str(output_path)


def main():
    print("=== 202606 交付月报：统计计算 → 入库 → 生成 ===\n")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. 加载数据
    print("1. 加载数据...")
    sign_df = load_csv(ONES_DIR / "签约项目统计.csv")
    poc_df = load_csv(ONES_DIR / "poc_提前实施.csv")
    abnormal_df = load_csv(ONES_DIR / "异常处置.csv")
    rev_cols, rev_rows = load_bdms_table("revenue_vouchers")
    acc_cols, acc_rows = load_bdms_table("acceptance_vouchers")
    print(f"   签约: {len(sign_df)}, POC: {len(poc_df)}, 异常: {len(abnormal_df)}")
    print(f"   确收: {len(rev_rows)}, 验收: {len(acc_rows)}")
    
    # 2. 初始化统计表
    print("\n2. 初始化统计表...")
    conn = sqlite3.connect(BDMS_DB)
    init_stats_table(conn)
    
    # 3. 清空旧统计（幂等）
    c = conn.cursor()
    c.execute("DELETE FROM report_statistics WHERE report_month=?", (REPORT_MONTH,))
    conn.commit()
    
    # 4. 计算并存储统计
    print("\n3. 计算统计指标并存储...")
    compute_all_stats(conn, sign_df, poc_df, abnormal_df, rev_rows, acc_rows)
    
    # 5. 验证存储
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM report_statistics WHERE report_month=?", (REPORT_MONTH,))
    stat_count = c.fetchone()[0]
    print(f"\n4. 验证: {stat_count} 条统计记录已存储")
    
    c.execute("SELECT sheet_name, COUNT(*) FROM report_statistics WHERE report_month=? GROUP BY sheet_name", 
              (REPORT_MONTH,))
    for row in c.fetchall():
        print(f"   {row[0]}: {row[1]} 条")
    
    # 6. 生成 Excel
    print("\n5. 生成 Excel...")
    output = generate_excel_from_stats(conn, sign_df, poc_df, abnormal_df, rev_rows, acc_rows)
    
    conn.close()
    print(f"\n✅ 完成: {output}")


if __name__ == "__main__":
    main()
