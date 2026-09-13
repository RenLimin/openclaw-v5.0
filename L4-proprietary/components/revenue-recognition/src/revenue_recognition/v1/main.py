"""确收管理模块 — 主入口"""

import sys
from pathlib import Path
from datetime import datetime

from .config import MANUAL_REPORT_PATH, OUTPUT_DIR
from .db import init_db
from .importer import import_all
from .engine import RevenueEngine
from .exporter import RevenueExporter
from .validator import validate_all_sheets, print_report


def main():
    """完整流程: 导入 → 计算 → 导出 → 核对"""
    print("=" * 60)
    print("L4 确收管理模块 — 报表自动化")
    print("=" * 60)

    period = "202606"

    # Phase 1: 初始化数据库
    print("\n[Phase 1] 初始化数据库...")
    init_db()

    # Phase 2: 数据导入
    print("\n[Phase 2] 从手工报表导入数据...")
    result = import_all()
    print(f"  导入结果: {result}")

    # Phase 3: 计算引擎验证
    print("\n[Phase 3] 计算引擎...")
    engine = RevenueEngine()
    summary = engine.compute_summary(period)
    print(f"  新签期间数: {len(summary['new'])}")
    print(f"  递延期间数: {len(summary['deferred'])}")

    monthly = engine.compute_monthly_detail(period)
    print(f"  月度明细数: {len(monthly)}")

    perf = engine.compute_performance_summary(period)
    print(f"  履约汇总: 新签预算={perf['new']['budget']}, 递延预算={perf['deferred']['budget']}")

    # Phase 4: 导出 Excel
    print("\n[Phase 4] 导出 Excel 报表...")
    exporter = RevenueExporter(engine)
    output_path = exporter.export(period)
    print(f"  输出路径: {output_path}")

    # Phase 5: 核对验证
    print("\n[Phase 5] 核对验证...")
    reports = validate_all_sheets(output_path)
    print_report(reports)

    # 输出最终结果
    all_passed = all(r.is_passed for r in reports)
    print(f"\n{'=' * 60}")
    if all_passed:
        print("全流程通过！报表自动化完成。")
    else:
        print("存在差异，请检查上方核对报告。")
    print(f"{'=' * 60}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
