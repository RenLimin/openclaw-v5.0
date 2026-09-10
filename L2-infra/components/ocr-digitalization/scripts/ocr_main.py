#!/usr/bin/env python3
"""
OCR 文档数字化 - 顶层 CLI 入口（与原 skill 调用方式兼容）

直接运行：
    python ocr_main.py <input> [output] [options]

等价于：
    python -m ocr_engine.cli <input> [output] [options]
"""
import os
import sys

# 将脚本所在目录加入 sys.path，确保可以 import ocr_engine 包
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from ocr_engine.cli import main

if __name__ == "__main__":
    sys.exit(main())
