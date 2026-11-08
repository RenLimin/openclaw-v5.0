"""providers — Revenue Forecast Part B 外部数据源占位（Phase 4）。

v1.0 仅提供契约：
  - ForecastProvider: 外部动态数据源 ABC（未来 ONES 实时口径实现它）；
  - NotConfiguredProvider: 未配置占位，恒显 not_configured，fetch 抛 NotImplementedError。

设计依据：DESIGN-DETAIL-REVENUE-FORECAST-v1.0 §6。
"""

from .base import ForecastProvider, ProviderStatus
from .null_provider import NotConfiguredProvider

__all__ = [
    "ForecastProvider",
    "ProviderStatus",
    "NotConfiguredProvider",
]
