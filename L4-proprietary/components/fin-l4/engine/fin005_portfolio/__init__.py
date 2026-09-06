"""
FIN-005 投资持仓核算引擎

功能:
- 投资组合管理（创建/持仓/调仓）
- 收益计算（浮动盈亏/收益率/年化）
- 资产配置分析（按类型/风险等级/集中度）
- 再平衡建议（日历触发/漂移触发）
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional, Dict
from datetime import date, datetime
import uuid


# ========== 工具函数 ==========

def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ========== 枚举 ==========

class AssetType(Enum):
    CASH = "cash"
    STOCK = "stock"
    FUND = "fund"
    BOND = "bond"
    REAL_ESTATE = "real_estate"
    INSURANCE_CV = "insurance_cv"
    OTHER = "other"


class RiskLevel(Enum):
    LOW = "low"
    LOW_MID = "low_mid"
    MID = "mid"
    MID_HIGH = "mid_high"
    HIGH = "high"


# 资产类型 → 风险等级映射
ASSET_RISK_MAP: Dict[AssetType, RiskLevel] = {
    AssetType.CASH: RiskLevel.LOW,
    AssetType.BOND: RiskLevel.LOW_MID,
    AssetType.FUND: RiskLevel.MID_HIGH,
    AssetType.STOCK: RiskLevel.HIGH,
    AssetType.REAL_ESTATE: RiskLevel.MID,
    AssetType.INSURANCE_CV: RiskLevel.LOW,
    AssetType.OTHER: RiskLevel.MID,
}

# 资产类型 → 流动性映射
ASSET_LIQUIDITY: Dict[AssetType, str] = {
    AssetType.CASH: "high",
    AssetType.STOCK: "high",
    AssetType.FUND: "high",
    AssetType.BOND: "mid",
    AssetType.REAL_ESTATE: "low",
    AssetType.INSURANCE_CV: "low",
    AssetType.OTHER: "varies",
}

# 再平衡漂移阈值
REBALANCE_DRIFT_THRESHOLD = Decimal("5.0")  # 5 个百分点


# ========== 数据模型 ==========

@dataclass
class Holding:
    """持仓"""
    id: str
    portfolio_id: str
    asset_type: AssetType
    asset_name: str
    asset_code: str
    shares: Decimal
    avg_cost: Decimal
    current_price: Decimal
    updated_at: datetime
    metadata: dict = field(default_factory=dict)

    @property
    def market_value(self) -> Decimal:
        return (self.shares * self.current_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def cost_basis(self) -> Decimal:
        return (self.shares * self.avg_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def gain(self) -> Decimal:
        return (self.market_value - self.cost_basis).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def return_pct(self) -> Decimal:
        if self.avg_cost == 0:
            return Decimal("0")
        return ((self.current_price - self.avg_cost) / self.avg_cost * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def risk_level(self) -> RiskLevel:
        return ASSET_RISK_MAP.get(self.asset_type, RiskLevel.MID)


@dataclass
class Portfolio:
    """投资组合"""
    id: str
    name: str
    base_currency: str
    created_at: date
    metadata: dict = field(default_factory=dict)


@dataclass
class HoldingSummary:
    """持仓摘要"""
    asset_name: str
    asset_code: str
    asset_type: AssetType
    shares: Decimal
    avg_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    gain: Decimal
    return_pct: Decimal
    weight_pct: Decimal  # 占组合比例


@dataclass
class PortfolioSummary:
    """组合摘要"""
    portfolio_id: str
    name: str
    total_value: Decimal
    total_cost: Decimal
    total_gain: Decimal
    total_return_pct: Decimal
    holdings: List[HoldingSummary]
    generated_at: datetime


@dataclass
class AllocationItem:
    """配置项"""
    category: str
    value: Decimal
    weight_pct: Decimal


@dataclass
class AllocationResult:
    """资产配置结果"""
    portfolio_id: str
    by_asset_type: List[AllocationItem]
    by_risk_level: List[AllocationItem]
    concentration_risk: Dict[str, Decimal]  # 集中度（单一资产占比）
    rebalancing_suggestion: Optional[List[Dict]]


@dataclass
class ReturnResult:
    """收益结果"""
    portfolio_id: str
    period: str
    total_return: Decimal
    total_return_pct: Decimal
    annualized_return_pct: Decimal
    holding_returns: List[Dict]


# ========== 引擎 ==========

class PortfolioEngine:
    """投资持仓核算引擎"""

    def __init__(self):
        self._portfolios: Dict[str, Portfolio] = {}
        self._holdings: Dict[str, List[Holding]] = {}  # portfolio_id → holdings

    # ---------- 组合管理 ----------

    def create_portfolio(self, name: str, base_currency: str = "CNY",
                         metadata: Optional[dict] = None) -> Portfolio:
        portfolio_id = f"PFO-{uuid.uuid4().hex[:8].upper()}"
        portfolio = Portfolio(
            id=portfolio_id,
            name=name,
            base_currency=base_currency,
            created_at=date.today(),
            metadata=metadata or {},
        )
        self._portfolios[portfolio_id] = portfolio
        self._holdings[portfolio_id] = []
        return portfolio

    def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        return self._portfolios.get(portfolio_id)

    def get_all_portfolios(self) -> List[Portfolio]:
        return list(self._portfolios.values())

    # ---------- 持仓管理 ----------

    def add_holding(
        self,
        portfolio_id: str,
        asset_type: AssetType,
        asset_name: str,
        asset_code: str,
        shares,
        cost_basis_price,
        current_price: Optional[Decimal] = None,
        metadata: Optional[dict] = None,
    ) -> Holding:
        """添加持仓"""
        if portfolio_id not in self._portfolios:
            raise ValueError(f"组合不存在: {portfolio_id}")

        holding = Holding(
            id=f"HLD-{uuid.uuid4().hex[:8].upper()}",
            portfolio_id=portfolio_id,
            asset_type=asset_type,
            asset_name=asset_name,
            asset_code=asset_code,
            shares=_to_decimal(shares),
            avg_cost=_to_decimal(cost_basis_price),
            current_price=_to_decimal(current_price) if current_price else _to_decimal(cost_basis_price),
            updated_at=datetime.now(),
            metadata=metadata or {},
        )
        self._holdings[portfolio_id].append(holding)
        return holding

    def update_price(self, portfolio_id: str, asset_code: str, new_price) -> Holding:
        """更新持仓价格"""
        if portfolio_id not in self._portfolios:
            raise ValueError(f"组合不存在: {portfolio_id}")

        for h in self._holdings[portfolio_id]:
            if h.asset_code == asset_code:
                h.current_price = _to_decimal(new_price)
                h.updated_at = datetime.now()
                return h

        raise ValueError(f"持仓不存在: {asset_code}")

    def remove_holding(self, portfolio_id: str, asset_code: str):
        """移除持仓"""
        if portfolio_id not in self._portfolios:
            raise ValueError(f"组合不存在: {portfolio_id}")
        self._holdings[portfolio_id] = [
            h for h in self._holdings[portfolio_id] if h.asset_code != asset_code
        ]

    def get_holdings(self, portfolio_id: str) -> List[Holding]:
        return self._holdings.get(portfolio_id, [])

    # ---------- 组合摘要 ----------

    def get_portfolio_summary(self, portfolio_id: str) -> PortfolioSummary:
        """获取组合摘要"""
        portfolio = self._portfolios.get(portfolio_id)
        if not portfolio:
            raise ValueError(f"组合不存在: {portfolio_id}")

        holdings = self._holdings.get(portfolio_id, [])
        total_value = sum(h.market_value for h in holdings)
        total_cost = sum(h.cost_basis for h in holdings)
        total_gain = total_value - total_cost

        if total_cost > 0:
            total_return_pct = (total_gain / total_cost * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            total_return_pct = Decimal("0")

        holding_summaries = []
        for h in holdings:
            weight = (h.market_value / total_value * Decimal("100")) if total_value > 0 else Decimal("0")
            holding_summaries.append(HoldingSummary(
                asset_name=h.asset_name,
                asset_code=h.asset_code,
                asset_type=h.asset_type,
                shares=h.shares,
                avg_cost=h.avg_cost,
                current_price=h.current_price,
                market_value=h.market_value,
                gain=h.gain,
                return_pct=h.return_pct,
                weight_pct=weight.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            ))

        return PortfolioSummary(
            portfolio_id=portfolio_id,
            name=portfolio.name,
            total_value=total_value,
            total_cost=total_cost,
            total_gain=total_gain,
            total_return_pct=total_return_pct,
            holdings=holding_summaries,
            generated_at=datetime.now(),
        )

    # ---------- 资产配置 ----------

    def get_asset_allocation(self, portfolio_id: str) -> AllocationResult:
        """资产配置分析"""
        portfolio = self._portfolios.get(portfolio_id)
        if not portfolio:
            raise ValueError(f"组合不存在: {portfolio_id}")

        holdings = self._holdings.get(portfolio_id, [])
        total_value = sum(h.market_value for h in holdings)

        if total_value == 0:
            return AllocationResult(
                portfolio_id=portfolio_id,
                by_asset_type=[],
                by_risk_level=[],
                concentration_risk={},
                rebalancing_suggestion=None,
            )

        # 按资产类型聚合
        by_type: Dict[str, Decimal] = {}
        for h in holdings:
            key = h.asset_type.value
            by_type[key] = by_type.get(key, Decimal("0")) + h.market_value

        by_asset_type = []
        for k, v in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
            by_asset_type.append(AllocationItem(
                category=k, value=v,
                weight_pct=(v / total_value * Decimal("100")).quantize(Decimal("0.01")),
            ))

        # 按风险等级聚合
        by_risk: Dict[str, Decimal] = {}
        for h in holdings:
            key = h.risk_level.value
            by_risk[key] = by_risk.get(key, Decimal("0")) + h.market_value

        by_risk_level = []
        for k, v in sorted(by_risk.items(), key=lambda x: x[1], reverse=True):
            by_risk_level.append(AllocationItem(
                category=k, value=v,
                weight_pct=(v / total_value * Decimal("100")).quantize(Decimal("0.01")),
            ))

        # 集中度风险（单一资产占比 > 25% 为高集中度）
        concentration = {}
        for h in holdings:
            weight = (h.market_value / total_value * Decimal("100")).quantize(Decimal("0.01"))
            if weight > REBALANCE_DRIFT_THRESHOLD:
                concentration[h.asset_name] = weight

        return AllocationResult(
            portfolio_id=portfolio_id,
            by_asset_type=by_asset_type,
            by_risk_level=by_risk_level,
            concentration_risk=concentration,
            rebalancing_suggestion=None,
        )

    # ---------- 收益计算 ----------

    def calculate_return(self, portfolio_id: str, period: str = "1y",
                         holding_days: int = 365) -> ReturnResult:
        """计算收益"""
        portfolio = self._portfolios.get(portfolio_id)
        if not portfolio:
            raise ValueError(f"组合不存在: {portfolio_id}")

        summary = self.get_portfolio_summary(portfolio_id)

        # 年化收益率
        if summary.total_cost > 0 and holding_days > 0:
            total_return_decimal = summary.total_gain / summary.total_cost
            # 年化: (1 + total_return)^(365/days) - 1
            import math
            annualized = ((1 + float(total_return_decimal)) ** (365.0 / holding_days) - 1.0) * 100
            annualized_pct = Decimal(str(annualized)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            annualized_pct = Decimal("0")

        holding_returns = []
        for h in summary.holdings:
            holding_returns.append({
                "asset_name": h.asset_name,
                "asset_code": h.asset_code,
                "gain": h.gain,
                "return_pct": h.return_pct,
                "weight_pct": h.weight_pct,
            })

        return ReturnResult(
            portfolio_id=portfolio_id,
            period=period,
            total_return=summary.total_gain,
            total_return_pct=summary.total_return_pct,
            annualized_return_pct=annualized_pct,
            holding_returns=holding_returns,
        )

    # ---------- 再平衡 ----------

    def suggest_rebalancing(
        self,
        portfolio_id: str,
        target_allocation: Dict[AssetType, Decimal],
    ) -> List[Dict]:
        """
        再平衡建议

        target_allocation: {AssetType: 目标比例（%）}
        """
        summary = self.get_portfolio_summary(portfolio_id)
        if summary.total_value == 0:
            return []

        # 当前配置
        current: Dict[str, Decimal] = {}
        for h in summary.holdings:
            key = h.asset_type.value
            current[key] = current.get(key, Decimal("0")) + h.weight_pct

        suggestions = []
        for asset_type, target_pct in target_allocation.items():
            current_pct = current.get(asset_type.value, Decimal("0"))
            diff = target_pct - current_pct

            if abs(diff) >= REBALANCE_DRIFT_THRESHOLD:
                adjust_value = (diff / Decimal("100") * summary.total_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                suggestions.append({
                    "asset_type": asset_type.value,
                    "current_pct": current_pct,
                    "target_pct": target_pct,
                    "diff_pct": diff.quantize(Decimal("0.01")),
                    "adjust_value": adjust_value,
                    "action": "buy" if diff > 0 else "sell",
                })

        return suggestions
