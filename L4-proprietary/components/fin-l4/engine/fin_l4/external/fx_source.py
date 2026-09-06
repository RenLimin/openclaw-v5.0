"""汇率数据源（预留，返回占位数据）

TODO: 接入真实汇率数据源（央行中间价 / 汇率 API / 银行牌价等）
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fin_l4.external.base import DataSource, DataSnapshot
from decimal import Decimal


# 占位汇率表（以 CNY 为基准的常见货币汇率参考值）
_PLACEHOLDER_RATES = {
    "USD": Decimal("7.20"),   # 美元
    "EUR": Decimal("7.80"),   # 欧元
    "JPY": Decimal("0.048"),  # 日元
    "HKD": Decimal("0.92"),   # 港币
    "GBP": Decimal("9.10"),   # 英镑
    "CNY": Decimal("1.00"),   # 人民币（基准）
}


class FxSource(DataSource):
    """汇率数据源（预留占位实现）"""

    @property
    def name(self) -> str:
        return "fx_placeholder"

    @property
    def data_type(self) -> str:
        return "fx"

    @property
    def ttl_seconds(self) -> int:
        return 43200  # 12h

    def fetch(self, **params) -> DataSnapshot:
        """
        获取汇率（占位实现）

        params:
            - from_currency: 源货币代码，默认 "USD"
            - to_currency: 目标货币代码，默认 "CNY"
        """
        from_ccy = params.get("from_currency", "USD").upper()
        to_ccy = params.get("to_currency", "CNY").upper()

        # 以 CNY 为中间货币计算交叉汇率
        from_rate = _PLACEHOLDER_RATES.get(from_ccy, Decimal("1"))
        to_rate = _PLACEHOLDER_RATES.get(to_ccy, Decimal("1"))

        if to_ccy == "CNY":
            rate = from_rate
        elif from_ccy == "CNY":
            rate = Decimal("1") / to_rate if to_rate != 0 else Decimal("0")
        else:
            rate = from_rate / to_rate if to_rate != 0 else Decimal("0")

        return DataSnapshot(
            source=self.name,
            data_type="fx",
            value=rate,
            currency=f"{from_ccy}/{to_ccy}",
            effective_date=None,
            metadata={
                "from_currency": from_ccy,
                "to_currency": to_ccy,
                "placeholder": True,
                "note": "汇率数据源尚未接入，返回静态参考值",
            },
            is_estimate=True,
        )

    def is_available(self) -> bool:
        # 占位实现始终可用
        return True
