#!/usr/bin/env python3
"""Login to IAM to get fresh cookies."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bdms.modules.integration.adapters.browser_adapter import login_iam

def main():
    print("=== Logging into IAM ===")
    # Use stored credentials
    username = "limin.ren"
    password = "June-123"

    success = login_iam(username, password)
    if success:
        print("✅ IAM login successful, cookies saved")
        sys.exit(0)
    else:
        print("❌ IAM login failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
