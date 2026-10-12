#!/usr/bin/env python3
"""Export ONES POC and abnormal data for 202609 - after sign export done."""

import sys
import os
import shutil
from pathlib import Path

# Add src to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bdms.modules.integration.connectors.ones_connector import OnesConnector
from bdms.modules.integration.connectors.ones_connector import FILTERS as ONES_FILTERS

# Output directory
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "202609"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Only POC and abnormal
FILTERS = [
    ("poc", "ones_poc_202609.csv"),
    ("abnormal", "ones_abnormal_202609.csv"),
]

def main():
    print("=== Exporting ONES POC and abnormal data 202609 ===")
    connector = OnesConnector()

    if not connector.authenticate():
        print("❌ Authentication failed!")
        sys.exit(1)

    print("✅ Authenticated successfully")

    DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"

    for filter_name, output_name in FILTERS:
        print(f"\n--- Exporting {filter_name} ---")
        # Clear cache first
        cached_path = DOWNLOAD_DIR / ONES_FILTERS[filter_name]["output_csv"]
        if cached_path.exists():
            print(f"   Removing old cache: {cached_path}")
            cached_path.unlink()

        try:
            data = connector.fetch(filter_name, month="202609", use_cache=False)
            print(f"   Fetched {len(data)} records")

            cached_path = DOWNLOAD_DIR / ONES_FILTERS[filter_name]["output_csv"]
            if cached_path.exists():
                dest_path = OUTPUT_DIR / output_name
                shutil.copy(cached_path, dest_path)
                size_mb = dest_path.stat().st_size / 1024 / 1024
                print(f"   Saved to {dest_path} ({size_mb:.2f} MB)")
            else:
                print(f"   ⚠️ Downloaded file not found")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n=== Done ===")
    print("\nFiles in output:")
    for f in OUTPUT_DIR.iterdir():
        size = f.stat().st_size / 1024 / 1024
        print(f"  {f.name}: {size:.2f} MB")

if __name__ == "__main__":
    main()
