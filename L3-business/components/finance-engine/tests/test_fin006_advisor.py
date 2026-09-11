"""FIN-006 理财建议引擎测试 — 财务健康诊断、资产配置建议、债务优化、保障缺口"""

import pytest
from decimal import Decimal

from fin006_advisor import (
    AdvisorEngine, RiskLevel, KPIStatus, DebtStrategy,
    DebtInfo, _to_decimal,
)


@pytest.fixture
def engine():
    return AdvisorEngine()


class TestFinancialHealthDiagnosis:
    """财务健康诊断"""

    def test_healthy_financials(self, engine):
        report = engine.diagnose_financial_health(
            monthly_income=Decimal("30000"),
            monthly_expenses=Decimal("15000"),
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("100000"),
            emergency_fund=Decimal("100000"),
        )
        assert report.overall_score > 0
        assert len(report.kpi_scores) > 0

    def test_savings_rate_calculation(self, engine):
        """储蓄率计算: (30000 - 15000) / 30000 * 100 = 50%"""
        report = engine.diagnose_financial_health(
            monthly_income=Decimal("30000"),
            monthly_expenses=Decimal("15000"),
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("100000"),
            emergency_fund=Decimal("100000"),
        )
        savings_kpi = [k for k in report.kpi_scores if k.name == "储蓄率"]
        assert len(savings_kpi) == 1
        assert savings_kpi[0].value == Decimal("50.00")

    def test_danger_low_savings(self, engine):
        """储蓄率过低应为 DANGER"""
        report = engine.diagnose_financial_health(
            monthly_income=Decimal("10000"),
            monthly_expenses=Decimal("9500"),
            total_assets=Decimal("10000"),
            total_liabilities=Decimal("0"),
            emergency_fund=Decimal("5000"),
        )
        savings_kpi = [k for k in report.kpi_scores if k.name == "储蓄率"]
        assert savings_kpi[0].status == KPIStatus.DANGER

    def test_strengths_and_weaknesses(self, engine):
        report = engine.diagnose_financial_health(
            monthly_income=Decimal("30000"),
            monthly_expenses=Decimal("10000"),
            total_assets=Decimal("1000000"),
            total_liabilities=Decimal("50000"),
            emergency_fund=Decimal("200000"),
        )
        assert len(report.strengths) > 0


class TestAssetAllocationAdvice:
    """资产配置建议"""

    def test_conservative_allocation(self, engine):
        result = engine.suggest_asset_allocation(age=60, risk_capacity=1, risk_tolerance=2)
        assert result.risk_level == RiskLevel.CONSERVATIVE

    def test_moderate_allocation(self, engine):
        result = engine.suggest_asset_allocation(age=40, risk_capacity=3, risk_tolerance=3)
        assert result.risk_level == RiskLevel.MODERATE

    def test_aggressive_allocation(self, engine):
        result = engine.suggest_asset_allocation(age=25, risk_capacity=5, risk_tolerance=5)
        assert result.risk_level == RiskLevel.AGGRESSIVE

    def test_effective_score_takes_minimum(self, engine):
        """取风险能力和风险承受度的较低分"""
        result = engine.suggest_asset_allocation(age=30, risk_capacity=2, risk_tolerance=5)
        # effective_score = min(2, 5) = 2 → conservative
        assert result.risk_level == RiskLevel.CONSERVATIVE

    def test_age_adjusted_allocation(self, engine):
        """Rule of 110 年龄调整"""
        result = engine.suggest_asset_allocation(age=30, risk_capacity=4, risk_tolerance=4)
        assert result.age_adjusted_allocation["stock"] == Decimal("80.00")

    def test_target_allocation_sum(self, engine):
        result = engine.suggest_asset_allocation(age=35, risk_capacity=3, risk_tolerance=3)
        total = sum(result.target_allocation.values())
        # 四类资产之和应接近 100
        assert Decimal("95") <= total <= Decimal("105")


class TestDebtOptimization:
    """债务优化"""

    def test_avalanche_strategy(self, engine):
        debts = [
            DebtInfo("信用卡", Decimal("10000"), Decimal("0.18"), Decimal("200")),
            DebtInfo("车贷", Decimal("50000"), Decimal("0.05"), Decimal("1000")),
        ]
        plan = engine.optimize_debt_payoff(debts, Decimal("2000"), "avalanche")
        assert plan.strategy == DebtStrategy.AVALANCHE

    def test_snowball_strategy(self, engine):
        debts = [
            DebtInfo("信用卡", Decimal("10000"), Decimal("0.18"), Decimal("200")),
            DebtInfo("车贷", Decimal("50000"), Decimal("0.05"), Decimal("1000")),
        ]
        plan = engine.optimize_debt_payoff(debts, Decimal("2000"), "snowball")
        assert plan.strategy == DebtStrategy.SNOWBALL

    def test_no_debts(self, engine):
        plan = engine.optimize_debt_payoff([], Decimal("2000"))
        assert plan.total_months == 0
        assert plan.schedule == []


class TestInsuranceGap:
    """保障缺口分析"""

    def test_life_gap(self, engine):
        gap = engine.analyze_insurance_gap(
            annual_income=Decimal("360000"),
            total_liabilities=Decimal("1000000"),
            liquid_assets=Decimal("200000"),
            existing_life_coverage=Decimal("0"),
        )
        # 寿险需求 = 360000 * 10 + 1000000 - 200000 = 3800000
        assert gap.life_gap > 0

    def test_ci_gap(self, engine):
        gap = engine.analyze_insurance_gap(
            annual_income=Decimal("360000"),
            total_liabilities=Decimal("0"),
            liquid_assets=Decimal("0"),
            existing_ci_coverage=Decimal("0"),
        )
        # 重疾需求 = 360000 * 3 + 300000 = 1380000
        assert gap.ci_gap > 0

    def test_medical_gap_no_coverage(self, engine):
        gap = engine.analyze_insurance_gap(
            annual_income=Decimal("360000"),
            total_liabilities=Decimal("0"),
            liquid_assets=Decimal("0"),
            has_medical=False,
        )
        assert gap.medical_gap == Decimal("300000")

    def test_medical_gap_with_coverage(self, engine):
        gap = engine.analyze_insurance_gap(
            annual_income=Decimal("360000"),
            total_liabilities=Decimal("0"),
            liquid_assets=Decimal("0"),
            has_medical=True,
        )
        assert gap.medical_gap == Decimal("0")

    def test_premium_budget(self, engine):
        gap = engine.analyze_insurance_gap(
            annual_income=Decimal("360000"),
            total_liabilities=Decimal("0"),
            liquid_assets=Decimal("0"),
        )
        # 保费预算 = 年收入 * 10% = 36000
        assert gap.total_premium_budget == Decimal("36000.00")


class TestFinancialReport:
    """综合理财报告"""

    def test_generate_report(self, engine):
        report = engine.generate_financial_report(
            monthly_income=Decimal("30000"),
            monthly_expenses=Decimal("15000"),
            total_assets=Decimal("500000"),
            total_liabilities=Decimal("100000"),
            emergency_fund=Decimal("100000"),
            age=35,
            risk_capacity=3,
            risk_tolerance=4,
        )
        assert report.health_score > 0
        assert report.allocation_advice is not None
        assert report.insurance_gap is not None
        assert len(report.summary) > 0


class TestToDecimal:
    """_to_decimal 辅助函数"""

    def test_from_str(self):
        assert _to_decimal("99.99") == Decimal("99.99")

    def test_from_float(self):
        assert _to_decimal(3.14159) == Decimal("3.14")
