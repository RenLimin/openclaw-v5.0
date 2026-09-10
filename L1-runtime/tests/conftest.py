"""
L1 运行时抽象层测试配置
"""
import os
import sys

# 把 L1-runtime 加入 path，使 adapters 包可被导入
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, RUNTIME_DIR)
