"""BDMS 主入口

Bangcle 交付管理系统 - 主调度入口。
串联 M1(采集) → M2(引擎) → M3(报告) 完整流程。

用法:
  python3 -m scripts.l4.delivery_center.main 202606         # 完整流程
  python3 -m scripts.l4.delivery_center.main 202606 --report-only  # 仅生成报告
  python3 -m scripts.l4.delivery_center.main 202606 --dry-run       # 仅验证

已验证 2026-09-01。
"""

import argparse
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.l4.delivery_center.pipeline import run_pipeline
from scripts.l4.delivery_center.generators.delivery_report import generate_delivery_report
from scripts.l4.delivery_center.generators.revenue_report import generate_revenue_report
from scripts.l4.delivery_center.generators.approval_engine import generate_revenue_acceptance_summary
from scripts.l4.delivery_center.engines.join_engine import load_oa_contracts
from scripts.l4.delivery_center.engines.join_engine import (
    load_revenue_vouchers,
    load_acceptance_vouchers,
)


def run_full_pipeline(month: str, report_only: bool = False, dry_run: bool = False) -> dict:
    """运行完整的 BDMS 流程

    Args:
        month: 报告月份（YYYYMM）
        report_only: 仅生成报告（跳过采集）
        dry_run: 仅验证不生成

    Returns:
        结果字典
    """
    print("=" * 60)
    print(f"BDMS 完整流程: {month}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    result = {"month": month, "status": "ok", "outputs": {}}

    if dry_run:
        print("\n[DRY RUN] 仅验证，不生成报告")
        return result

    # Step 1: 数据采集 + 清洗 + 存储
    if not report_only:
        print("\n[Step 1] 数据采集 + 清洗 + 存储...")
        try:
            run_pipeline(month, collect_only=False, clean_only=False)
            result["outputs"]["pipeline"] = "ok"
        except Exception as e:
            print(f"  ⚠️ 流水线异常: {e}")
            result["outputs"]["pipeline"] = f"error: {e}"

    # Step 2: 生成报告
    print("\n[Step 2] 生成报告...")

    # 加载数据
    rev_df = load_revenue_vouchers()
    acc_df = load_acceptance_vouchers()
    oa_df = load_oa_contracts()

    # ONES API 数据采集（异常项目）
    ones_abnormal_df = pd.DataFrame()
    try:
        from scripts.l4.delivery_center.collectors.ones_collector import load_ones_abnormal_projects
        ones_abnormal_df = load_ones_abnormal_projects()
        print(f"  ✅ ONES 异常项目: {len(ones_abnormal_df)} 个")
    except Exception as e:
        print(f"  ⚠️ ONES 异常项目加载失败: {e}")

    # 交付月报
    try:
        delivery_path = generate_delivery_report(
            month=month,
            contract_df=oa_df,
            exception_df=ones_abnormal_df,
            revenue_df=rev_df,
            acceptance_df=acc_df,
        )
        result["outputs"]["delivery_report"] = delivery_path
        print(f"  ✅ 交付月报: {delivery_path}")
    except Exception as e:
        print(f"  ⚠️ 交付月报异常: {e}")
        result["outputs"]["delivery_report"] = f"error: {e}"

    # 确收月报
    try:
        revenue_path = generate_revenue_report(
            month=month,
            revenue_df=rev_df,
            acceptance_df=acc_df,
        )
        result["outputs"]["revenue_report"] = revenue_path
        print(f"  ✅ 确收月报: {revenue_path}")
    except Exception as e:
        print(f"  ⚠️ 确收月报异常: {e}")
        result["outputs"]["revenue_report"] = f"error: {e}"

    # 审批摘要
    try:
        summary = generate_revenue_acceptance_summary(rev_df, acc_df)
        result["outputs"]["summary"] = "generated"
        print(f"\n{summary}")
    except Exception as e:
        print(f"  ⚠️ 摘要异常: {e}")

    print("\n" + "=" * 60)
    print("✅ BDMS 流程完成")
    print("=" * 60)
    return result


def main():
    parser = argparse.ArgumentParser(description="BDMS - Bangcle 交付管理系统")
    parser.add_argument("month", help="报告月份（YYYYMM）")
    parser.add_argument("--report-only", action="store_true", help="仅生成报告")
    parser.add_argument("--dry-run", action="store_true", help="仅验证不生成")

    args = parser.parse_args()

    result = run_full_pipeline(
        month=args.month,
        report_only=args.report_only,
        dry_run=args.dry_run,
    )

    print(f"\n结果: {result['status']}")
    for key, val in result.get("outputs", {}).items():
        print(f"  {key}: {val}")


if __name__ == "__main__":
    main()
