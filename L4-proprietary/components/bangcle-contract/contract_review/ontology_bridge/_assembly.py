"""_assembly — L3 装配脚本的绝对路径加载（避免 scripts 包名冲突）。

L4 bangcle-contract 与 L3 contract-management 各有一个 `scripts/` 目录，
两者都进 sys.path 时 `import scripts.register_ontology_functions` 的包名
解析不确定（namespace vs regular package）。这里用 importlib 按 L3 脚本
绝对路径加载，显式命名模块，杜绝歧义。

用法：
    from contract_review.ontology_bridge._assembly import l3_register_all
    summary = l3_register_all(ai_kb_path)
"""
from __future__ import annotations

import importlib.util
import os
import sys
from typing import Optional

_L3_SCRIPT = os.path.join(
    "scripts", "register_ontology_functions.py",
)


def _l3_component_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))          # .../ontology_bridge
    comp = os.path.dirname(os.path.dirname(here))              # .../bangcle-contract
    l4_components = os.path.dirname(comp)                      # .../components
    root = os.path.abspath(os.path.join(l4_components, "..", ".."))
    return os.path.join(root, "L3-business", "components", "contract-management")


def _load_l3_module():
    """加载 L3 register_ontology_functions 模块（按绝对路径，显式命名）。"""
    l3_root = _l3_component_root()
    script_path = os.path.join(l3_root, _L3_SCRIPT)
    if not os.path.isfile(script_path):
        raise RuntimeError(f"L3 装配脚本不存在: {script_path}")
    # 脚本内部需要 L2 ai-kb 与自身组件根在 sys.path（脚本内已自插，这里兜底）
    for p in (l3_root,):
        if p not in sys.path:
            sys.path.insert(0, p)
    mod_name = "_l3_register_ontology_functions"
    spec = importlib.util.spec_from_file_location(mod_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 L3 装配脚本: {script_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def l3_register_all(ai_kb_path: str) -> dict:
    """调用 L3 register_all（domain + functions + actions，幂等）。

    返回与 L3 脚本一致的 summary dict。
    """
    mod = _load_l3_module()
    return mod.register_all(ai_kb_path)
