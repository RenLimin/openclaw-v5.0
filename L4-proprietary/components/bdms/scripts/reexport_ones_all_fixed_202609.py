#!/usr/bin/env python3
"""Re-export ALL ONES data for 202609 after bug fix."""

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

# All filters to export: name -> output filename
FILTERS = [
    ("sign", "ones_sign_202609.csv"),
    ("poc", "ones_poc_202609.csv"),
    ("abnormal", "ones_abnormal_202609.csv"),
]

def main():
    print("=== Re-exporting ALL ONES data for 202609 (after bug fix) ===")
    connector = OnesConnector()

    if not connector.authenticate():
        print("❌ Authentication failed!")
        sys.exit(1)

    print("✅ Authenticated successfully")

    # Clear existing cached files to force fresh download
    DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
    for filter_name, _ in FILTERS:
        # Clear all possible cached names
        cached_generic = DOWNLOAD_DIR / ONES_FILTERS[filter_name]["output_csv"]
        cached_generic.unlink(missing_ok=True)
        cached_month = DOWNLOAD_DIR / f"202609周报-{ONES_FILTERS[filter_name]['output_csv']}"
        cached_month.unlink(missing_ok=True)
        print(f"   Cleared cache: {cached_generic} and {cached_month}")

    print("\nStarting exports...")
    for filter_name, output_name in FILTERS:
        print(f"\n--- Exporting {filter_name} ---")
        try:
            data = connector.fetch(filter_name, month="202609", use_cache=False)
            print(f"   ✓ Fetched {len(data)} records")

            cached_path = DOWNLOAD_DIR / ONES_FILTERS[filter_name]["output_csv"]
            if cached_path.exists():
                dest_path = OUTPUT_DIR / output_name
                dest_path.unlink(missing_ok=True)
                shutil.copy(cached_path, dest_path)
                size_mb = dest_path.stat().st_size / 1024 / 1024
                print(f"   ✓ Saved to {dest_path} ({size_mb:.2f} MB)")
            else:
                print(f"   ⚠️ Cached file not found after export")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n=== Export completed ===")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")
    print("\nFinal files:")
    total_size = 0
    for f in OUTPUT_DIR.iterdir():
        size = f.stat().st_size
        total_size += size
        size_mb = size / 1024 / 1024
        print(f"  - {f.name}: {size_mb:.2f} MB ({f.stat().st_size:,} bytes)")
    print(f"\nTotal size: {total_size / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    main()
