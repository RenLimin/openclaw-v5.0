"""FIN-005 投资组合引擎测试 — 持仓管理、收益计算、资产配置、再平衡"""

import pytest
from decimal import Decimal

from fin005_portfolio import (
    PortfolioEngine, AssetType, RiskLevel,
    ASSET_RISK_MAP, REBALANCE_DRIFT_THRESHOLD,
)


@pytest.fixture
def engine():
    return PortfolioEngine()


@pytest.fixture
def sample_portfolio(engine):
    portfolio = engine.create_portfolio("测试组合", "CNY")
    engine.add_holding(
        portfolio.id, AssetType.STOCK, "腾讯", "0700.HK",
        Decimal("100"), Decimal("300"), Decimal("350"),
    )
    engine.add_holding(
        portfolio.id, AssetType.BOND, "国债", "GB001",
        Decimal("1000"), Decimal("100"), Decimal("102"),
    )
    engine.add_holding(
        portfolio.id, AssetType.CASH, "银行存款", "CASH",
        Decimal("50000"), Decimal("1"), Decimal("1"),
    )
    return portfolio


class TestPortfolioCreation:
    """组合创建"""

    def test_create_portfolio(self, engine):
        p = engine.create_portfolio("我的组合")
        assert p.name == "我的组合"
        assert p.base_currency == "CNY"
        assert p.id.startswith("PFO-")

    def test_create_portfolio_custom_currency(self, engine):
        p = engine.create_portfolio("美元组合", "USD")
        assert p.base_currency == "USD"


class TestHoldingManagement:
    """持仓管理"""

    def test_add_holding(self, engine, sample_portfolio):
        holdings = engine.get_holdings(sample_portfolio.id)
        assert len(holdings) == 3

    def test_add_holding_invalid_portfolio(self, engine):
        with pytest.raises(ValueError, match="组合不存在"):
            engine.add_holding(
                "NONEXIST", AssetType.STOCK, "测试", "T",
                Decimal("100"), Decimal("10"),
            )

    def test_update_price(self, engine, sample_portfolio):
        result = engine.update_price(sample_portfolio.id, "0700.HK", Decimal("400"))
        assert result.current_price == Decimal("400")

    def test_update_price_nonexistent(self, engine, sample_portfolio):
        with pytest.raises(ValueError, match="持仓不存在"):
            engine.update_price(sample_portfolio.id, "NONEXIST", Decimal("100"))

    def test_remove_holding(self, engine, sample_portfolio):
        engine.remove_holding(sample_portfolio.id, "CASH")
        holdings = engine.get_holdings(sample_portfolio.id)
        assert len(holdings) == 2


class TestHoldingProperties:
    """持仓属性计算"""

    def test_market_value(self, engine, sample_portfolio):
        holdings = engine.get_holdings(sample_portfolio.id)
        stock = [h for h in holdings if h.asset_code == "0700.HK"][0]
        assert stock.market_value == Decimal("35000.00")

    def test_cost_basis(self, engine, sample_portfolio):
        holdings = engine.get_holdings(sample_portfolio.id)
        stock = [h for h in holdings if h.asset_code == "0700.HK"][0]
        assert stock.cost_basis == Decimal("30000.00")

    def test_gain(self, engine, sample_portfolio):
        holdings = engine.get_holdings(sample_portfolio.id)
        stock = [h for h in holdings if h.asset_code == "0700.HK"][0]
        assert stock.gain == Decimal("5000.00")

    def test_return_pct(self, engine, sample_portfolio):
        holdings = engine.get_holdings(sample_portfolio.id)
        stock = [h for h in holdings if h.asset_code == "0700.HK"][0]
        assert stock.return_pct == Decimal("16.67")


class TestPortfolioSummary:
    """组合摘要"""

    def test_summary(self, engine, sample_portfolio):
        summary = engine.get_portfolio_summary(sample_portfolio.id)
        assert summary.total_value > 0
        assert summary.total_cost > 0
        assert len(summary.holdings) == 3

    def test_summary_empty_portfolio(self, engine):
        p = engine.create_portfolio("空组合")
        summary = engine.get_portfolio_summary(p.id)
        assert summary.total_value == Decimal("0")
        assert summary.total_return_pct == Decimal("0")


class TestAssetAllocation:
    """资产配置"""

    def test_allocation(self, engine, sample_portfolio):
        alloc = engine.get_asset_allocation(sample_portfolio.id)
        assert len(alloc.by_asset_type) > 0

    def test_allocation_empty(self, engine):
        p = engine.create_portfolio("空组合")
        alloc = engine.get_asset_allocation(p.id)
        assert len(alloc.by_asset_type) == 0

    def test_concentration_risk(self, engine):
        """集中度风险检测"""
        p = engine.create_portfolio("集中组合")
        # 添加一个占比很大的持仓
        engine.add_holding(
            p.id, AssetType.STOCK, "重仓股", "STOCK1",
            Decimal("10000"), Decimal("100"), Decimal("100"),
        )
        # 添加一个小持仓
        engine.add_holding(
            p.id, AssetType.CASH, "现金", "CASH",
            Decimal("100"), Decimal("1"), Decimal("1"),
        )
        alloc = engine.get_asset_allocation(p.id)
        # 重仓股占比 > 5%，应被标记为集中度风险
        assert len(alloc.concentration_risk) > 0


class TestRebalancing:
    """再平衡建议"""

    def test_suggest_rebalancing(self, engine, sample_portfolio):
        target = {
            AssetType.STOCK: Decimal("40"),
            AssetType.BOND: Decimal("30"),
            AssetType.FUND: Decimal("20"),
            AssetType.CASH: Decimal("10"),
        }
        suggestions = engine.suggest_rebalancing(sample_portfolio.id, target)
        assert isinstance(suggestions, list)

    def test_rebalancing_empty_portfolio(self, engine):
        p = engine.create_portfolio("空组合")
        target = {AssetType.STOCK: Decimal("50"), AssetType.BOND: Decimal("50")}
        suggestions = engine.suggest_rebalancing(p.id, target)
        assert suggestions == []


class TestAssetRiskMap:
    """资产风险映射"""

    def test_cash_is_low_risk(self):
        assert ASSET_RISK_MAP[AssetType.CASH] == RiskLevel.LOW

    def test_stock_is_high_risk(self):
        assert ASSET_RISK_MAP[AssetType.STOCK] == RiskLevel.HIGH

    def test_bond_is_low_mid_risk(self):
        assert ASSET_RISK_MAP[AssetType.BOND] == RiskLevel.LOW_MID
