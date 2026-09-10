#!/usr/bin/env python3
"""向后兼容 wrapper — kb_index 已迁移到 knowledge-base 组件。

本文件保留以避免破坏现有引用（如 system_full_audit.py、文档中的命令等）。
新代码请直接使用：
    L2-infra/components/knowledge-base/kb_index.py

或者使用通用知识库组件：
    from knowledge_base import KnowledgeBase

2026-09-10 迁移（task-20260910-kb-extraction）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 重定向到 knowledge-base 组件的实际实现
_KB_INDEX = Path(__file__).resolve().parent.parent / "knowledge-base" / "kb_index.py"

if __name__ == "__main__":
    # 作为脚本运行时，转发所有参数
    import subprocess
    sys.exit(subprocess.call([sys.executable, str(_KB_INDEX)] + sys.argv[1:]))
else:
    # 作为模块导入时，重导出所有符号
    import importlib.util
    _spec = importlib.util.spec_from_file_location("kb_index_actual", _KB_INDEX)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules["kb_index_actual"] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore

    # 把所有公共名称复制到本模块命名空间
    for _name in dir(_mod):
        if not _name.startswith("_"):
            globals()[_name] = getattr(_mod, _name)
