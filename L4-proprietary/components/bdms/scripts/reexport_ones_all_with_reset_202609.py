#!/usr/bin/env python3
"""Re-export ALL ONES data for 202609 with reset step added (fix for data size issue)."""

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
    print("=== Re-export ALL ONES data for 202609 (with reset before export) ===")
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
        # Clear our target files
        target = OUTPUT_DIR / FILTERS[[name for name, _ in FILTERS].index(filter_name)][1]
        target.unlink(missing_ok=True)
        print(f"   Cleared cache for {filter_name}")

    print("\nStarting exports with reset step...")
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
                lines = sum(1 for _ in open(dest_path))
                print(f"   ✓ Saved to {dest_path} ({size_mb:.2f} MB, {lines} lines)")
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
    total_lines = 0
    for f in OUTPUT_DIR.iterdir():
        if f.suffix == ".csv":
            size = f.stat().st_size
            lines = sum(1 for _ in open(f))
            total_size += size
            total_lines += lines
            size_mb = size / 1024 / 1024
            print(f"  - {f.name}: {size_mb:.2f} MB, {lines} lines")
    print(f"\nTotal: {total_lines} lines, {total_size / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    main()
