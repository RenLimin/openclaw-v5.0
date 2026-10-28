"""OA Cube E2E：有真实会话时跑，无会话时 skip（绝不伪造数据）。"""
import os
import sys

import pytest

from conftest import oa_session_available, OA_STATE

pytestmark = pytest.mark.skipif(
    not oa_session_available(),
    reason="OA storage_state 不可用，跳过 OA E2E（不伪造数据）",
)


def test_oa_session_still_valid():
    """TC-OA-01：会话可用性验证（不直接连 OA，仅文件结构确认）。"""
    import json
    state = json.load(open(OA_STATE, encoding="utf-8"))
    assert "cookies" in state or "origins" in state
    assert isinstance(state.get("cookies", []), list)


def test_cube_client_init():
    """TC-OA-02：CubeClient 可构造，storage_state 加载不抛错。"""
    from services.oa.cube import CubeClient
    client = CubeClient(storage_state=OA_STATE)
    assert client is not None
    assert hasattr(client, "get_contract")
    assert hasattr(client, "download_attachment")
    # storage_state 路径已记录（构造不抛错 = 可初始化）
    assert client.storage_state_path is not None


def test_get_contract_empty_billid_rejected():
    """空 billid 在 helpers 层直接拒绝（不发真实请求，纯函数校验）。"""
    from services.oa import helpers as H
    with pytest.raises(H.HelperError):
        H._require_billid("")
    # None 也拒绝
    with pytest.raises(H.HelperError):
        H._require_billid(None)
