"""
pytest 配置与公共 fixture。
"""

from __future__ import annotations

import os
import sys
import tempfile
import pytest

# 确保 bangcle_ppt 包可被导入
_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.dirname(_HERE)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)


@pytest.fixture
def tmp_output_dir():
    """临时输出目录（自动清理）。"""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_engine():
    """一个注册了所有 renderer 的引擎实例。"""
    from bangcle_ppt.engine import TemplateEngine
    from bangcle_ppt.renderers import REGISTRY

    engine = TemplateEngine(theme="light")
    engine.register_renderers(REGISTRY)
    return engine
