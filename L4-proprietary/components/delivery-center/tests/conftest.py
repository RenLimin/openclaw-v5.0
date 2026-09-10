"""pytest 配置 — 确保 delivery_center 包可被导入"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(os.path.dirname(_HERE), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
