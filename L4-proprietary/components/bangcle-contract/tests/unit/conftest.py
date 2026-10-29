"""pytest 配置：注入组件根与 L3 contract-management 根到 sys.path。

真实文件夹具构造器已移至 file_fixtures.py（避免多 tests 目录 conftest 撞名）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_ROOT = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")

for path in (COMPONENT_ROOT, L3_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)
