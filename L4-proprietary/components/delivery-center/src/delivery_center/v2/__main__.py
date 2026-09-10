"""
BDMS v2 顶层入口 — python -m v2.cli.bdmsctl 的便捷入口

用法:
    cd delivery-center
    python -m v2 generate 2026-08
    python -m v2 list
    python -m v2 serve
"""
import sys
from v2.cli.bdmsctl import main

if __name__ == "__main__":
    sys.exit(main())
