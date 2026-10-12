#!/usr/bin/env python3
"""Import 202610 签约项目异常处置 CSV into BDMS database."""

import sys
from pathlib import Path

# Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR / "L4-proprietary" / "components" / "bdms"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bdms.modules.integration.connectors.ones_connector import OnesConnector
from bdms.core.db import transaction
from bdms.modules.delivery_report.service import DeliveryReportService

CSV_PATH = PROJECT_ROOT / "data" / "raw" / "202610" / "202610-签约项目异常处置.csv"
MONTH = "202610"

def main():
    print(f"=== Importing 202610-签约项目异常处置 into BDMS ===")
    print(f"CSV: {CSV_PATH}")
    
    if not CSV_PATH.exists():
        print(f"❌ File not found: {CSV_PATH}")
        sys.exit(1)
    
    connector = OnesConnector()
    data = connector.fetch(file_path=str(CSV_PATH))
    print(f"✅ Read {len(data)} raw records from CSV")
    
    normalized = connector.normalize(data)
    print(f"✅ Normalized {len(normalized)} records")
    
    service = DeliveryReportService()
    with transaction() as conn:
        inserted = 0
        for record in normalized:
            try:
                service.insert_row(conn, MONTH, record)
                inserted += 1
            except Exception as e:
                print(f"⚠️  Failed to insert record: {e}")
        
        print(f"\n✅ Import completed! Inserted {inserted}/{len(normalized)} records")
    
    sys.exit(0)

if __name__ == "__main__":
    main()
