"""行情数据源（预留，返回占位数据）

TODO: 接入真实行情数据源（新浪财经 / 东方财富 / Wind / Tushare 等）
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fin_l4.external.base import DataSource, DataSnapshot
from decimal import Decimal


class MarketSource(DataSource):
    """行情数据源（预留占位实现）"""

    @property
    def name(self) -> str:
        return "market_placeholder"

    @property
    def data_type(self) -> str:
        return "market"

    @property
    def ttl_seconds(self) -> int:
        return 3600  # 1h（行情数据更新快）

    def fetch(self, **params) -> DataSnapshot:
        """
        获取行情数据（占位实现）

        params:
            - symbol: 证券代码，如 "600000.SH"
            - asset_type: 资产类型 stock/fund/bond
        """
        symbol = params.get("symbol", "UNKNOWN")
        asset_type = params.get("asset_type", "stock")

        # 占位：返回 0.0 作为默认值
        return DataSnapshot(
            source=self.name,
            data_type="market",
            value=Decimal("0"),
            effective_date=None,
            metadata={
                "symbol": symbol,
                "asset_type": asset_type,
                "placeholder": True,
                "note": "行情数据源尚未接入，返回占位值",
            },
            is_estimate=True,
        )

    def is_available(self) -> bool:
        # 占位实现始终可用（但返回占位数据）
        return True
