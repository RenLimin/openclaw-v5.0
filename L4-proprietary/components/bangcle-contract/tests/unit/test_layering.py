"""P8 §9：层级依赖回归（锁定，防后续破坏）。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_DIR = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")

_FORBIDDEN_IN_L3 = ("bangcle-contract", "contract_review", "L4-proprietary")


def _iter_py(*dirs):
    for d in dirs:
        for root, _, files in os.walk(d):
            if "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(root, f)


def test_l3_does_not_reference_l4():
    """L3 contract-management 不得 import L4（依赖方向铁律）。"""
    hits = []
    for p in _iter_py(L3_DIR):
        text = open(p, encoding="utf-8", errors="ignore").read()
        for token in _FORBIDDEN_IN_L3:
            if re.search(r"(from|import)\s+.*%s" % re.escape(token), text):
                hits.append((p, token))
    assert hits == [], "L3 出现 L4 反向引用: %s" % hits


def test_l4_sibling_bdms_reuse_is_isolated_to_oa():
    """L4→同级 bdms 的复用只允许出现在 services/oa（DESIGN-OUTLINE 授权边界）。"""
    offenders = []
    for p in _iter_py(os.path.join(COMPONENT_ROOT, "contract_review"),
                      os.path.join(COMPONENT_ROOT, "repository"),
                      os.path.join(COMPONENT_ROOT, "cli")):
        text = open(p, encoding="utf-8", errors="ignore").read()
        if re.search(r"(from|import)\s+bdms", text):
            offenders.append(p)
    assert offenders == [], "bdms 复用越出 services/oa 边界: %s" % offenders
