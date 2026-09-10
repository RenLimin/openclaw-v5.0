
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

    # ========== 仪表盘专用方法 ==========

    def dashboard_overview(self, family_id: str) -> Dict:
        """仪表盘总览：总资产、总负债、本月收入/支出/结余、储蓄率"""
        from calendar import monthrange
        from datetime import date as _date

        today = _date.today()
        month_start = _date(today.year, today.month, 1).strftime('%Y-%m-%d')
        _, last_day = monthrange(today.year, today.month)
        month_end = _date(today.year, today.month, last_day).strftime('%Y-%m-%d')

        bs = self.balance_sheet(family_id)
        total_assets = Decimal(bs['total_assets'])
        total_liabilities = Decimal(bs['total_liabilities'])
        net_worth = total_assets - total_liabilities

        income = Decimal('0')
        expense = Decimal('0')
        rows = self.conn.execute(
            """
            SELECT c.type as category_type,
                   COALESCE(SUM(CAST(t.amount AS DECIMAL)), 0) as total
            FROM fin4_transactions t
            JOIN fin4_categories c ON c.id = t.category_id
            WHERE t.family_id = ?
              AND t.date >= ? AND t.date <= ?
              AND c.type IN ('income', 'expense')
            GROUP BY c.type
            """,
            (family_id, month_start, month_end),
        ).fetchall()
        for r in rows:
            if r['category_type'] == 'income':
                income = Decimal(str(r['total']))
            elif r['category_type'] == 'expense':
                expense = Decimal(str(r['total']))

        savings_rate = (
            ((income - expense) / income * 100).quantize(Decimal('0.1'))
            if income > 0 else Decimal('0')
        )
        debt_ratio = (
            (total_liabilities / total_assets * 100).quantize(Decimal('0.1'))
            if total_assets > 0 else Decimal('0')
        )

        return {
            'total_assets': str(total_assets),
            'total_liabilities': str(total_liabilities),
            'net_worth': str(net_worth),
            'monthly_income': str(income),
            'monthly_expense': str(expense),
            'monthly_savings': str(income - expense),
            'savings_rate': str(savings_rate),
            'debt_ratio': str(debt_ratio),
            'month': today.strftime('%Y-%m'),
        }

    def category_summary(self, family_id: str, month: str = None,
                        category_type: str = None) -> List[Dict]:
        """分类统计汇总
        category_type: 'income' | 'expense' | None(全部)
        month: 'YYYY-MM'，默认本月
        """
        from calendar import monthrange
        from datetime import date as _date

        if month is None:
            today = _date.today()
            month = today.strftime('%Y-%m')

        year, mon = map(int, month.split('-'))
        _, last_day = monthrange(year, mon)
        month_start = f'{year}-{mon:02d}-01'
        month_end = f'{year}-{mon:02d}-{last_day:02d}'

        sql = """
        SELECT c.id as category_id,
               c.name as category_name,
               c.type as category_type,
               c.color as color,
               COALESCE(SUM(CAST(t.amount AS DECIMAL)), 0) as total
        FROM fin4_transactions t
        JOIN fin4_categories c ON c.id = t.category_id
        WHERE t.family_id = ?
          AND t.date >= ? AND t.date <= ?
          AND c.family_id = ?
        """
        params = [family_id, month_start, month_end, family_id]

        if category_type:
            sql += ' AND c.type = ?'
            params.append(category_type)

        sql += ' GROUP BY c.id, c.name, c.type, c.color ORDER BY total DESC'

        rows = self.conn.execute(sql, params).fetchall()

        result = []
        for r in rows:
            result.append({
                'category_id': r['category_id'],
                'category_name': r['category_name'],
                'type': r['category_type'],
                'color': r['color'] or self._default_color(r['category_type'], r['category_id']),
                'amount': str(Decimal(str(r['total']))),
            })

        return result

    def _default_color(self, cat_type: str, cat_id: str) -> str:
        """默认分类配色"""
        income_colors = ['#10b981', '#14b8a6', '#06b6d4', '#3b82f6', '#6366f1', '#8b5cf6']
        expense_colors = ['#ef4444', '#f97316', '#f59e0b', '#eab308', '#ec4899', '#f43f5e']
        colors = income_colors if cat_type == 'income' else expense_colors
        idx = abs(hash(cat_id)) % len(colors)
        return colors[idx]

    def monthly_trend(self, family_id: str, months: int = 12) -> List[Dict]:
        """月度收支趋势（近 N 个月，含结余）"""
        rows = self.conn.execute(
            """
            SELECT substr(date, 1, 7) as month,
                   SUM(CASE WHEN c.type = 'income' THEN CAST(t.amount AS DECIMAL) ELSE 0 END) as income,
                   SUM(CASE WHEN c.type = 'expense' THEN CAST(t.amount AS DECIMAL) ELSE 0 END) as expense
            FROM fin4_transactions t
            LEFT JOIN fin4_categories c ON c.id = t.category_id
            WHERE t.family_id = ?
              AND c.type IS NOT NULL
            GROUP BY substr(date, 1, 7)
            ORDER BY month DESC
            LIMIT ?
            """,
            (family_id, months),
        ).fetchall()

        result = []
        for r in reversed(rows):
            income_val = Decimal(str(r['income'] or 0))
            expense_val = Decimal(str(r['expense'] or 0))
            result.append({
                'month': r['month'],
                'income': str(income_val),
                'expense': str(expense_val),
                'savings': str(income_val - expense_val),
            })
        return result

    def recent_transactions(self, family_id: str, limit: int = 20) -> List[Dict]:
        """最近交易记录（带分类名）"""
        rows = self.conn.execute(
            """
            SELECT t.*, c.name as category_name, c.type as category_type
            FROM fin4_transactions t
            LEFT JOIN fin4_categories c ON c.id = t.category_id
            WHERE t.family_id = ?
            ORDER BY t.date DESC, t.created_at DESC
            LIMIT ?
            """,
            (family_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def budget_progress(self, family_id: str, month: str = None) -> Dict:
        """预算执行进度（仪表盘用）"""
        from datetime import date as _date
        if month is None:
            month = _date.today().strftime('%Y-%m')
        from fin_l4.services.budget_svc import BudgetService
        svc = BudgetService(self.conn)
        return svc.get_overview(family_id, month)

    def investment_summary(self, family_id: str) -> List[Dict]:
        """投资组合概览（含持仓 + 收益）"""
        portfolios = self.portfolio_repo.list_by_family(family_id)
        result = []

        for p in portfolios:
            holdings = self.holding_repo.list_by_portfolio(p['id'])
            total_cost = Decimal('0')
            total_value = Decimal('0')

            holding_list = []
            for h in holdings:
                shares = Decimal(str(h['shares']))
                cost_price = Decimal(str(h['cost_basis_price']))
                current_price = Decimal(str(h.get('current_price') or h['cost_basis_price']))

                cost = shares * cost_price
                value = shares * current_price
                gain = value - cost
                gain_pct = (gain / cost * 100).quantize(Decimal('0.1')) if cost > 0 else Decimal('0')

                total_cost += cost
                total_value += value

                holding_list.append({
                    'id': h['id'],
                    'asset_name': h['asset_name'],
                    'asset_code': h['asset_code'],
                    'asset_type': h['asset_type'],
                    'shares': str(shares),
                    'cost_price': str(cost_price),
                    'current_price': str(current_price),
                    'cost': str(cost.quantize(Decimal('0.01'))),
                    'value': str(value.quantize(Decimal('0.01'))),
                    'gain': str(gain.quantize(Decimal('0.01'))),
                    'gain_pct': str(gain_pct),
                })

            total_gain = total_value - total_cost
            total_gain_pct = (
                (total_gain / total_cost * 100).quantize(Decimal('0.1'))
                if total_cost > 0 else Decimal('0')
            )

            result.append({
                'portfolio_id': p['id'],
                'portfolio_name': p['name'],
                'base_currency': p['base_currency'],
                'total_cost': str(total_cost.quantize(Decimal('0.01'))),
                'total_value': str(total_value.quantize(Decimal('0.01'))),
                'total_gain': str(total_gain.quantize(Decimal('0.01'))),
                'total_gain_pct': str(total_gain_pct),
                'holdings': holding_list,
            })

        return result
