#!/usr/bin/env python3
"""Export ONES data for 202609 delivery report."""

import sys
import os
import shutil
from pathlib import Path

# Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bdms.modules.integration.connectors.ones_connector import OnesConnector

# Output directory
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "202609"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Filters to export: name -> output filename
FILTERS = [
    ("sign", "ones_sign_202609.csv"),
    ("poc", "ones_poc_202609.csv"),
    ("abnormal", "ones_abnormal_202609.csv"),
    # 确收交接和验收交接需要另外处理？不对，看代码里FILTERS只定义了三个，需要确认下
]

def main():
    print("=== Starting ONES data export for 202609 ===")
    connector = OnesConnector()

    if not connector.authenticate():
        print("❌ Authentication failed!")
        sys.exit(1)

    print("✅ Authenticated successfully")

    for filter_name, output_name in FILTERS:
        print(f"\n--- Exporting {filter_name} ---")
        try:
            data = connector.fetch(filter_name, month="202609", use_cache=False)
            print(f"   Fetched {len(data)} records")

            # Find the cached csv and move it to output dir
            cached_path = Path.home() / ".openclaw" / "data" / "ones_exports" / connector._find_cached_csv(filter_name, "202609")
            if cached_path.exists():
                dest_path = OUTPUT_DIR / output_name
                shutil.copy(cached_path, dest_path)
                print(f"   Saved to {dest_path}")
            else:
                print(f"   ⚠️ Cached file not found")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

    print("\n=== Export completed ===")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")

if __name__ == "__main__":
    main()
