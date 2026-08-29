"""BDMS 主入口

Bangcle 交付管理系统 - 主调度入口。
负责协调采集、引擎、生成器的执行流程。
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.l4.delivery_center.collectors.data_cleaner import (
    clean_ones_contract, clean_ones_poc, clean_ones_exception,
    clean_oa_contract, clean_wecom_revenue, clean_wecom_acceptance,
    clean_workhour, calibrate_contract_no
)
from scripts.l4.delivery_center.engines.join_engine import (
    join_contract_oa, join_with_legend, generate_project_summary
)
from scripts.l4.delivery_center.engines.status_engine import apply_status_engine
from scripts.l4.delivery_center.engines.scoring_engine import (
    calculate_accuracy_score, calculate_timeliness_score, calculate_department_summary
)
from scripts.l4.delivery_center.generators.delivery_report import generate_delivery_report
from scripts.l4.delivery_center.generators.revenue_report import generate_revenue_report


def run_pipeline(month: str, data_dir: str, output_dir: str) -> dict:
    """运行完整的报告生成流水线

    Args:
        month: 报告月份（YYYYMM）
        data_dir: 原始数据目录
        output_dir: 输出目录

    Returns:
        结果字典
    """
    print(f"BDMS 流水线启动: {month}")
    print(f"数据目录: {data_dir}")
    print(f"输出目录: {output_dir}")

    # Step 1: 数据清洗
    print("\n[Step 1] 数据清洗...")
    # TODO: 根据实际文件路径加载和清洗数据

    # Step 2: 业务逻辑
    print("\n[Step 2] 业务逻辑引擎...")
    # TODO: 关联查询、状态判定、考核计算

    # Step 3: 报告生成
    print("\n[Step 3] 报告生成...")
    # TODO: 生成交付月报和确收月报

    print("\n✅ 流水线完成")
    return {"status": "ok", "month": month}


def main():
    parser = argparse.ArgumentParser(description="BDMS - Bangcle 交付管理系统")
    parser.add_argument("month", help="报告月份（YYYYMM）")
    parser.add_argument("--data-dir", default=None, help="原始数据目录")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="仅验证不生成")

    args = parser.parse_args()

    result = run_pipeline(
        month=args.month,
        data_dir=args.data_dir,
        output_dir=args.output_dir or str(Path.home() / ".openclaw" / "data" / "reports")
    )

    print(f"\n结果: {result}")


if __name__ == "__main__":
    main()
