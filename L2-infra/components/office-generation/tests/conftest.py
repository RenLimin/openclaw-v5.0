import sys
import os

# 让 src 下的 office_engine 包可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 确保 pytest 不尝试收集上层 __init__.py 作为测试包
collect_ignore = ["../__init__.py"]
