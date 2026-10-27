"""pytest 配置：把组件根加入 sys.path，使 contract_management 可导入。"""
import os
import sys

COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)
