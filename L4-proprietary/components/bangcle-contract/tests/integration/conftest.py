"""集成测试 sys.path 注入（组件根 + L3 contract-management）。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_ROOT = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")

for path in (COMPONENT_ROOT, L3_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)
