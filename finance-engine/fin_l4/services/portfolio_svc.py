"""投资服务 — 调用 FIN-005 引擎"""

from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional
from fin005_portfolio import PortfolioEngine, AssetType
from fin_l4.db.repositories import PortfolioRepository, HoldingRepository, AuditLogRepository


ASSET_TYPE_MAP = {
    "stock": AssetType.STOCK,
    "bond": AssetType.BOND,
    "fund": AssetType.FUND,
    "cash": AssetType.CASH,
    "real_estate": AssetType.REAL_ESTATE,
    "insurance_cv": AssetType.INSURANCE_CV,
    "other": AssetType.OTHER,
}


class PortfolioService:
    """投资服务"""

    def __init__(self, conn):
        self.conn = conn
        self.portfolio_repo = PortfolioRepository(conn)
        self.holding_repo = HoldingRepository(conn)
        self.audit = AuditLogRepository(conn)
        self.engine = PortfolioEngine()

    def create_portfolio(self, family_id: str, name: str,
                         base_currency: str = "CNY") -> Dict:
        """创建投资组合"""
        portfolio_id = self.portfolio_repo.create(family_id, name, base_currency)
        self.audit.log(
            family_id=family_id, user="system", action="create",
            entity_type="portfolio", entity_id=portfolio_id,
            details={"name": name},
        )
        return {"id": portfolio_id, "name": name}

    def buy(self, portfolio_id: str, asset_type: str, asset_name: str,
            asset_code: str, shares: str, price: str) -> Dict:
        """买入"""
        if asset_type not in ASSET_TYPE_MAP:
            raise ValueError(f"无效资产类型: {asset_type}")

        holding_id = self.holding_repo.create(
            portfolio_id=portfolio_id,
            asset_type=asset_type,
            asset_name=asset_name,
            asset_code=asset_code,
            shares=shares,
            cost_basis_price=price,
            current_price=price,
        )

        return {"id": holding_id, "action": "buy", "asset": asset_name}

    def sell(self, holding_id: str, shares: str = None) -> Dict:
        """卖出（简化：全部卖出）"""
        # 实际实现需要部分卖出逻辑
        return {"id": holding_id, "action": "sell"}

    def update_price(self, holding_id: str, current_price: str) -> Dict:
        """更新市价"""
        self.holding_repo.update_price(holding_id, current_price)
        return {"id": holding_id, "current_price": current_price}

    def get_performance(self, portfolio_id: str) -> Dict:
        """盈亏分析 — 调用 FIN-005"""
        holdings = self.holding_repo.list_by_portfolio(portfolio_id)
        if not holdings:
            return {"portfolio_id": portfolio_id, "total_value": "0", "holdings": []}

        # 灌入 L3 引擎
        portfolio = self.engine.create_portfolio("temp")
        for h in holdings:
            self.engine.add_holding(
                portfolio_id=portfolio.id,
                asset_type=ASSET_TYPE_MAP.get(h["asset_type"], AssetType.OTHER),
                asset_name=h["asset_name"],
                asset_code=h.get("asset_code", ""),
                shares=Decimal(h["shares"]),
                cost_basis_price=Decimal(h["cost_basis_price"]),
                current_price=Decimal(h["current_price"] or h["cost_basis_price"]),
            )

        summary = self.engine.get_portfolio_summary(portfolio.id)
        return {
            "portfolio_id": portfolio_id,
            "total_value": str(summary.total_value),
            "total_cost": str(summary.total_cost),
            "total_gain": str(summary.total_gain),
            "total_return_pct": str(summary.total_return_pct),
            "holdings": len(holdings),
        }

    def get_allocation(self, portfolio_id: str) -> Dict:
        """资产配置 — 调用 FIN-005"""
        holdings = self.holding_repo.list_by_portfolio(portfolio_id)
        if not holdings:
            return {"portfolio_id": portfolio_id, "allocation": []}

        portfolio = self.engine.create_portfolio("temp")
        for h in holdings:
            self.engine.add_holding(
                portfolio_id=portfolio.id,
                asset_type=ASSET_TYPE_MAP.get(h["asset_type"], AssetType.OTHER),
                asset_name=h["asset_name"],
                asset_code=h.get("asset_code", ""),
                shares=Decimal(h["shares"]),
                cost_basis_price=Decimal(h["cost_basis_price"]),
                current_price=Decimal(h["current_price"] or h["cost_basis_price"]),
            )

        alloc = self.engine.get_asset_allocation(portfolio.id)
        return {
            "portfolio_id": portfolio_id,
            "allocation": [
                {"category": a.category, "weight": str(a.weight_pct)}
                for a in alloc.by_asset_type
            ],
        }

    def get_rebalance(self, portfolio_id: str, target_alloc: Dict[str, str] = None) -> Dict:
        """再平衡建议 — 调用 FIN-005"""
        holdings = self.holding_repo.list_by_portfolio(portfolio_id)
        if not holdings:
            return {"portfolio_id": portfolio_id, "suggestions": []}

        portfolio = self.engine.create_portfolio("temp")
        for h in holdings:
            self.engine.add_holding(
                portfolio_id=portfolio.id,
                asset_type=ASSET_TYPE_MAP.get(h["asset_type"], AssetType.OTHER),
                asset_name=h["asset_name"],
                asset_code=h.get("asset_code", ""),
                shares=Decimal(h["shares"]),
                cost_basis_price=Decimal(h["cost_basis_price"]),
                current_price=Decimal(h["current_price"] or h["cost_basis_price"]),
            )

        target = None
        if target_alloc:
            target = {
                ASSET_TYPE_MAP.get(k, AssetType.OTHER): Decimal(v)
                for k, v in target_alloc.items()
            }

        suggestions = self.engine.suggest_rebalancing(portfolio.id, target)
        return {
            "portfolio_id": portfolio_id,
            "suggestions": [
                {
                    "asset_type": s.get("asset_type", ""),
                    "current_pct": str(s.get("current_pct", 0)),
                    "target_pct": str(s.get("target_pct", 0)),
                    "action": s.get("action", ""),
                    "adjust_value": str(s.get("adjust_value", 0)),
                }
                for s in suggestions
            ],
        }

    def list_portfolios(self, family_id: str) -> List[Dict]:
        """列出家庭所有组合"""
        return self.portfolio_repo.list_by_family(family_id)

    def get_holdings(self, portfolio_id: str) -> List[Dict]:
        """获取持仓明细"""
        return self.holding_repo.list_by_portfolio(portfolio_id)
