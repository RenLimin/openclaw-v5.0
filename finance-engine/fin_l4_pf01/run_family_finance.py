"""
FIN-L4-PF01 Rex 家庭理财系统 — 端到端运行

加载模拟数据 → 调用 L3 引擎 → 生成完整财务报告
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from datetime import date

from fin_l4_pf01 import RexFamilyFinance, FamilyProfile
from fin002_loan import LoanMethod
from fin003_insurance import InsuranceType
from fin005_portfolio import AssetType
from data.rex_family_data import (
    get_family_profile, get_opening_balances,
    get_loans, get_insurances, get_investments,
)


def main():
    print("=" * 60)
    print("🏠 FIN-L4-PF01 Rex 家庭理财系统")
    print("=" * 60)
    print()

    # 初始化系统
    system = RexFamilyFinance()

    # 1. 加载家庭画像
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
    print(f"👨‍👩‍👧 家庭: {profile.name}")
    print(f"   月收入: {profile.monthly_income} | 月支出: {profile.monthly_expenses}")
    print(f"   总资产: {profile.total_assets} | 总负债: {profile.total_liabilities}")
    print(f"   应急资金: {profile.emergency_fund}")
    print()

    # 2. 建立科目表 + 导入期初余额
    balances = get_opening_balances()
    system.setup_chart_of_accounts(opening_balances=balances)
    print(f"📒 科目表: {len(system.accounting.get_all_accounts())} 个科目")
    tb = system.accounting.get_trial_balance()
    print(f"   试算平衡: {'✅ 平衡' if tb.is_balanced else '❌ 不平衡'} (借={tb.debit_total}, 贷={tb.credit_total})")
    print()

    # 3. 添加贷款
    loans_data = get_loans()
    for ld in loans_data:
        method_map = {
            "equal_payment": LoanMethod.EQUAL_PAYMENT,
            "equal_principal": LoanMethod.EQUAL_PRINCIPAL,
            "interest_only": LoanMethod.INTEREST_ONLY,
        }
        loan = system.add_loan(
            name=ld["name"],
            principal=ld["principal"],
            annual_rate=ld["annual_rate"],
            term_months=ld["term_months"],
            method=method_map.get(ld["method"], LoanMethod.EQUAL_PAYMENT),
            start_date=ld["start_date"],
        )
        summary = system.loan.get_loan_summary(loan)
        print(f"🏦 贷款: {loan.name}")
        print(f"   本金: {loan.principal} | 利率: {loan.annual_rate} | 期限: {loan.term_months}月")
        print(f"   月供: {summary.next_payment_amount} | 总利息: {summary.total_interest}")
        print()

    # 4. 添加保险
    ins_data = get_insurances()
    gender_map = {"male": "M", "female": "F"}
    type_map = {
        "whole_life": InsuranceType.WHOLE_LIFE,
        "term_life": InsuranceType.TERM_LIFE,
        "critical_illness": InsuranceType.CRITICAL_ILLNESS,
        "medical": InsuranceType.MEDICAL,
        "endowment": InsuranceType.ENDOWMENT,
        "annuity": InsuranceType.ANNUITY,
        "universal": InsuranceType.UNIVERSAL_LIFE,
        "tax_deferred": InsuranceType.TAX_DEFERRED,
    }
    for ins in ins_data:
        policy = system.add_insurance(
            name=ins["name"],
            policy_type=type_map[ins["policy_type"]],
            premium=ins["premium"],
            sum_assured=ins["sum_assured"],
            term_years=ins["term_years"],
            payment_years=ins["payment_years"],
            insured_age=ins["insured_age"],
            insured_gender=gender_map[ins["insured_gender"]],
        )
        print(f"🛡️ 保险: {policy.product_name}")
        print(f"   类型: {policy.policy_type.value} | 年缴保费: {policy.annual_premium} | 保额: {policy.sum_assured}")
        try:
            cv = system.insurance.calculate_cash_value(policy.id, 5)
            print(f"   5年末现金价值: {cv.total_cv}")
        except ValueError:
            print(f"   现金价值: 不支持（{policy.policy_type.value}）")
        print()

    # 5. 建立投资组合
    portfolio = system.setup_portfolio()
    inv_data = get_investments()
    asset_type_map = {
        "stock": AssetType.STOCK,
        "fund": AssetType.FUND,
        "bond": AssetType.BOND,
        "cash": AssetType.CASH,
    }
    for inv in inv_data:
        system.portfolio.add_holding(
            portfolio_id=portfolio.id,
            asset_type=asset_type_map[inv["asset_type"]],
            asset_name=inv["asset_name"],
            asset_code=inv["asset_code"],
            shares=inv["shares"],
            cost_basis_price=inv["cost_basis_price"],
            current_price=inv["current_price"],
        )

    pfo_summary = system.portfolio.get_portfolio_summary(portfolio.id)
    alloc = system.portfolio.get_asset_allocation(portfolio.id)
    print(f"📈 投资组合: {pfo_summary.name}")
    print(f"   总市值: {pfo_summary.total_value} | 总成本: {pfo_summary.total_cost}")
    print(f"   总盈亏: {pfo_summary.total_gain} ({pfo_summary.total_return_pct}%)")
    print(f"   持仓数: {len(pfo_summary.holdings)}")
    print(f"   资产配置:")
    for item in alloc.by_asset_type:
        print(f"     {item.category}: {item.value} ({item.weight_pct}%)")
    print()

    # 6. 生成综合报告
    report = system.generate_family_report()
    print("=" * 60)
    print("📋 综合财务报告")
    print("=" * 60)
    print(f"财务健康评分: {report.health_score}/100")
    print()
    print("贷款概览:")
    for ls in report.loan_summaries:
        print(f"  {ls['name']}: 月供={ls['monthly_payment']}, 总利息={ls['total_interest']}")
    print()
    print("保险概览:")
    for ins in report.insurance_summaries:
        print(f"  {ins['name']}: 保费={ins['premium']}, 保额={ins['sum_assured']}")
    print()
    if report.portfolio_summary:
        ps = report.portfolio_summary
        print(f"投资组合: {ps['name']}")
        print(f"  总市值: {ps['total_value']} | 盈亏: {ps['total_gain']} ({ps['return_pct']}%)")
        print(f"  配置: {', '.join(f'{a['type']}={a['weight']}%' for a in ps['allocation'])}")
    print()
    print(f"💡 {report.advisor_summary}")
    print()
    print("=" * 60)
    print("🎉 FIN-L4-PF01 Rex 家庭理财系统 — 端到端运行完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
