"""E2E 配置：sys.path 注入 + OA 会话可用性探测（不可用则 skip，不伪造）。"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_ROOT = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")
for p in (COMPONENT_ROOT, L3_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

OA_STATE = os.path.expanduser("~/.openclaw/data/clm-oa-recon/state.json")


def oa_session_available() -> bool:
    """探测 OA storage_state 是否可用（仅文件存在性 + 时效近似判断）。"""
    if not os.path.isfile(OA_STATE):
        return False
    import json
    try:
        state = json.load(open(OA_STATE, encoding="utf-8"))
    except Exception:
        return False
    cookies = state.get("cookies", [])
    return any("bangcle.com" in (c.get("domain") or "") for c in cookies)


@pytest.fixture
def oa_state_path():
    return OA_STATE
