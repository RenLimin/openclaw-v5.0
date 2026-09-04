"""预算管理服务"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class BudgetStatus:
    """预算执行状态"""
    category_id: str
    category_name: str
    budget_amount: Decimal
    spent_amount: Decimal
    remaining: Decimal
    usage_pct: Decimal  # 百分比
    status: str  # ok / warning / exceeded
    days_left: int
    daily_budget: Decimal  # 剩余日均预算


class BudgetService:
    """预算管理"""

    def __init__(self, conn):
        self.conn = conn

    def set_budget(self, family_id: str, category_id: str,
                   month: str, amount: str) -> Dict:
        """
        设置月度预算
        month: "2026-09"
        """
        from fin_l4.db.repositories import BudgetRepository
        repo = BudgetRepository(self.conn)
        bid = repo.upsert(family_id, category_id, month, amount)
        return {"id": bid, "status": "ok"}

    def get_budget(self, family_id: str, category_id: str,
                   month: str) -> Optional[Dict]:
        """查询单个预算"""
        from fin_l4.db.repositories import BudgetRepository
        repo = BudgetRepository(self.conn)
        return repo.get(family_id, category_id, month)

    def list_budgets(self, family_id: str, month: str) -> List[Dict]:
        """列出当月所有预算"""
        from fin_l4.db.repositories import BudgetRepository
        repo = BudgetRepository(self.conn)
        return repo.list_by_family(family_id, month)

    def get_status(self, family_id: str, month: str) -> List[BudgetStatus]:
        """
        获取预算执行状态
        对比预算 vs 实际支出
        """
        from fin_l4.db.repositories import (
            BudgetRepository, TransactionRepository, CategoryRepository,
            AccountRepository
        )
        budget_repo = BudgetRepository(self.conn)
        txn_repo = TransactionRepository(self.conn)
        cat_repo = CategoryRepository(self.conn)
        account_repo = AccountRepository(self.conn)

        budgets = budget_repo.list_by_family(family_id, month)
        if not budgets:
            return []

        # 解析月份范围
        year, mon = map(int, month.split("-"))
        from calendar import monthrange
        _, last_day = monthrange(year, mon)
        from datetime import date
        month_start = date(year, mon, 1)
        month_end = date(year, mon, last_day)
        days_in_month = last_day
        days_elapsed = min(date.today().day, last_day)
        days_left = max(days_in_month - days_elapsed, 0)

        results = []
        for budget in budgets:
            cat_id = budget["category_id"]
            cat = cat_repo.get(cat_id)
            budget_amount = Decimal(budget["amount"])

            # 计算该分类当月实际支出
            spent = self._calc_spent(
                family_id, cat_id, month_start, month_end,
                txn_repo, account_repo
            )

            remaining = budget_amount - spent
            usage_pct = (
                (spent / budget_amount * 100).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                ) if budget_amount > 0 else Decimal("0")
            )

            if usage_pct >= Decimal("100"):
                status = "exceeded"
            elif usage_pct >= Decimal("80"):
                status = "warning"
            else:
                status = "ok"

            daily_budget = (
                remaining / days_left if days_left > 0 else remaining
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            results.append(BudgetStatus(
                category_id=cat_id,
                category_name=cat["name"] if cat else cat_id,
                budget_amount=budget_amount,
                spent_amount=spent,
                remaining=remaining,
                usage_pct=usage_pct,
                status=status,
                days_left=days_left,
                daily_budget=daily_budget,
            ))

        return results

    def _calc_spent(self, family_id: str, category_id: str,
                    month_start, month_end, txn_repo, account_repo) -> Decimal:
        """计算某分类当月支出总额（直接按 category_id 汇总）"""
        txns = txn_repo.list_by_family(
            family_id, from_date=str(month_start), to_date=str(month_end), limit=1000
        )
        total = Decimal("0")
        for txn in txns:
            if txn.get("category_id") == category_id:
                total += Decimal(txn["amount"])
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def get_overview(self, family_id: str, month: str) -> Dict:
        """预算总览"""
        statuses = self.get_status(family_id, month)
        if not statuses:
            return {"month": month, "total_budget": "0", "total_spent": "0"}

        total_budget = sum(s.budget_amount for s in statuses)
        total_spent = sum(s.spent_amount for s in statuses)
        exceeded = sum(1 for s in statuses if s.status == "exceeded")
        warning = sum(1 for s in statuses if s.status == "warning")

        return {
            "month": month,
            "total_budget": str(total_budget),
            "total_spent": str(total_spent),
            "total_remaining": str(total_budget - total_spent),
            "categories": len(statuses),
            "exceeded": exceeded,
            "warning": warning,
            "statuses": [
                {
                    "category": s.category_name,
                    "budget": str(s.budget_amount),
                    "spent": str(s.spent_amount),
                    "remaining": str(s.remaining),
                    "usage_pct": str(s.usage_pct),
                    "status": s.status,
                    "days_left": s.days_left,
                    "daily_budget": str(s.daily_budget),
                }
                for s in statuses
            ],
        }
