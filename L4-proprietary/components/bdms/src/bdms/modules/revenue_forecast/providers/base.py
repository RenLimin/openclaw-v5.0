"""base — Part B 外部动态数据源抽象契约（DESIGN-DETAIL §6）。

未来 Part B 提供真正实时的动态口径（替代 1.71 静态快照）；
v1.0 不建调用链、不引依赖，仅定义 ABC + 状态结构。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# ProviderStatus.status 取值
STATUS_READY = "ready"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_ERROR = "error"
STATUS_VALUES = (STATUS_READY, STATUS_NOT_CONFIGURED, STATUS_ERROR)


@dataclass(frozen=True)
class ProviderStatus:
    """外部数据源状态（provider-status 端点序列化它）。"""

    name: str           # 提供商标识，如 "ones"
    status: str         # ready | not_configured | error
    message: str = ""   # 人类可读说明

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "message": self.message}


class ForecastProvider(ABC):
    """外部动态数据源抽象基类。

    未来实现（如 OnesProvider）：
      - get_status 依据凭据/连通性返回 ready|error；
      - fetch 按 obligation_ids 拉取该年实时动态数据，
        返回 {obligation_id: {动态字段...}}。
    """

    name: str = "base"

    @abstractmethod
    def get_status(self) -> ProviderStatus:
        """返回当前提供商标态。"""

    @abstractmethod
    def fetch(self, obligation_ids: list[str], year: int) -> dict:
        """拉取实时动态数据。未接入时必须抛 NotImplementedError。"""
