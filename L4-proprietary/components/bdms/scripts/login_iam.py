#!/usr/bin/env python3
"""Login to IAM to get fresh cookies.

凭据只从 ~/.openclaw/secrets/iam.username 与 iam.password 读取，
不在代码中硬编码任何明文。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bdms.modules.integration.adapters.browser_adapter import (
    login_iam,
    _iam_credentials,
)


def main():
    print("=== Logging into IAM ===")
    username, password = _iam_credentials()
    if not username or not password:
        print("❌ IAM 凭据缺失：请配置 ~/.openclaw/secrets/iam.username 与 iam.password")
        sys.exit(2)

    success = login_iam(username, password)
    if success:
        print("✅ IAM login successful, cookies saved")
        sys.exit(0)
    else:
        print("❌ IAM login failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
