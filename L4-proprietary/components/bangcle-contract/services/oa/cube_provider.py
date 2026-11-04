"""services.oa.cube_provider — 把既有 CubeClient 适配为 L3 OaProvider（P1 只读桥）。

契约（DESIGN-DETAIL-contract-ontology-bridge-v1.0 §2.2）：
- get_contract_attachment(pid) 委托 CubeClient.get_contract(pid)（返回 ContractData）
- query_process(pid) 恒返 unknown 信封（泛微 workflow 审批流未接入，绝不发请求/伪造）
- push_result / register_callback 显式 NotImplementedError（P4 前冻结）
- 不修改 CubeClient；组合复用
- L3 OaProvider 通过 sys.path 注入导入（与 contract_review/risk.py 同一方式）
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from .cube import CubeClient, ContractData


# ---------------------------------------------------------------
# L3 路径注入（与 contract_review/risk.py 一致）
# ---------------------------------------------------------------

def _default_l3_component_root() -> str:
    # 本文件：<repo>/L4-proprietary/components/bangcle-contract/services/oa/cube_provider.py
    here = os.path.dirname(os.path.abspath(__file__))
    component_root = os.path.dirname(os.path.dirname(here))  # bangcle-contract/
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(component_root))
    )
    return os.path.join(repo_root, "L3-business", "components", "contract-management")


def _load_oa_provider():
    """注入 L3 组件根到 sys.path 并返回 OaProvider ABC。"""
    root = _default_l3_component_root()
    if not os.path.isdir(root):
        raise RuntimeError(f"L3 contract-management 组件不存在: {root}")

    import sys

    if root not in sys.path:
        sys.path.insert(0, root)

    from contract_management.oa.base import OaProvider

    return OaProvider


_OaProvider = _load_oa_provider()

# query_process 的固定 unknown 信封（DETAIL §2.2）
UNKNOWN_PROCESS_ENVELOPE = {
    "process_status": "unknown",
    "node": None,
    "confidence": 0.0,
    "source": "workflow-api-unavailable",
}


class CubeOaProvider(_OaProvider):
    """CubeClient → L3 OaProvider 只读适配器（P1）。"""

    def __init__(
        self,
        storage_state: Optional[os.PathLike] = None,
        *,
        client: Optional[CubeClient] = None,
        **kwargs: Any,
    ) -> None:
        """可注入现成 client（测试用），否则按 storage_state/kwargs 构造 CubeClient。"""
        self._client = client if client is not None else CubeClient(
            storage_state=storage_state, **kwargs
        )

    @property
    def client(self) -> CubeClient:
        return self._client

    def get_contract_attachment(self, process_instance_id: str) -> ContractData:
        """委托 CubeClient.get_contract，返回其 ContractData。"""
        return self._client.get_contract(process_instance_id)

    def query_process(self, process_instance_id: str) -> dict:
        """泛微 workflow 审批流未接入：恒返 unknown 信封，不发任何请求。"""
        return dict(UNKNOWN_PROCESS_ENVELOPE)

    def push_result(
        self,
        process_instance_id: str,
        action: str,
        comment: str,
        approver: str,
    ) -> bool:
        """审批结果写回冻结至 P4。"""
        raise NotImplementedError("push_result 在 P4（真写回）前冻结")

    def register_callback(self, handler: Callable[..., Any]) -> None:
        """OA 事件回调冻结至 P4。"""
        raise NotImplementedError("register_callback 在 P4（回调）前冻结")


def build_cube_provider(
    storage_state: Optional[os.PathLike] = None, **kwargs: Any
) -> CubeOaProvider:
    """工厂：按 storage_state 与 CubeClient 构造参数创建只读 provider。"""
    return CubeOaProvider(storage_state=storage_state, **kwargs)
