"""
FIN-L4-PF01 Rex 家庭理财系统 — 集成测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from fin_l4_pf01 import RexFamilyFinance, FamilyProfile
from fin003_insurance import InsuranceType
from fin002_loan import LoanMethod
from fin005_portfolio import AssetType
from fin_l4_pf01.data.rex_family_data import (
    get_family_profile, get_opening_balances,
    get_loans, get_insurances, get_investments,
)


def test_full_pipeline():
    """完整端到端流程"""
    system = RexFamilyFinance()

    # 1. 家庭画像
    profile_data = get_family_profile()
    profile = FamilyProfile(
        name=profile_data["name"],
        members=profile_data["members"],
        monthly_income=profile_data["monthly_income"],
        monthly_expenses=profile_data["monthly_expenses"],
        total_assets=profile_data["total_assets"],
        total_liabilities=profile_data["total_liabilities"],
        emergency_fund=profile_data["emergency_fund"],
    )
    system.load_family_profile(profile)

    # 2. 科目表 + 期初余额
    balances = get_opening_balances()
    system.setup_chart_of_accounts(opening_balances=balances)

    tb = system.accounting.get_trial_balance()
    assert tb.is_balanced, f"试算不平衡: 借={tb.debit_total}, 贷={tb.credit_total}"
    print(f"✅ 试算平衡: 借={tb.debit_total}, 贷={tb.credit_total}")

    # 3. 贷款
    loans_data = get_loans()
    for ld in loans_data:
        method_map = {"equal_payment": LoanMethod.EQUAL_PAYMENT, "equal_principal": LoanMethod.EQUAL_PRINCIPAL}
        system.add_loan(
            name=ld["name"], principal=ld["principal"],
            annual_rate=ld["annual_rate"], term_months=ld["term_months"],
            method=method_map.get(ld["method"], LoanMethod.EQUAL_PAYMENT),
        )
    assert len(system._loans) == len(loans_data)
    print(f"✅ 贷款: {len(system._loans)} 笔")

    # 4. 保险
    ins_data = get_insurances()
    type_map = {
        "whole_life": InsuranceType.WHOLE_LIFE,
        "term_life": InsuranceType.TERM_LIFE,
        "critical_illness": InsuranceType.CRITICAL_ILLNESS,
        "medical": InsuranceType.MEDICAL,
    }
    for ins in ins_data:
        system.add_insurance(
            name=ins["name"], policy_type=type_map[ins["policy_type"]],
            premium=ins["premium"], sum_assured=ins["sum_assured"],
            term_years=ins["term_years"], payment_years=ins["payment_years"],
            insured_age=ins["insured_age"],
        )
    assert len(system._policies) == len(ins_data)
    print(f"✅ 保险: {len(system._policies)} 份")

    # 5. 投资组合
    portfolio = system.setup_portfolio()
    inv_data = get_investments()
    asset_map = {"stock": AssetType.STOCK, "fund": AssetType.FUND, "bond": AssetType.BOND, "cash": AssetType.CASH}
    for inv in inv_data:
        system.portfolio.add_holding(
            portfolio_id=portfolio.id, asset_type=asset_map[inv["asset_type"]],
            asset_name=inv["asset_name"], asset_code=inv["asset_code"],
            shares=inv["shares"], cost_basis_price=inv["cost_basis_price"],
            current_price=inv["current_price"],
        )
    pfo = system.portfolio.get_portfolio_summary(portfolio.id)
    assert len(pfo.holdings) == len(inv_data)
    print(f"✅ 投资组合: {len(pfo.holdings)} 只标的")

    # 6. 综合报告
    report = system.generate_family_report()
    assert report.health_score >= 0
    assert len(report.loan_summaries) == len(loans_data)
    assert len(report.insurance_summaries) == len(ins_data)
    assert report.portfolio_summary is not None
    print(f"✅ 综合报告: 健康={report.health_score}/100")

    print("\n🎉 FIN-L4-PF01 集成测试通过!")


if __name__ == "__main__":
    test_full_pipeline()
