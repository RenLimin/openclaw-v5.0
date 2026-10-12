#!/usr/bin/env python3
"""Re-export ALL ONES data for 202609 delivery report as requested."""

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

# All filters to export: name -> output filename
from bdms.modules.integration.connectors.ones_connector import FILTERS as ONES_FILTERS
FILTERS = [
    ("sign", "ones_sign_202609.csv"),
    ("poc", "ones_poc_202609.csv"),
    ("abnormal", "ones_abnormal_202609.csv"),
]

def main():
    print("=== Re-exporting ALL ONES data for 202609 (fresh download) ===")
    connector = OnesConnector()

    if not connector.authenticate():
        print("❌ Authentication failed!")
        sys.exit(1)

    print("✅ Authenticated successfully")

    # Clear existing cached files to force fresh download
    DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
    for filter_name, _ in FILTERS:
        cached = connector._find_cached_csv(filter_name, "202609")
        if cached:
            print(f"   Removing existing cached: {cached}")
            cached.unlink(missing_ok=True)
        generic_cached = DOWNLOAD_DIR / ONES_FILTERS[filter_name]["output_csv"]
        generic_cached.unlink(missing_ok=True)

    for filter_name, output_name in FILTERS:
        print(f"\n--- Exporting {filter_name} (fresh) ---")
        try:
            data = connector.fetch(filter_name, month="202609", use_cache=False)
            print(f"   Fetched {len(data)} records")

            # Find the cached csv and move it to output dir
            cached_path = DOWNLOAD_DIR / ONES_FILTERS[filter_name]["output_csv"]
            if not cached_path.exists():
                cached_path = connector._find_cached_csv(filter_name, "202609")
            if cached_path and cached_path.exists():
                dest_path = OUTPUT_DIR / output_name
                shutil.copy(cached_path, dest_path)
                size_mb = dest_path.stat().st_size / 1024 / 1024
                print(f"   Saved to {dest_path} ({size_mb:.2f} MB)")
            else:
                print(f"   ⚠️ Cached file not found")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n=== Export completed ===")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")
    print("\nCurrent files in output directory:")
    total_size = 0
    for f in OUTPUT_DIR.iterdir():
        size = f.stat().st_size
        total_size += size
        print(f"  - {f.name} ({size / 1024 / 1024:.2f} MB)")
    print(f"\nTotal size: {total_size / 1024 / 1024:.2f} MB")

if __name__ == "__main__":
    main()
