#!/usr/bin/env python3
"""Generate BDMS Delivery Report for 202610 with new abnormal data."""

import sys
from pathlib import Path

# Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR / "L4-proprietary" / "components" / "bdms"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bdms.modules.delivery_report.service import DeliveryReportService

MONTH = "202610"

def main():
    print(f"=== Generating BDMS Delivery Report for {MONTH} ===")
    
    service = DeliveryReportService()
    
    try:
        # 强制重新生成，因为有新的异常数据
        result = service.generate(MONTH, mode="regenerate")
        print(f"\n✅ 生成完成!")
        print(f"   月份: {result['month']}")
        print(f"   动作: {result['action']}")
        print(f"   总行数: {result['total_rows']}")
        print(f"   Sheet统计:")
        for sheet, count in result['sheets'].items():
            print(f"     - {sheet}: {count} 行")
        print(f"   审核状态: {result['review_status']}")
        
        if 'validation' in result and 'summary' in result['validation']:
            print(f"\n   校验结果:")
            print(f"     错误: {result['validation']['summary']['total_errors']}")
            print(f"     警告: {result['validation']['summary']['total_warnings']}")
        
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
