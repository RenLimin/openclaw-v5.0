"""数据源注册表 — 注册所有数据源到 DataSourceRegistry

在模块导入时自动完成注册。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fin_l4.external.base import DataSourceRegistry
from fin_l4.external.rate_source import RateSource
from fin_l4.external.market_source import MarketSource
from fin_l4.external.fx_source import FxSource


def register_all() -> DataSourceRegistry:
    """注册所有已知数据源"""
    DataSourceRegistry.register(RateSource())
    DataSourceRegistry.register(MarketSource())
    DataSourceRegistry.register(FxSource())
    return DataSourceRegistry


# 导入即注册
register_all()


__all__ = ["register_all"]
