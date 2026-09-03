"""
FIN-L4-PF01 Rex 家庭理财系统

L4 专有业务层实例：
- 灌入 Rex 家庭模拟数据
- 调用 L3 引擎计算
- 生成报表 + 理财建议
"""

from datetime import date, datetime
from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# L3 引擎
from fin001_account import AccountingEngine, AccountType
from fin002_loan import LoanEngine, LoanMethod
from fin003_insurance import InsuranceEngine, InsuranceType
from fin004_rate import RateEngine
from fin005_portfolio import PortfolioEngine, AssetType
from fin006_advisor import AdvisorEngine, DebtInfo


@dataclass
class FamilyProfile:
    """家庭画像"""
    name: str
    members: List[Dict]
    monthly_income: Decimal
    monthly_expenses: Decimal
    total_assets: Decimal
    total_liabilities: Decimal
    emergency_fund: Decimal
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class FamilyFinancialReport:
    """家庭财务报告"""
    profile: FamilyProfile
    account_summary: Dict
    loan_summaries: List[Dict]
    insurance_summaries: List[Dict]
    portfolio_summary: Optional[Dict]
    health_score: int
    advisor_summary: str
    generated_at: datetime = field(default_factory=datetime.now)


class RexFamilyFinance:
    """Rex 家庭理财系统"""

    def __init__(self):
        # L3 引擎
        self.accounting = AccountingEngine()
        self.loan = LoanEngine()
        self.insurance = InsuranceEngine()
        self.rate = RateEngine()
        self.portfolio = PortfolioEngine()
        self.advisor = AdvisorEngine()

        # 家庭数据
        self.profile: Optional[FamilyProfile] = None
        self._loans = []
        self._policies = []

    # ---------- 数据导入 ----------

    def load_family_profile(self, profile: FamilyProfile):
        """加载家庭画像"""
        self.profile = profile

    def setup_chart_of_accounts(self, opening_balances: Optional[Dict[str, Decimal]] = None):
        """建立科目表（含期初余额）"""
        balances = opening_balances or {}

        # 资产类
        self.accounting.create_account(name="库存现金", type=AccountType.ASSET, account_id="1001",
                                       initial_balance=balances.get("库存现金", Decimal("0")))
        self.accounting.create_account(name="银行存款", type=AccountType.ASSET, account_id="1002",
                                       initial_balance=balances.get("银行存款", Decimal("0")))
        self.accounting.create_account(name="股票投资", type=AccountType.ASSET, account_id="1010",
                                       initial_balance=balances.get("股票投资", Decimal("0")))
        self.accounting.create_account(name="基金投资", type=AccountType.ASSET, account_id="1011",
                                       initial_balance=balances.get("基金投资", Decimal("0")))
        self.accounting.create_account(name="债券投资", type=AccountType.ASSET, account_id="1012",
                                       initial_balance=balances.get("债券投资", Decimal("0")))
        self.accounting.create_account(name="保单现金价值", type=AccountType.ASSET, account_id="1020",
                                       initial_balance=balances.get("保单现金价值", Decimal("0")))
        self.accounting.create_account(name="房产", type=AccountType.ASSET, account_id="1501",
                                       initial_balance=balances.get("房产", Decimal("0")))

        # 负债类
        self.accounting.create_account(name="信用卡欠款", type=AccountType.LIABILITY, account_id="2001",
                                       initial_balance=balances.get("信用卡欠款", Decimal("0")))
        self.accounting.create_account(name="消费贷", type=AccountType.LIABILITY, account_id="2002",
                                       initial_balance=balances.get("消费贷", Decimal("0")))
        self.accounting.create_account(name="房贷", type=AccountType.LIABILITY, account_id="2501",
                                       initial_balance=balances.get("房贷", Decimal("0")))

        # 权益类
        self.accounting.create_account(name="初始权益", type=AccountType.EQUITY, account_id="3001",
                                       initial_balance=balances.get("初始权益", Decimal("0")))

        # 收入类
        self.accounting.create_account(name="工资收入", type=AccountType.INCOME, account_id="4001")
        self.accounting.create_account(name="投资收益", type=AccountType.INCOME, account_id="4002")

        # 费用类
        self.accounting.create_account(name="利息支出", type=AccountType.EXPENSE, account_id="5001")
        self.accounting.create_account(name="保费支出", type=AccountType.EXPENSE, account_id="5002")
        self.accounting.create_account(name="生活支出", type=AccountType.EXPENSE, account_id="5003")

    # ---------- 贷款 ----------

    def add_loan(self, name, principal, annual_rate, term_months,
                 method=LoanMethod.EQUAL_PAYMENT, start_date=None):
        """添加贷款"""
        loan = self.loan.create_loan(
            name=name,
            principal=principal,
            annual_rate=annual_rate,
            term_months=term_months,
            method=method,
            start_date=start_date or date.today(),
        )
        self._loans.append(loan)
        return loan

    # ---------- 保险 ----------

    def add_insurance(self, name, policy_type, premium, sum_assured,
                      term_years, payment_years, insured_age,
                      insured_gender="M"):
        """添加保险"""
        policy = self.insurance.create_policy(
            product_name=name,
            policy_type=policy_type,
            annual_premium=premium,
            sum_assured=sum_assured,
            term_years=term_years,
            payment_years=payment_years,
            insured_age=insured_age,
            insured_gender=insured_gender,
        )
        self._policies.append(policy)
        return policy

    # ---------- 投资 ----------

    def setup_portfolio(self, name="Rex 家庭投资组合"):
        """建立投资组合"""
        return self.portfolio.create_portfolio(name)

    # ---------- 报表 ----------

    def generate_family_report(self) -> FamilyFinancialReport:
        """生成家庭财务报告"""
        # 1. 账户摘要
        trial_balance = self.accounting.get_trial_balance()
        account_summary = {
            "total_debits": trial_balance.debit_total,
            "total_credits": trial_balance.credit_total,
            "balanced": trial_balance.is_balanced,
            "accounts": len(self.accounting.get_all_accounts()),
        }

        # 2. 贷款摘要
        loan_summaries = []
        for loan in self._loans:
            summary = self.loan.get_loan_summary(loan)
            schedule = self.loan.calculate_amortization_schedule(loan)
            loan_summaries.append({
                "name": loan.name,
                "monthly_payment": summary.next_payment_amount,
                "total_interest": summary.total_interest,
                "remaining_principal": summary.remaining_balance,
                "paid_months": summary.paid_periods,
                "remaining_months": summary.remaining_periods,
            })

        # 3. 保险摘要
        insurance_summaries = []
        for policy in self._policies:
            try:
                cv = self.insurance.calculate_cash_value(policy.id, 5)
                cv_val = cv.total_cv
            except ValueError:
                cv_val = None
            insurance_summaries.append({
                "name": policy.product_name,
                "type": policy.policy_type.value,
                "premium": policy.annual_premium,
                "sum_assured": policy.sum_assured,
                "cash_value_5y": cv_val,
            })

        # 4. 投资组合
        portfolios = self.portfolio.get_all_portfolios()
        portfolio_summary = None
        if portfolios:
            pfo_summary = self.portfolio.get_portfolio_summary(portfolios[0].id)
            alloc = self.portfolio.get_asset_allocation(portfolios[0].id)
            portfolio_summary = {
                "name": pfo_summary.name,
                "total_value": pfo_summary.total_value,
                "total_gain": pfo_summary.total_gain,
                "return_pct": pfo_summary.total_return_pct,
                "holdings": len(pfo_summary.holdings),
                "allocation": [
                    {"type": a.category, "weight": a.weight_pct}
                    for a in alloc.by_asset_type
                ],
            }

        # 5. 理财建议
        debts = [
            DebtInfo(
                name=ls["name"],
                balance=ls["remaining_principal"],
                annual_rate=loan.annual_rate,
                min_payment=ls["monthly_payment"],
            )
            for ls, loan in zip(loan_summaries, self._loans)
        ]

        advisor_report = self.advisor.generate_financial_report(
            monthly_income=self.profile.monthly_income,
            monthly_expenses=self.profile.monthly_expenses,
            total_assets=self.profile.total_assets,
            total_liabilities=self.profile.total_liabilities,
            emergency_fund=self.profile.emergency_fund,
            debts=debts if debts else None,
            monthly_budget=self.profile.monthly_income * Decimal("0.2"),
            age=30,
            risk_capacity=3,
            risk_tolerance=4,
        )

        return FamilyFinancialReport(
            profile=self.profile,
            account_summary=account_summary,
            loan_summaries=loan_summaries,
            insurance_summaries=insurance_summaries,
            portfolio_summary=portfolio_summary,
            health_score=advisor_report.health_score,
            advisor_summary=advisor_report.summary,
        )
