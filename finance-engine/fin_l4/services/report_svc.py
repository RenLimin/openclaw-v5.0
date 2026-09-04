"""报表服务 — 调用 L3 引擎生成各类报表"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional
from fin_l4.db.repositories import (
    AccountRepository, TransactionRepository, LoanRepository,
    InsuranceRepository, PortfolioRepository, HoldingRepository,
)


class ReportService:
    """报表服务"""

    def __init__(self, conn):
        self.conn = conn
        self.account_repo = AccountRepository(conn)
        self.txn_repo = TransactionRepository(conn)
        self.loan_repo = LoanRepository(conn)
        self.insurance_repo = InsuranceRepository(conn)
        self.portfolio_repo = PortfolioRepository(conn)
        self.holding_repo = HoldingRepository(conn)

    def balance_sheet(self, family_id: str) -> Dict:
        """资产负债表（时点快照）"""
        accounts = self.account_repo.list_by_family(family_id)

        assets = []
        liabilities = []
        equity = []
        total_assets = Decimal("0")
        total_liabilities = Decimal("0")
        total_equity = Decimal("0")

        for acc in accounts:
            balance = self.account_repo.get_balance(acc["id"])
            if balance == 0:
                continue

            item = {
                "code": acc["code"],
                "name": acc["name"],
                "balance": str(balance),
            }

            if acc["type"] == "ASSET":
                assets.append(item)
                total_assets += balance
            elif acc["type"] == "LIABILITY":
                liabilities.append(item)
                total_liabilities += balance
            elif acc["type"] == "EQUITY":
                equity.append(item)
                total_equity += balance

        return {
            "date": str(date.today()),
            "assets": assets,
            "total_assets": str(total_assets),
            "liabilities": liabilities,
            "total_liabilities": str(total_liabilities),
            "equity": equity,
            "total_equity": str(total_equity),
            "net_worth": str(total_assets - total_liabilities),
            "is_balanced": (total_assets == total_liabilities + total_equity),
        }

    def income_summary(self, family_id: str, from_date: str = None,
                       to_date: str = None) -> Dict:
        """收支汇总表"""
        accounts = self.account_repo.list_by_family(family_id)

        income_total = Decimal("0")
        expense_total = Decimal("0")
        income_items = []
        expense_items = []

        for acc in accounts:
            if acc["type"] not in ("INCOME", "EXPENSE"):
                continue

            balance = self.account_repo.get_balance(acc["id"])
            if balance == 0:
                continue

            item = {"code": acc["code"], "name": acc["name"], "amount": str(balance)}

            if acc["type"] == "INCOME":
                income_items.append(item)
                income_total += balance
            else:
                expense_items.append(item)
                expense_total += balance

        return {
            "from_date": from_date or "—",
            "to_date": to_date or str(date.today()),
            "income": income_items,
            "total_income": str(income_total),
            "expenses": expense_items,
            "total_expenses": str(expense_total),
            "net": str(income_total - expense_total),
        }

    def cashflow_monthly(self, family_id: str, months: int = 6) -> List[Dict]:
        """月度现金流"""
        rows = self.conn.execute(
            """
            SELECT substr(date, 1, 7) as month,
                   SUM(CASE WHEN t.amount > 0 THEN CAST(t.amount AS DECIMAL) ELSE 0 END) as total_in,
                   SUM(CASE WHEN t.amount < 0 THEN CAST(t.amount AS DECIMAL) ELSE 0 END) as total_out
            FROM fin4_transactions t
            WHERE t.family_id = ?
            GROUP BY substr(date, 1, 7)
            ORDER BY month DESC
            LIMIT ?
            """,
            (family_id, months),
        ).fetchall()

        return [
            {
                "month": r["month"],
                "income": str(r["total_in"] or 0),
                "expense": str(abs(r["total_out"] or 0)),
            }
            for r in rows
        ]

    def loan_summary(self, family_id: str) -> List[Dict]:
        """贷款概览"""
        loans = self.loan_repo.list_by_family(family_id)
        return [
            {
                "id": loan["id"],
                "name": loan["name"],
                "principal": loan["principal"],
                "rate": loan["annual_rate"],
                "term": loan["term_months"],
                "method": loan["method"],
                "status": loan["status"],
            }
            for loan in loans
        ]

    def insurance_summary(self, family_id: str) -> List[Dict]:
        """保险概览"""
        policies = self.insurance_repo.list_by_family(family_id)
        return [
            {
                "id": policy["id"],
                "name": policy["product_name"],
                "type": policy["policy_type"],
                "premium": policy["annual_premium"],
                "sum_assured": policy["sum_assured"],
                "status": policy["status"],
            }
            for policy in policies
        ]

    def net_worth_trend(self, family_id: str) -> List[Dict]:
        """净值趋势（简化：当前净值）"""
        bs = self.balance_sheet(family_id)
        return [
            {
                "date": str(date.today()),
                "net_worth": bs["net_worth"],
                "total_assets": bs["total_assets"],
                "total_liabilities": bs["total_liabilities"],
            }
        ]

    def asset_distribution(self, family_id: str) -> List[Dict]:
        """资产分布按大分类汇总"""
        accounts = self.account_repo.list_by_family(family_id)
        categories = {
            "liquid": {"name": "现金/活期", "total": Decimal("0")},
            "fixed": {"name": "定期存款", "total": Decimal("0")},
            "investment": {"name": "投资资产", "total": Decimal("0")},
            "other": {"name": "其他资产", "total": Decimal("0")},
        }

        for acc in accounts:
            balance = self.account_repo.get_balance(acc["id"])
            if balance <= 0:
                continue
            # 这里简单分类：根据账户代码前缀或者类型
            # 对于演示数据，我们按以下方式分类
            if acc["code"].startswith("LIQ_"):
                categories["liquid"]["total"] += balance
            elif acc["code"].startswith("FIX_"):
                categories["fixed"]["total"] += balance
            elif acc["code"].startswith("INV_"):
                categories["investment"]["total"] += balance
            else:
                categories["other"]["total"] += balance

        result = []
        for cat in categories.values():
            if cat["total"] > 0:
                result.append({"label": cat["name"], "value": str(cat["total"])})

        return result
