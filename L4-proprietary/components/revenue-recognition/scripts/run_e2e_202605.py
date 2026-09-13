#!/usr/bin/env python3
"""Wrapper to run e2e for 202605 period without modifying source files."""

import sys
import os
from pathlib import Path

# Add src to path
script_dir = Path(__file__).resolve().parent
project_dir = script_dir.parent
src_dir = project_dir / "src"
sys.path.insert(0, str(src_dir))

# Monkey-patch config before importing modules
from revenue_recognition.v1 import config
config.MANUAL_REPORT_PATH = Path(
    "/Users/bangcle/Bangcle Workspace/01. Management/2026/2026团队报告/202605/"
    "2026年计划确收&实际确收对比表202601-05-0627-差异分析.xlsx"
)

from revenue_recognition.v1.db import init_db
from revenue_recognition.v1.importer import import_all
from revenue_recognition.v1.engine import RevenueEngine
from revenue_recognition.v1.exporter import RevenueExporter

def main():
    period = "202605"
    print("=" * 60)
    print(f"L4 确收管理模块 — 报表自动化 (period={period})")
    print("=" * 60)

    # Phase 1: 初始化数据库
    print("\n[Phase 1] 初始化数据库...")
    init_db()

    # Phase 2: 数据导入
    print("\n[Phase 2] 从手工报表导入数据...")
    result = import_all()
    print(f"  导入结果: {result}")

    # Phase 3: 计算引擎
    print("\n[Phase 3] 计算引擎...")
    engine = RevenueEngine()
    monthly = engine.compute_monthly_detail(period)
    print(f"  月度明细数: {len(monthly)}")

    perf = engine.compute_performance_summary(period)
    print(f"  履约汇总: 新签预算={perf['new']['budget']}, 递延预算={perf['deferred']['budget']}")

    # Phase 4: 导出 Excel
    print("\n[Phase 4] 导出 Excel 报表...")
    exporter = RevenueExporter(engine)
    output_path = exporter.export(period)
    print(f"  输出路径: {output_path}")

    print(f"\n✅ 202605 端到端完成!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
