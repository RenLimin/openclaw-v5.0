#!/usr/bin/env python3
"""Export a single ONES filter for 202609 - step by step to avoid timeout."""

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

def main(filter_name):
    print(f"=== Exporting single ONES filter: {filter_name} for 202609 ===")
    connector = OnesConnector()

    if not connector.authenticate():
        print("❌ Authentication failed!")
        sys.exit(1)

    print("✅ Authenticated successfully")

    # Clear existing cached
    DOWNLOAD_DIR = Path.home() / ".openclaw" / "data" / "ones_exports"
    output_name = f"ones_{filter_name}_202609.csv"

    # Clear cache
    cached_generic = DOWNLOAD_DIR / ONES_FILTERS[filter_name]["output_csv"]
    cached_generic.unlink(missing_ok=True)
    cached_month = DOWNLOAD_DIR / f"202609周报-{ONES_FILTERS[filter_name]['output_csv']}"
    cached_month.unlink(missing_ok=True)
    dest_path = OUTPUT_DIR / output_name
    dest_path.unlink(missing_ok=True)
    print(f"   Cleared existing cache and output")

    print(f"\nStarting export...")
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
            sys.exit(1)
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"\n✅ {filter_name} export completed!")
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python export_single_ones_202609.py <filter_name>")
        print("Filters: sign, poc, abnormal")
        sys.exit(1)
    main(sys.argv[1])
