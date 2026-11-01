#!/usr/bin/env python3
"""Force re-run 202610 delivery report generation, bypass job cache."""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bdms.core.config import get_config
from bdms.modules.delivery_report.service import DeliveryReportService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

MONTH = "202610"

def main():
    print(f"=== Generating BDMS Delivery Report for {MONTH} (force regenerate) ===")
    _ = get_config()  # 初始化配置
    service = DeliveryReportService()
    result = service.generate(MONTH, mode="regenerate", refetch_sources=True)
    print()
    print("✅ 生成完成！")
    print(f" 报告路径: {result}")

if __name__ == "__main__":
    main()
