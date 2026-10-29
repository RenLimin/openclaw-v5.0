"""E2E 配置：sys.path 注入 + OA 会话 fixture（不可用则 skip，不伪造）。"""
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

from oa_session import OA_STATE, oa_session_available


@pytest.fixture
def oa_state_path():
    return OA_STATE


@pytest.fixture
def require_oa():
    if not oa_session_available():
        pytest.skip("OA storage_state 不可用（E2E 环境不满足，留证跳过，不伪造）")
    return OA_STATE
