# -*- coding: utf-8 -*-
"""共享测试配置 — 将 workspace 根目录加入 sys.path 以支持 L3.business 导入。"""

import sys
from pathlib import Path

# 将 workspace 根目录加入 sys.path，使 L3.business... 导入可用
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

# 同时将组件根目录加入 sys.path，使直接导入也可用
COMPONENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COMPONENT_ROOT))
