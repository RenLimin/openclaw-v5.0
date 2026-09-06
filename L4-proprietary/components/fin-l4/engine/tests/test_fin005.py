"""
FIN-005 投资持仓核算测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from fin005_portfolio import PortfolioEngine, AssetType, RiskLevel


def test_create_portfolio():
    """测试创建组合"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("Rex 家庭组合", "CNY")
    assert p.id.startswith("PFO-")
    assert p.name == "Rex 家庭组合"
    assert p.base_currency == "CNY"
    print(f"✅ test_create_portfolio passed (id={p.id})")


def test_add_holding():
    """测试添加持仓"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")

    h = engine.add_holding(
        p.id, AssetType.STOCK, "贵州茅台", "600519",
        shares=100, cost_basis_price=1500, current_price=1600,
    )
    assert h.asset_name == "贵州茅台"
    assert h.market_value == Decimal("160000.00")
    assert h.cost_basis == Decimal("150000.00")
    assert h.gain == Decimal("10000.00")
    assert h.return_pct == Decimal("6.67")
    print(f"✅ test_add_holding passed (市值={h.market_value}, 盈亏={h.gain})")


def test_update_price():
    """测试更新价格"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")
    engine.add_holding(p.id, AssetType.FUND, "易方达蓝筹", "005827",
                       shares=5000, cost_basis_price=2.0, current_price=2.0)

    updated = engine.update_price(p.id, "005827", 2.5)
    assert updated.current_price == Decimal("2.50")
    assert updated.gain == Decimal("2500.00")
    print(f"✅ test_update_price passed (新价格={updated.current_price}, 盈亏={updated.gain})")


def test_portfolio_summary():
    """测试组合摘要"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("Rex 家庭组合")

    engine.add_holding(p.id, AssetType.STOCK, "贵州茅台", "600519",
                       shares=100, cost_basis_price=1500, current_price=1600)
    engine.add_holding(p.id, AssetType.FUND, "易方达蓝筹", "005827",
                       shares=10000, cost_basis_price=2.0, current_price=2.5)
    engine.add_holding(p.id, AssetType.CASH, "银行存款", "CASH",
                       shares=1, cost_basis_price=200000, current_price=200000)

    summary = engine.get_portfolio_summary(p.id)
    # 茅台 160000 + 蓝筹 25000 + 存款 200000 = 385000
    assert summary.total_value == Decimal("385000.00")
    assert summary.total_cost == Decimal("370000.00")
    assert summary.total_gain == Decimal("15000.00")
    assert len(summary.holdings) == 3
    print(f"✅ test_portfolio_summary passed (总值={summary.total_value}, 收益={summary.total_gain})")


def test_asset_allocation():
    """测试资产配置"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")

    engine.add_holding(p.id, AssetType.STOCK, "茅台", "600519",
                       shares=100, cost_basis_price=1500, current_price=1600)
    engine.add_holding(p.id, AssetType.BOND, "国债", "T-BOND",
                       shares=1000, cost_basis_price=100, current_price=102)
    engine.add_holding(p.id, AssetType.CASH, "存款", "CASH",
                       shares=1, cost_basis_price=50000, current_price=50000)

    alloc = engine.get_asset_allocation(p.id)
    assert len(alloc.by_asset_type) == 3
    assert len(alloc.by_risk_level) >= 2

    # 股票占比最高
    assert alloc.by_asset_type[0].category == "stock"
    print(f"✅ test_asset_allocation passed ({len(alloc.by_asset_type)} 类资产)")


def test_concentration_risk():
    """测试集中度风险"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")

    # 单一资产占比 > 50%
    engine.add_holding(p.id, AssetType.STOCK, "茅台", "600519",
                       shares=1000, cost_basis_price=1500, current_price=1600)
    engine.add_holding(p.id, AssetType.CASH, "存款", "CASH",
                       shares=1, cost_basis_price=100000, current_price=100000)

    alloc = engine.get_asset_allocation(p.id)
    # 茅台占比 > 50%，应被标记为集中度风险
    assert "茅台" in alloc.concentration_risk
    print(f"✅ test_concentration_risk passed (集中度: {alloc.concentration_risk})")


def test_calculate_return():
    """测试收益计算"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")

    engine.add_holding(p.id, AssetType.STOCK, "茅台", "600519",
                       shares=100, cost_basis_price=1500, current_price=1800)
    engine.add_holding(p.id, AssetType.FUND, "蓝筹", "005827",
                       shares=5000, cost_basis_price=2.0, current_price=1.8)

    result = engine.calculate_return(p.id, "1y", 365)
    # 茅台 +30000，蓝筹 -1000，总收益 +29000
    assert result.total_return == Decimal("29000.00")
    assert len(result.holding_returns) == 2
    print(f"✅ test_calculate_return passed (总收益={result.total_return})")


def test_rebalancing_suggestion():
    """测试再平衡建议"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")

    # 当前：股票 80%，现金 20%
    engine.add_holding(p.id, AssetType.STOCK, "茅台", "600519",
                       shares=800, cost_basis_price=1500, current_price=1600)
    engine.add_holding(p.id, AssetType.CASH, "存款", "CASH",
                       shares=1, cost_basis_price=320000, current_price=320000)

    # 目标：股票 60%，债券 30%，现金 10%
    target = {
        AssetType.STOCK: Decimal("60"),
        AssetType.BOND: Decimal("30"),
        AssetType.CASH: Decimal("10"),
    }

    suggestions = engine.suggest_rebalancing(p.id, target)
    assert len(suggestions) > 0

    # 股票应卖出
    stock_sugg = [s for s in suggestions if s["asset_type"] == "stock"]
    if stock_sugg:
        assert stock_sugg[0]["action"] == "sell"

    print(f"✅ test_rebalancing_suggestion passed ({len(suggestions)} 条建议)")


def test_remove_holding():
    """测试移除持仓"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")
    engine.add_holding(p.id, AssetType.STOCK, "茅台", "600519",
                       shares=100, cost_basis_price=1500, current_price=1600)
    engine.add_holding(p.id, AssetType.CASH, "存款", "CASH",
                       shares=1, cost_basis_price=50000, current_price=50000)

    engine.remove_holding(p.id, "600519")
    holdings = engine.get_holdings(p.id)
    assert len(holdings) == 1
    assert holdings[0].asset_code == "CASH"
    print("✅ test_remove_holding passed")


def test_annualized_return():
    """测试年化收益率"""
    engine = PortfolioEngine()
    p = engine.create_portfolio("测试组合")

    engine.add_holding(p.id, AssetType.STOCK, "茅台", "600519",
                       shares=100, cost_basis_price=1000, current_price=1200)

    # 持有 180 天，收益 20%，年化约 44%
    result = engine.calculate_return(p.id, "6m", 180)
    assert result.annualized_return_pct > result.total_return_pct
    print(f"✅ test_annualized_return passed (总收益={result.total_return_pct}%, 年化={result.annualized_return_pct}%)")


if __name__ == "__main__":
    test_create_portfolio()
    test_add_holding()
    test_update_price()
    test_portfolio_summary()
    test_asset_allocation()
    test_concentration_risk()
    test_calculate_return()
    test_rebalancing_suggestion()
    test_remove_holding()
    test_annualized_return()
    print("\n🎉 FIN-005 全部测试通过!")
