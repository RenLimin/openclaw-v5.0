"""Smoke test: 验证组件目录结构和 Python 文件存在"""
import sys
from pathlib import Path

COMP_DIR = Path(__file__).resolve().parent.parent


def test_component_dir_exists():
    assert COMP_DIR.is_dir(), f"{COMP_DIR} 不存在"


def test_has_python_files():
    py_files = [p for p in COMP_DIR.rglob("*.py") if "__pycache__" not in str(p)]
    assert len(py_files) > 0, f"{COMP_DIR} 没有 Python 文件"
