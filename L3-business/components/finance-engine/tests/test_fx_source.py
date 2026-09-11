"""汇率数据源测试 — FxSource 占位实现"""

import pytest
from decimal import Decimal

from finance_engine.core.external.fx_source import FxSource, _PLACEHOLDER_RATES
from finance_engine.core.external.base import DataSourceRegistry, DataSnapshot


class TestFxSource:
    """汇率数据源"""

    def test_name(self):
        source = FxSource()
        assert source.name == "fx_placeholder"

    def test_data_type(self):
        source = FxSource()
        assert source.data_type == "fx"

    def test_ttl(self):
        source = FxSource()
        assert source.ttl_seconds == 43200

    def test_is_available(self):
        source = FxSource()
        assert source.is_available() is True

    def test_fetch_usd_to_cny(self):
        source = FxSource()
        result = source.fetch(from_currency="USD", to_currency="CNY")
        assert result.value == Decimal("7.20")
        assert result.is_estimate is True

    def test_fetch_eur_to_cny(self):
        source = FxSource()
        result = source.fetch(from_currency="EUR", to_currency="CNY")
        assert result.value == Decimal("7.80")

    def test_fetch_cny_to_usd(self):
        """人民币转美元"""
        source = FxSource()
        result = source.fetch(from_currency="CNY", to_currency="USD")
        expected = Decimal("1") / Decimal("7.20")
        assert abs(result.value - expected) < Decimal("0.01")

    def test_fetch_cross_rate(self):
        """交叉汇率: USD → EUR"""
        source = FxSource()
        result = source.fetch(from_currency="USD", to_currency="EUR")
        # USD->CNY = 7.20, EUR->CNY = 7.80
        # USD->EUR = 7.20 / 7.80
        expected = Decimal("7.20") / Decimal("7.80")
        assert abs(result.value - expected) < Decimal("0.01")

    def test_fetch_same_currency(self):
        """相同货币汇率 = 1"""
        source = FxSource()
        result = source.fetch(from_currency="USD", to_currency="USD")
        # from_rate / to_rate = 7.20 / 7.20 = 1
        assert result.value == Decimal("1.00") or abs(result.value - Decimal("1")) < Decimal("0.01")

    def test_fetch_metadata(self):
        source = FxSource()
        result = source.fetch(from_currency="USD", to_currency="CNY")
        assert result.metadata["placeholder"] is True
        assert result.metadata["from_currency"] == "USD"
        assert result.metadata["to_currency"] == "CNY"

    def test_fetch_unknown_currency(self):
        """未知货币使用默认汇率 1"""
        source = FxSource()
        result = source.fetch(from_currency="XYZ", to_currency="CNY")
        # XYZ 不在表中，默认 1；CNY = 1
        # rate = 1 / 1 = 1
        assert result.value == Decimal("1")


class TestDataSourceRegistry:
    """数据源注册表"""

    def test_register_and_get(self):
        source = FxSource()
        DataSourceRegistry.register(source)
        result = DataSourceRegistry.get("fx_placeholder")
        assert result is not None
        assert result.name == "fx_placeholder"

    def test_list_all(self):
        source = FxSource()
        DataSourceRegistry.register(source)
        sources = DataSourceRegistry.list_all()
        assert len(sources) >= 1

    def test_list_by_type(self):
        source = FxSource()
        DataSourceRegistry.register(source)
        fx_sources = DataSourceRegistry.list_by_type("fx")
        assert len(fx_sources) >= 1

    def test_get_nonexistent(self):
        result = DataSourceRegistry.get("nonexistent_source")
        assert result is None
