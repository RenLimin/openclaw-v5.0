"""
FIN-006 理财建议引擎测试
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from decimal import Decimal
from fin006_advisor import (
    AdvisorEngine, DebtInfo, DebtStrategy,
    RiskLevel, KPIStatus,
)


def test_health_diagnosis():
    """测试财务健康诊断"""
    engine = AdvisorEngine()
    report = engine.diagnose_financial_health(
        monthly_income=30000,
        monthly_expenses=15000,
        total_assets=Decimal("500000"),
        total_liabilities=Decimal("200000"),
        emergency_fund=Decimal("100000"),
    )

    assert 0 <= report.overall_score <= 100
    assert len(report.kpi_scores) >= 5
    print(f"✅ test_health_diagnosis passed (总分={report.overall_score})")


def test_health_kpi_details():
    """测试 KPI 详情"""
    engine = AdvisorEngine()
    report = engine.diagnose_financial_health(
        monthly_income=30000,
        monthly_expenses=15000,
        total_assets=Decimal("500000"),
        total_liabilities=Decimal("200000"),
        emergency_fund=Decimal("100000"),
        investment_concentration=Decimal("30"),
    )

    # 储蓄率 = 15000/30000 = 50% → GOOD
    savings_kpi = [k for k in report.kpi_scores if k.name == "储蓄率"]
    assert len(savings_kpi) > 0
    assert savings_kpi[0].value == Decimal("50.00")
    assert savings_kpi[0].status == KPIStatus.GOOD

    # 应急储备 = 100000/15000 = 6.67 月 → GOOD
    emergency_kpi = [k for k in report.kpi_scores if k.name == "应急储备(月)"]
    assert len(emergency_kpi) > 0
    assert emergency_kpi[0].status == KPIStatus.GOOD

    print(f"✅ test_health_kpi_details passed")


def test_health_danger():
    """测试危险状态"""
    engine = AdvisorEngine()
    report = engine.diagnose_financial_health(
        monthly_income=10000,
        monthly_expenses=9500,
        total_assets=Decimal("50000"),
        total_liabilities=Decimal("300000"),
        emergency_fund=Decimal("5000"),
    )

    # 储蓄率 = 500/10000 = 5% → DANGER
    savings_kpi = [k for k in report.kpi_scores if k.name == "储蓄率"]
    assert savings_kpi[0].status == KPIStatus.DANGER

    # 应急储备 = 5000/9500 = 0.53 月 → DANGER
    emergency_kpi = [k for k in report.kpi_scores if k.name == "应急储备(月)"]
    assert emergency_kpi[0].status == KPIStatus.DANGER

    assert report.overall_score <= 60
    print(f"✅ test_health_danger passed (总分={report.overall_score})")


def test_asset_allocation_conservative():
    """测试保守型配置"""
    engine = AdvisorEngine()
    advice = engine.suggest_asset_allocation(
        age=55, risk_capacity=2, risk_tolerance=1, investment_horizon=5,
    )

    assert advice.risk_level == RiskLevel.CONSERVATIVE
    assert advice.risk_tolerance_score == 1  # 取较低分
    stock = advice.target_allocation["stock"]
    assert stock <= Decimal("50")
    print(f"✅ test_asset_allocation_conservative passed (股票={stock}%)")


def test_asset_allocation_aggressive():
    """测试积极型配置"""
    engine = AdvisorEngine()
    advice = engine.suggest_asset_allocation(
        age=25, risk_capacity=5, risk_tolerance=4, investment_horizon=30,
    )

    assert advice.risk_level == RiskLevel.AGGRESSIVE
    stock = advice.target_allocation["stock"]
    assert stock >= Decimal("75")
    print(f"✅ test_asset_allocation_aggressive passed (股票={stock}%)")


def test_asset_allocation_age_adjusted():
    """测试年龄调整"""
    engine = AdvisorEngine()
    advice = engine.suggest_asset_allocation(
        age=30, risk_capacity=4, risk_tolerance=4,
    )

    # Rule of 110: 110 - 30 = 80% 股票
    assert advice.age_adjusted_allocation["stock"] == Decimal("80.00")
    assert advice.age_adjusted_allocation["bond"] == Decimal("20.00")
    print(f"✅ test_asset_allocation_age_adjusted passed (股票={advice.age_adjusted_allocation['stock']}%)")


def test_debt_avalanche():
    """测试雪崩法"""
    engine = AdvisorEngine()
    debts = [
        DebtInfo("信用卡", Decimal("50000"), Decimal("0.18"), Decimal("2000")),
        DebtInfo("消费贷", Decimal("30000"), Decimal("0.08"), Decimal("1500")),
        DebtInfo("房贷", Decimal("800000"), Decimal("0.035"), Decimal("4000")),
    ]

    plan = engine.optimize_debt_payoff(debts, Decimal("10000"), "avalanche")

    assert plan.strategy == DebtStrategy.AVALANCHE
    assert plan.total_interest > 0
    assert plan.total_months > 0
    assert "雪崩" in plan.rationale
    print(f"✅ test_debt_avalanche passed ({plan.total_months}月, 利息={plan.total_interest})")


def test_debt_snowball():
    """测试雪球法"""
    engine = AdvisorEngine()
    debts = [
        DebtInfo("信用卡", Decimal("50000"), Decimal("0.18"), Decimal("2000")),
        DebtInfo("消费贷", Decimal("30000"), Decimal("0.08"), Decimal("1500")),
        DebtInfo("房贷", Decimal("800000"), Decimal("0.035"), Decimal("4000")),
    ]

    plan = engine.optimize_debt_payoff(debts, Decimal("10000"), "snowball")

    assert plan.strategy == DebtStrategy.SNOWBALL
    assert "雪球" in plan.rationale
    print(f"✅ test_debt_snowball passed ({plan.total_months}月, 利息={plan.total_interest})")


def test_insurance_gap():
    """测试保障缺口"""
    engine = AdvisorEngine()
    gap = engine.analyze_insurance_gap(
        annual_income=Decimal("360000"),
        total_liabilities=Decimal("800000"),
        liquid_assets=Decimal("200000"),
        existing_life_coverage=Decimal("100000"),
        existing_ci_coverage=Decimal("0"),
        has_medical=False,
        dependents=2,
    )

    # 寿险缺口 = 360000×10 + 800000 - 200000 - 100000 = 4,300,000
    assert gap.life_gap == Decimal("4100000.00")

    # 重疾缺口 = 360000×3 + 300000 - 0 = 1,380,000
    assert gap.ci_gap == Decimal("1380000.00")

    # 医疗缺口 = 300000（无医疗险）
    assert gap.medical_gap == Decimal("300000")

    # 保费预算 = 360000×10% = 36000
    assert gap.total_premium_budget == Decimal("36000.00")

    assert len(gap.recommendations) > 0
    print(f"✅ test_insurance_gap passed (寿险缺口={gap.life_gap}, 重疾缺口={gap.ci_gap})")


def test_insurance_no_gap():
    """测试无缺口"""
    engine = AdvisorEngine()
    gap = engine.analyze_insurance_gap(
        annual_income=Decimal("360000"),
        total_liabilities=Decimal("0"),
        liquid_assets=Decimal("5000000"),
        existing_life_coverage=Decimal("5000000"),
        existing_ci_coverage=Decimal("2000000"),
        has_medical=True,
    )

    # 流动资产充足，寿险缺口可能为 0
    assert gap.life_gap >= Decimal("0")
    assert gap.medical_gap == Decimal("0")
    print(f"✅ test_insurance_no_gap passed")


def test_comprehensive_report():
    """测试综合报告"""
    engine = AdvisorEngine()
    debts = [
        DebtInfo("信用卡", Decimal("20000"), Decimal("0.18"), Decimal("1000")),
    ]

    report = engine.generate_financial_report(
        monthly_income=30000,
        monthly_expenses=15000,
        total_assets=Decimal("500000"),
        total_liabilities=Decimal("200000"),
        emergency_fund=Decimal("100000"),
        debts=debts,
        monthly_budget=Decimal("5000"),
        age=30,
        risk_capacity=3,
        risk_tolerance=4,
        investment_concentration=Decimal("25"),
    )

    assert 0 <= report.health_score <= 100
    assert report.allocation_advice is not None
    assert report.debt_plan is not None
    assert report.insurance_gap is not None
    assert len(report.summary) > 0
    print(f"✅ test_comprehensive_report passed (健康={report.health_score}, 风险={report.allocation_advice.risk_level.value})")


def test_allocation_moderate():
    """测试稳健型配置"""
    engine = AdvisorEngine()
    advice = engine.suggest_asset_allocation(age=40, risk_capacity=3, risk_tolerance=3)

    assert advice.risk_level == RiskLevel.MODERATE
    stock = advice.target_allocation["stock"]
    assert Decimal("55") <= stock <= Decimal("70")
    print(f"✅ test_allocation_moderate passed (股票={stock}%)")


if __name__ == "__main__":
    test_health_diagnosis()
    test_health_kpi_details()
    test_health_danger()
    test_asset_allocation_conservative()
    test_asset_allocation_aggressive()
    test_asset_allocation_age_adjusted()
    test_debt_avalanche()
    test_debt_snowball()
    test_insurance_gap()
    test_insurance_no_gap()
    test_comprehensive_report()
    test_allocation_moderate()
    print("\n🎉 FIN-006 全部测试通过!")
