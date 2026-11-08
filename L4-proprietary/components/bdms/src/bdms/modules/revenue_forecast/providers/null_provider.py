"""null_provider — 未配置数据源占位（DESIGN-DETAIL §6）。

v1.0 Part B 恒显 not_configured；任何对 fetch 的调用 fail-closed 抛 NotImplementedError。
"""

from __future__ import annotations

from .base import ForecastProvider, ProviderStatus, STATUS_NOT_CONFIGURED

_DEFAULT_MESSAGE = "Part B（ONES 实时动态）待接入，当前为财报静态快照口径"


class NotConfiguredProvider(ForecastProvider):
    """未配置占位 Provider。"""

    name = "ones"

    def __init__(self, message: str = _DEFAULT_MESSAGE):
        self._message = message

    def get_status(self) -> ProviderStatus:
        return ProviderStatus(self.name, STATUS_NOT_CONFIGURED, self._message)

    def fetch(self, obligation_ids: list[str], year: int) -> dict:
        raise NotImplementedError(
            f"Provider {self.name!r} 未配置，Part B 实时动态口径暂不可用"
        )
