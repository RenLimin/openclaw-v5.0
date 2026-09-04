"""理财建议服务 — 调用 FIN-006 引擎"""

from decimal import Decimal
from typing import Dict, List, Optional
from fin006_advisor import AdvisorEngine, DebtStrategy
from fin_l4.db.repositories import AccountRepository


class AdviseService:
    """理财建议服务"""

    def __init__(self, conn):
        self.conn = conn
        self.account_repo = AccountRepository(conn)
        self.engine = AdvisorEngine()

    def health_check(self, family_id: str, monthly_income: str,
                     monthly_expenses: str, age: int = 30,
                     risk_capacity: int = 3, risk_tolerance: int = 4) -> Dict:
        """财务健康诊断"""
        accounts = self.account_repo.list_by_family(family_id)

        total_assets = Decimal("0")
        total_liabilities = Decimal("0")
        liquid_assets = Decimal("0")

        for acc in accounts:
            balance = self.account_repo.get_balance(acc["id"])
            if acc["type"] == "ASSET":
                total_assets += balance
                # 流动资产：现金、银行存款
                if acc["code"] in ("1001", "1002"):
                    liquid_assets += balance
            elif acc["type"] == "LIABILITY":
                total_liabilities += balance

        report = self.engine.generate_financial_report(
            monthly_income=Decimal(monthly_income),
            monthly_expenses=Decimal(monthly_expenses),
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            emergency_fund=liquid_assets,
            age=age,
            risk_capacity=risk_capacity,
            risk_tolerance=risk_tolerance,
        )

        result = {
            "health_score": report.health_score,
            "summary": report.summary,
        }
        if report.allocation_advice:
            result["allocation"] = report.allocation_advice
        if report.debt_plan:
            result["debt_plan"] = report.debt_plan
        if report.insurance_gap:
            result["insurance_gap"] = report.insurance_gap
        return result

    def debt_optimization(self, family_id: str,
                          strategy: str = "avalanche") -> Dict:
        """债务优化建议"""
        if strategy not in ("avalanche", "snowball"):
            raise ValueError(f"无效策略: {strategy}")

        accounts = self.account_repo.list_by_family(family_id)
        debts = []
        for acc in accounts:
            if acc["type"] == "LIABILITY":
                balance = self.account_repo.get_balance(acc["id"])
                if balance > 0:
                    debts.append({
                        "name": acc["name"],
                        "balance": balance,
                        "rate": Decimal("0.05"),  # 默认估算
                    })

        if not debts:
            return {"message": "无负债，无需优化", "plan": []}

        return {
            "strategy": strategy,
            "debts": [
                {"name": d["name"], "balance": str(d["balance"])}
                for d in debts
            ],
        }

    def allocation_advice(self, age: int, risk_capacity: int,
                          risk_tolerance: int) -> Dict:
        """资产配置建议"""
        result = self.engine.suggest_asset_allocation(
            age=age,
            risk_capacity=risk_capacity,
            risk_tolerance=risk_tolerance,
        )
        return {
            "risk_level": result.risk_level.value,
            "target_allocation": {k: str(v) for k, v in result.target_allocation.items()},
            "rationale": result.rationale,
        }
