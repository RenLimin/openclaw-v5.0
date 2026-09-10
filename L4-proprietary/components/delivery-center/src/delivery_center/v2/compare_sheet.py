#!/usr/bin/env python3
"""
交付月报 V2 — 单 Sheet 对比工具

用来快速对比生成表和参考表某个 Sheet 的差异，定位问题。
"""

import sys
import openpyxl
import pandas as pd
from pathlib import Path

REFERENCE = "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202606/2026交付月报-20260630.xlsx"
GENERATED = str(Path.home() / ".openclaw" / "data" / "reports" / "交付月报-202606-v2.xlsx")


def load_sheet_df(file_path, sheet_name, header_row=1):
    """加载一个 sheet 为 DataFrame，header_row 是表头所在行（1-based）"""
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb[sheet_name]

    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        rows.append(row)
        if i > header_row + 20000:  # 防止太大
            break

    wb.close()

    # 从 header_row 开始作为表头
    headers = list(rows[header_row - 1])
    data_rows = rows[header_row:]  # 表头之后的数据

    df = pd.DataFrame(data_rows, columns=headers)
    return df


def compare_sheet(sheet_name, ref_header_row=2, gen_header_row=2):
    """对比一个 Sheet"""
    print(f"\n{'='*60}")
    print(f"📊 对比 Sheet: {sheet_name}")
    print(f"{'='*60}")

    df_ref = load_sheet_df(REFERENCE, sheet_name, header_row=ref_header_row)
    df_gen = load_sheet_df(GENERATED, sheet_name, header_row=gen_header_row)

    print(f"\n参考表: {len(df_ref)} 行 × {len(df_ref.columns)} 列")
    print(f"生成表: {len(df_gen)} 行 × {len(df_gen.columns)} 列")

    # 1. 列名对比
    ref_cols = list(df_ref.columns)
    gen_cols = list(df_gen.columns)

    only_ref = [c for c in ref_cols if c not in gen_cols]
    only_gen = [c for c in gen_cols if c not in ref_cols]
    common = [c for c in ref_cols if c in gen_cols]

    print(f"\n列对比:")
    print(f"  共有列: {len(common)}")
    if only_ref:
        print(f"  ❌ 仅参考表有 ({len(only_ref)}):")
        for c in only_ref[:20]:
            print(f"    - {c}")
        if len(only_ref) > 20:
            print(f"    ... 还有 {len(only_ref) - 20} 列")
    if only_gen:
        print(f"  ⚠️  仅生成表有 ({len(only_gen)}):")
        for c in only_gen[:20]:
            print(f"    - {c}")
        if len(only_gen) > 20:
            print(f"    ... 还有 {len(only_gen) - 20} 列")

    # 2. 行数差异分析
    if len(df_ref) != len(df_gen):
        print(f"\n❌ 行数差异: 参考 {len(df_ref)} vs 生成 {len(df_gen)} (差 {len(df_gen) - len(df_ref)})")

    # 3. 对共有列，做数据对比（抽样几个关键列）
    if common:
        # 找主键
        key_candidates = ["BI履约ID", "ID", "销售合同编号"]
        key_col = None
        for k in key_candidates:
            if k in common:
                key_col = k
                break

        if key_col:
            print(f"\n🔑 主键列: {key_col}")
            ref_keys = set(df_ref[key_col].dropna().astype(str))
            gen_keys = set(df_gen[key_col].dropna().astype(str))
            only_ref_keys = ref_keys - gen_keys
            only_gen_keys = gen_keys - ref_keys
            print(f"  参考表唯一键: {len(ref_keys)}")
            print(f"  生成表唯一键: {len(gen_keys)}")
            if only_ref_keys:
                print(f"  ❌ 仅参考表有 ({len(only_ref_keys)}):")
                for k in sorted(list(only_ref_keys))[:10]:
                    print(f"    - {k}")
            if only_gen_keys:
                print(f"  ⚠️  仅生成表有 ({len(only_gen_keys)}):")
                for k in sorted(list(only_gen_keys))[:10]:
                    print(f"    - {k}")

        # 抽样几列的值分布对比
        sample_cols = common[:5] + [c for c in ["状态", "项目状态", "合同归档年度"] if c in common]
        print(f"\n📈 抽样列值分布对比:")
        for col in sample_cols[:8]:
            ref_vals = df_ref[col].value_counts(dropna=False).head(5).to_dict()
            gen_vals = df_gen[col].value_counts(dropna=False).head(5).to_dict()
            print(f"\n  列: {col}")
            print(f"    参考: {ref_vals}")
            print(f"    生成: {gen_vals}")

    return {
        "ref_rows": len(df_ref),
        "gen_rows": len(df_gen),
        "ref_cols": len(df_ref.columns),
        "gen_cols": len(df_gen.columns),
        "only_ref": only_ref,
        "only_gen": only_gen,
        "common": common,
    }


if __name__ == "__main__":
    sheet = sys.argv[1] if len(sys.argv) > 1 else "签约"
    ref_header = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    gen_header = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    compare_sheet(sheet, ref_header, gen_header)
