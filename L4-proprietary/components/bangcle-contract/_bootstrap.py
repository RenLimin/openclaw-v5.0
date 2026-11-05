"""跨组件 sys.path 引导（L4 -> L3/L2，L4 同级 product-kb）。

组件自包含运行：import 本模块即把所需组件根目录加入 sys.path。
依赖方向严格 L4 -> L3 -> L2，不反向。
"""
import os
import sys

_COMP = os.path.dirname(os.path.abspath(__file__))          # .../bangcle-contract
_L4 = os.path.dirname(_COMP)                                 # .../components
_ROOT = os.path.abspath(os.path.join(_COMP, "..", "..", ".."))  # workspace root

_PATHS = {
    "l3_contract": os.path.join(_ROOT, "L3-business", "components", "contract-management"),
    "l2_aikb": os.path.join(_ROOT, "L2-infra", "components", "ai-knowledge-base"),
    "l4_product_kb": os.path.join(_L4, "product-kb"),
}

for _p in _PATHS.values():
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
