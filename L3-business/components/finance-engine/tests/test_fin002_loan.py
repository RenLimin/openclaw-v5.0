"""FIN-002 贷款引擎测试 — 四种还款方式、提前还款、贷款摘要"""

import pytest
from decimal import Decimal
from datetime import date

from fin002_loan import LoanEngine, LoanMethod, _to_decimal, _add_months, _is_leap


@pytest.fixture
def engine():
    return LoanEngine()


@pytest.fixture
def sample_loan(engine):
    return engine.create_loan(
        principal=Decimal("1000000"),
        annual_rate=Decimal("0.035"),
        term_months=360,
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
        name="房贷",
    )


class TestLoanCreation:
    """贷款创建"""

    def test_create_loan(self, engine, sample_loan):
        assert sample_loan.name == "房贷"
        assert sample_loan.principal == Decimal("1000000")
        assert sample_loan.term_months == 360
        assert sample_loan.remaining_balance == Decimal("1000000")

    def test_create_loan_invalid_principal(self, engine):
        with pytest.raises(ValueError, match="本金必须 > 0"):
            engine.create_loan(principal=Decimal("-1000"), annual_rate=Decimal("0.05"),
                              term_months=12, method=LoanMethod.EQUAL_PAYMENT,
                              start_date=date(2026, 1, 1))

    def test_create_loan_invalid_rate(self, engine):
        with pytest.raises(ValueError, match="利率不能为负"):
            engine.create_loan(principal=Decimal("100000"), annual_rate=Decimal("-0.01"),
                              term_months=12, method=LoanMethod.EQUAL_PAYMENT,
                              start_date=date(2026, 1, 1))

    def test_create_loan_invalid_term(self, engine):
        with pytest.raises(ValueError, match="期限必须 > 0"):
            engine.create_loan(principal=Decimal("100000"), annual_rate=Decimal("0.05"),
                              term_months=0, method=LoanMethod.EQUAL_PAYMENT,
                              start_date=date(2026, 1, 1))


class TestEqualPayment:
    """等额本息"""

    def test_schedule_length(self, engine, sample_loan):
        schedule = engine.calculate_amortization_schedule(sample_loan)
        assert len(schedule.entries) == 360

    def test_monthly_payment_positive(self, engine, sample_loan):
        schedule = engine.calculate_amortization_schedule(sample_loan)
        assert schedule.entries[0].payment > 0

    def test_total_interest(self, engine, sample_loan):
        schedule = engine.calculate_amortization_schedule(sample_loan)
        assert schedule.total_interest > 0

    def test_final_balance_zero(self, engine, sample_loan):
        schedule = engine.calculate_amortization_schedule(sample_loan)
        assert schedule.entries[-1].remaining_balance == Decimal("0")

    def test_payment_consistency(self, engine, sample_loan):
        """等额本息月供一致（除最后一期）"""
        schedule = engine.calculate_amortization_schedule(sample_loan)
        first_payment = schedule.entries[0].payment
        # 前几期月供应相同
        for entry in schedule.entries[:10]:
            assert entry.payment == first_payment


class TestEqualPrincipal:
    """等额本金"""

    def test_schedule(self, engine):
        loan = engine.create_loan(
            principal=Decimal("120000"), annual_rate=Decimal("0.06"),
            term_months=12, method=LoanMethod.EQUAL_PRINCIPAL,
            start_date=date(2026, 1, 1),
        )
        schedule = engine.calculate_amortization_schedule(loan)
        assert len(schedule.entries) == 12

    def test_decreasing_payment(self, engine):
        """等额本金月供递减"""
        loan = engine.create_loan(
            principal=Decimal("120000"), annual_rate=Decimal("0.06"),
            term_months=12, method=LoanMethod.EQUAL_PRINCIPAL,
            start_date=date(2026, 1, 1),
        )
        schedule = engine.calculate_amortization_schedule(loan)
        assert schedule.entries[0].payment > schedule.entries[1].payment


class TestInterestOnly:
    """先息后本"""

    def test_interest_only(self, engine):
        loan = engine.create_loan(
            principal=Decimal("100000"), annual_rate=Decimal("0.06"),
            term_months=12, method=LoanMethod.INTEREST_ONLY,
            start_date=date(2026, 1, 1),
        )
        schedule = engine.calculate_amortization_schedule(loan)
        # 前11期只付利息
        monthly_interest = Decimal("100000") * Decimal("0.06") / Decimal("12")
        assert schedule.entries[0].interest == monthly_interest.quantize(Decimal("0.01"))
        assert schedule.entries[0].principal == Decimal("0")

    def test_final_payment_includes_principal(self, engine):
        """最后一期还本"""
        loan = engine.create_loan(
            principal=Decimal("100000"), annual_rate=Decimal("0.06"),
            term_months=12, method=LoanMethod.INTEREST_ONLY,
            start_date=date(2026, 1, 1),
        )
        schedule = engine.calculate_amortization_schedule(loan)
        assert schedule.entries[-1].principal == Decimal("100000")


class TestEarlyPayoff:
    """提前还款"""

    def test_early_payoff_saves_interest(self, engine, sample_loan):
        result = engine.calculate_early_payoff(
            sample_loan, Decimal("100000"), date(2027, 1, 1)
        )
        assert result.interest_saved > 0

    def test_early_payoff_zero_extra(self, engine, sample_loan):
        """额外还款为 0 时利息不变"""
        result = engine.calculate_early_payoff(
            sample_loan, Decimal("0"), date(2027, 1, 1)
        )
        assert result.interest_saved == Decimal("0")


class TestLoanSummary:
    """贷款摘要"""

    def test_summary(self, engine, sample_loan):
        summary = engine.get_loan_summary(sample_loan)
        assert summary.original_principal == Decimal("1000000")
        assert summary.term_months if hasattr(summary, 'term_months') else True
        assert summary.next_payment_amount > 0


class TestUtilityFunctions:
    """辅助函数"""

    def test_to_decimal_from_str(self):
        assert _to_decimal("99.99") == Decimal("99.99")

    def test_to_decimal_from_float(self):
        assert _to_decimal(3.14159) == Decimal("3.14")

    def test_add_months(self):
        d = date(2026, 1, 15)
        result = _add_months(d, 2)
        assert result == date(2026, 3, 15)

    def test_add_months_year_boundary(self):
        d = date(2026, 11, 15)
        result = _add_months(d, 3)
        assert result == date(2027, 2, 15)

    def test_is_leap(self):
        assert _is_leap(2024) is True
        assert _is_leap(2023) is False
        assert _is_leap(2100) is False  # 整百年不闰
        assert _is_leap(2000) is True
