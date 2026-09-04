"""BDMS 数据流水线

串联数据采集 → 清洗 → SQLite 存储的完整流程。

用法:
  python3 pipeline.py 202606          # 采集+清洗+存储 202606 月份数据
  python3 pipeline.py 202606 --collect-only  # 仅采集
  python3 pipeline.py 202606 --clean-only    # 仅清洗+存储（使用已采集文件）
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.l4.delivery_center.db import init_db, executemany, query
from scripts.l4.delivery_center.collectors.data_cleaner import (
    calibrate_contract_no,
    clean_oa_contract,
    clean_wecom_revenue,
    clean_wecom_acceptance,
)


def store_oa_contracts(excel_path: str) -> int:
    """存储 OA 合同台账到 SQLite"""
    import pandas as pd

    df = clean_oa_contract(excel_path)
    if df.empty:
        return 0

    # 映射列名
    col_map = {
        "uf_xsht_xxb_htbh": "htbh",
        "uf_xsht_xxb_htmcspan": "合同名称",
        "uf_xsht_xxb_khmcspan": "客户名称",
        "uf_xsht_xxb_qyje": "签约金额",
        "uf_xsht_xxb_dqhtgjrspan": "责任销售",
        "zrxsssbmspan": "责任销售部门",
        "uf_xsht_xxb_qyrspan": "签约销售",
        "uf_xsht_xxb_qyrsstd1span": "签约销售团队",
        "modedatacreatedate": "创建日期",
        "uf_xsht_xxb_sqsj": "申请日期",
        "fwkssj": "服务开始日期",
        "fwjssj": "服务结束日期",
        "uf_xsht_xxb_zqhdlspan": "直签或代理",
        "uf_xsht_xxb_htfl": "合同分类",
        "uf_xsht_xxb_htgdztspan": "归档状态",
    }

    # 只保留存在的列
    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename)

    # 确保核心列存在
    for col in ["htbh", "合同名称", "客户名称"]:
        if col not in df.columns:
            print(f"  ⚠️ 缺少核心列: {col}")
            return 0

    # 合同编号校准
    if "htbh" in df.columns:
        df["htbh"] = df["htbh"].apply(calibrate_contract_no)

    # 转换为记录
    records = []
    for _, row in df.iterrows():
        records.append((
            str(row.get("htbh", "")),
            str(row.get("合同名称", ""))[:200],
            str(row.get("客户名称", ""))[:200],
            float(row["签约金额"]) if pd.notna(row.get("签约金额")) else None,
            str(row.get("责任销售", ""))[:50],
            str(row.get("责任销售部门", ""))[:100],
            str(row.get("签约销售", ""))[:50],
            str(row.get("签约销售团队", ""))[:100],
            str(row.get("创建日期", "")),
            str(row.get("申请日期", "")),
            str(row.get("服务开始日期", "")),
            str(row.get("服务结束日期", "")),
            str(row.get("直签或代理", ""))[:20],
            str(row.get("合同分类", ""))[:50],
            str(row.get("归档状态", ""))[:50],
        ))

    sql = """INSERT INTO oa_contracts
        (htbh, 合同名称, 客户名称, 签约金额, 责任销售, 责任销售部门,
         签约销售, 签约销售团队, 创建日期, 申请日期, 服务开始日期,
         服务结束日期, 直签或代理, 合同分类, 归档状态)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(htbh) DO UPDATE SET
            合同名称=excluded.合同名称, 客户名称=excluded.客户名称,
            签约金额=excluded.签约金额, 责任销售=excluded.责任销售,
            导入时间=CURRENT_TIMESTAMP"""

    count = executemany(sql, records)
    print(f"  ✅ OA 合同台账: {count} 行已存储")
    return count


def store_revenue(csv_path: str) -> int:
    """存储确收凭证到 SQLite"""
    import pandas as pd

    df = clean_wecom_revenue(csv_path)
    if df.empty:
        return 0

    col_map = {
        "标题": "合同名称",
        "ID": "voucher_id",
        "BI履约ID": "bi_id",
        "合同编号": "合同编号",
        "客户名称": "客户名称",
        "销售部门": "销售部门",
        "项目经理": "项目经理",
        "交接日期": "交接日期",
        "财务": "财务",
        "是否接收": "是否接收",
    }
    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename)

    if "合同编号" in df.columns:
        df["合同编号"] = df["合同编号"].apply(calibrate_contract_no)

    records = []
    for _, row in df.iterrows():
        if pd.isna(row.get("合同编号")) and pd.isna(row.get("合同名称")):
            continue
        records.append((
            str(row.get("voucher_id", ""))[:50],
            str(row.get("bi_id", ""))[:100],
            str(row.get("合同编号", ""))[:100],
            str(row.get("合同名称", ""))[:200],
            str(row.get("客户名称", ""))[:200],
            str(row.get("销售部门", ""))[:100],
            str(row.get("项目经理", ""))[:50],
            str(row.get("交接日期", "")),
            str(row.get("财务", ""))[:50],
            str(row.get("是否接收", ""))[:20],
        ))

    sql = """INSERT INTO revenue_vouchers
        (voucher_id, bi_id, 合同编号, 合同名称, 客户名称, 销售部门,
         项目经理, 交接日期, 财务, 是否接收)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    count = executemany(sql, records)
    print(f"  ✅ 确收凭证: {count} 行已存储")
    return count


def store_acceptance(csv_path: str) -> int:
    """存储验收凭证到 SQLite"""
    import pandas as pd

    df = clean_wecom_acceptance(csv_path)
    if df.empty:
        return 0

    col_map = {
        "合同名称": "合同名称",
        "标题": "标题",
        "ID": "voucher_id",
        "BI履约ID": "bi_id",
        "验收单编号-财务端": "验收单编号",
        "合同编号": "合同编号",
        "客户名称": "客户名称",
        "项目经理": "项目经理",
        "交接日期": "交接日期",
        "验收方式": "验收方式",
        "截至目前全部/部分验收": "全部或部分",
        "财务": "财务",
        "财务是否接收": "财务是否接收",
    }
    rename = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename)

    if "合同编号" in df.columns:
        df["合同编号"] = df["合同编号"].apply(calibrate_contract_no)

    records = []
    for _, row in df.iterrows():
        if pd.isna(row.get("合同编号")) and pd.isna(row.get("合同名称")):
            continue
        records.append((
            str(row.get("voucher_id", ""))[:50],
            str(row.get("bi_id", ""))[:100],
            str(row.get("合同编号", ""))[:100],
            str(row.get("合同名称", ""))[:200],
            str(row.get("客户名称", ""))[:200],
            str(row.get("项目经理", ""))[:50],
            str(row.get("验收单编号", ""))[:50],
            str(row.get("交接日期", "")),
            str(row.get("验收方式", ""))[:50],
            str(row.get("全部或部分", ""))[:20],
            str(row.get("财务", ""))[:50],
            str(row.get("财务是否接收", ""))[:20],
        ))

    sql = """INSERT INTO acceptance_vouchers
        (voucher_id, bi_id, 合同编号, 合同名称, 客户名称, 项目经理,
         验收单编号, 交接日期, 验收方式, 全部或部分, 财务, 财务是否接收)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    count = executemany(sql, records)
    print(f"  ✅ 验收凭证: {count} 行已存储")
    return count


def store_workhours(json_path: str, month: str) -> int:
    """存储工时数据到 SQLite"""
    import json as json_mod

    data = json_mod.loads(Path(json_path).read_text(encoding="utf-8"))
    records_data = data.get("data", [])

    records = []
    for r in records_data:
        records.append((
            r.get("work_item", "")[:200],
            float(r.get("total_hours", 0)),
            float(r.get("migrated_hours", 0)),
            float(r.get("remaining_hours", 0)),
            month,
        ))

    sql = """INSERT INTO workhours (工作项, 总工时, 迁移工时, 剩余工时, 月份)
        VALUES (?, ?, ?, ?, ?)"""

    count = executemany(sql, records)
    print(f"  ✅ 工时数据: {count} 行已存储")
    return count


def run_pipeline(month: str, collect_only: bool = False, clean_only: bool = False):
    """运行完整的数据流水线

    Args:
        month: 报告月份（YYYYMM）
        collect_only: 仅采集
        clean_only: 仅清洗+存储
    """
    import pandas as pd

    print("=" * 60)
    print(f"BDMS 数据流水线: {month}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 初始化数据库
    init_db()

    base_data = Path.home() / ".openclaw" / "data"
    oa_exports = base_data / "oa_exports"
    wecom_exports = base_data / "wecom_exports"
    workhour_exports = base_data / "workhour_exports"

    if not clean_only:
        # Step 1: 采集
        print("\n[Step 1] 数据采集...")

        # OA 合同台账
        oa_file = oa_exports / f"contract_ledger_{month}.xlsx"
        if not oa_file.exists():
            print(f"  ⚠️ OA 合同台账不存在: {oa_file}")
            print("  请先运行: python3 -m scripts.l4.delivery_center.collectors.oa_collector {month}")

        # WeCom
        from scripts.l4.delivery_center.collectors.wecom_collector import collect_from_local
        collect_from_local(month)

        # 工时
        wh_json = workhour_exports / f"workhour_{month}.json"
        if not wh_json.exists():
            print(f"  ⚠️ 工时数据不存在: {wh_json}")

    if collect_only:
        print("\n=== 采集完成（跳过清洗）===")
        return

    # Step 2: 清洗 + 存储
    print("\n[Step 2] 清洗 + 存储...")

    # OA 合同台账
    oa_file = oa_exports / f"contract_ledger_{month}.xlsx"
    if oa_file.exists():
        print("\n  [OA 合同台账]")
        store_oa_contracts(str(oa_file))

    # 确收凭证
    rev_file = wecom_exports / f"revenue_{month}.csv"
    if rev_file.exists():
        print("\n  [确收凭证]")
        store_revenue(str(rev_file))

    # 验收凭证
    acc_file = wecom_exports / f"acceptance_{month}.csv"
    if acc_file.exists():
        print("\n  [验收凭证]")
        store_acceptance(str(acc_file))

    # 工时
    wh_json = workhour_exports / f"workhour_{month}.json"
    if wh_json.exists():
        print("\n  [工时数据]")
        store_workhours(str(wh_json), month)

    # 统计
    print("\n[Step 3] 存储统计...")
    tables = ["oa_contracts", "revenue_vouchers", "acceptance_vouchers", "workhours"]
    for table in tables:
        result = query(f"SELECT COUNT(*) as cnt FROM {table}")
        count = result[0]["cnt"] if result else 0
        print(f"  {table}: {count} 行")

    print("\n" + "=" * 60)
    print("✅ 流水线完成")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BDMS 数据流水线")
    parser.add_argument("month", help="报告月份（YYYYMM）")
    parser.add_argument("--collect-only", action="store_true", help="仅采集")
    parser.add_argument("--clean-only", action="store_true", help="仅清洗+存储")
    args = parser.parse_args()

    run_pipeline(args.month, args.collect_only, args.clean_only)
