#!/usr/bin/env python3
"""
CLI 快捷入口 — 转发到 bangcle_ppt.cli.pptgen.main
直接运行: python cli/pptgen.py ...
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from bangcle_ppt.cli.pptgen import main

if __name__ == "__main__":
    sys.exit(main())
