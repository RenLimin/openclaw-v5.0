"""services.oa.cube_provider 单测（离线：假 client / monkeypatch，不连真实网络）。

契约：DESIGN-DETAIL-contract-ontology-bridge-v1.0 §2.2 / §4 P1。
"""
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

from contract_management.oa.base import OaProvider
from services.oa.cube import ContractData
from services.oa.cube_provider import (
    CubeOaProvider,
    UNKNOWN_PROCESS_ENVELOPE,
    build_cube_provider,
)


class FakeCubeClient:
    """假 CubeClient：只记录调用，不碰网络/文件。"""

    def __init__(self, *args, **kwargs):
        self.init_args = args
        self.init_kwargs = kwargs
        self.calls = []

    def get_contract(self, billid):
        self.calls.append(billid)
        return ContractData(billid=str(billid), main_fields={"合同编号": "FAKE-1"})


# ---------- ABC 契约 ----------

def test_is_oa_provider_subclass():
    assert issubclass(CubeOaProvider, OaProvider)


def test_cannot_instantiate_without_abstract_methods():
    # 仅实现部分抽象方法的类仍不可实例化
    class PartialProvider(OaProvider):
        def get_contract_attachment(self, process_instance_id):
            return None

    with pytest.raises(TypeError):
        PartialProvider()


# ---------- 委托 get_contract ----------

def test_get_contract_attachment_delegates():
    fake = FakeCubeClient()
    provider = CubeOaProvider(client=fake)
    data = provider.get_contract_attachment("15134")

    assert fake.calls == ["15134"]
    assert isinstance(data, ContractData)
    assert data.billid == "15134"
    assert data.main_fields == {"合同编号": "FAKE-1"}


def test_build_provider_with_monkeypatched_client(monkeypatch):
    # 工厂构造会 new CubeClient（不触发网络）；monkeypatch get_contract 验证委托
    import services.oa.cube_provider as cp_mod

    constructed = {}

    def fake_init(self, storage_state=None, **kwargs):
        constructed["storage_state"] = storage_state
        constructed["kwargs"] = kwargs

    def fake_get_contract(self, billid):
        return ContractData(billid=str(billid))

    monkeypatch.setattr(cp_mod.CubeClient, "__init__", fake_init)
    monkeypatch.setattr(cp_mod.CubeClient, "get_contract", fake_get_contract)

    provider = build_cube_provider(
        storage_state="fake-state.json", timeout=9.0, layoutid="535"
    )
    assert isinstance(provider, CubeOaProvider)
    assert constructed["storage_state"] == "fake-state.json"
    assert constructed["kwargs"] == {"timeout": 9.0, "layoutid": "535"}

    data = provider.get_contract_attachment("999")
    assert data.billid == "999"


# ---------- query_process 恒 unknown ----------

def test_query_process_unknown_envelope():
    fake = FakeCubeClient()
    provider = CubeOaProvider(client=fake)
    envelope = provider.query_process("15134")

    assert envelope == {
        "process_status": "unknown",
        "node": None,
        "confidence": 0.0,
        "source": "workflow-api-unavailable",
    }
    # 不产生任何 CubeClient 调用
    assert fake.calls == []
    # 返回副本，修改不污染常量
    envelope["node"] = "x"
    assert UNKNOWN_PROCESS_ENVELOPE["node"] is None


# ---------- 写方法冻结 ----------

def test_push_result_not_implemented():
    provider = CubeOaProvider(client=FakeCubeClient())
    with pytest.raises(NotImplementedError):
        provider.push_result("15134", "approve", "同意", "rex")


def test_register_callback_not_implemented():
    provider = CubeOaProvider(client=FakeCubeClient())
    with pytest.raises(NotImplementedError):
        provider.register_callback(lambda *a, **k: None)
