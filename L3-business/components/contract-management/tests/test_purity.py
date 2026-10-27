"""AC-2/AC-3 纯净性：AST 静态扫描禁止副作用模块与 L4 依赖。"""
import ast
import os

import pytest

COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(COMPONENT_ROOT, "contract_management")

# 禁止在 L3 出现的副作用/环境耦合模块
FORBIDDEN_TOP_LEVEL = {
    "os", "sys", "subprocess", "socket", "urllib", "urllib.request",
    "sqlite3", "http", "http.client", "requests", "httpx", "shutil",
    "pathlib", "tempfile", "pickle",
}
# oa/base.py 的白名单（只允许抽象层相关）
OA_BASE_ALLOWED = {"abc", "typing"}

# 禁止出现的 L4 / 专有耦合标记
# 仅扫描专有耦合标记；"L4" 是架构层级名（可出现在说明性注释），
# 真正的 L4 import 由 test_no_forbidden_modules 的 AST 检测负责。
FORBIDDEN_TOKENS = ["bangcle", "product_kb", "office-contract", "uf_xsht"]


def _iter_py_files():
    for root, _dirs, files in os.walk(PKG_DIR):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


def _imported_roots(path):
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    roots = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # 绝对导入
                roots.append(node.module.split(".")[0])
    return roots


def test_no_forbidden_modules():
    violations = []
    for path in _iter_py_files():
        rel = os.path.relpath(path, PKG_DIR)
        for root in _imported_roots(path):
            if root in FORBIDDEN_TOP_LEVEL:
                violations.append(f"{rel}: import {root}")
    assert violations == [], "L3 出现副作用模块: %s" % violations


def test_oa_base_only_abc_typing():
    base = os.path.join(PKG_DIR, "oa", "base.py")
    roots = set(_imported_roots(base))
    extra = roots - OA_BASE_ALLOWED
    assert extra == set(), "oa/base.py 只能 import abc/typing，发现: %s" % extra


def test_no_l4_or_proprietary_coupling():
    violations = []
    for path in _iter_py_files():
        rel = os.path.relpath(path, PKG_DIR)
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        for tok in FORBIDDEN_TOKENS:
            if tok in src:
                violations.append(f"{rel}: token {tok!r}")
    assert violations == [], "L3 出现 L4/专有耦合: %s" % violations
