"""
FIN-002 贷款/借款核算测试
"""
import sys
sys.path.insert(0, '..')

from decimal import Decimal
from datetime import date
from fin002_loan import (
    LoanEngine, LoanMethod, LoanStatus,
    _to_decimal, _add_months,
)


def test_equal_payment():
    """测试等额本息"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=1000000,          # 100万
        annual_rate=0.035,          # 3.5%
        term_months=360,            # 30年
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
        name="房贷",
    )

    schedule = engine.calculate_amortization_schedule(loan)

    # 验证：月供 ≈ 4490.45（标准 PMT 公式）
    first_payment = schedule.entries[0].payment
    assert first_payment == Decimal("4490.45"), f"月供错误: {first_payment}"

    # 验证：总利息 > 0
    assert schedule.total_interest > 0
    print(f"✅ test_equal_payment passed (月供={first_payment}, 总利息={schedule.total_interest})")


def test_equal_payment_zero_rate():
    """测试零利率等额本息"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=120000,
        annual_rate=0,
        term_months=12,
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
    )

    schedule = engine.calculate_amortization_schedule(loan)
    assert schedule.entries[0].payment == Decimal("10000.00")
    assert schedule.total_interest == Decimal("0.00")
    print("✅ test_equal_payment_zero_rate passed")


def test_equal_principal():
    """测试等额本金"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=120000,
        annual_rate=0.06,
        term_months=12,
        method=LoanMethod.EQUAL_PRINCIPAL,
        start_date=date(2026, 1, 1),
    )

    schedule = engine.calculate_amortization_schedule(loan)

    # 每月本金 = 10000
    assert schedule.entries[0].principal == Decimal("10000.00")

    # 月供递减
    assert schedule.entries[0].payment > schedule.entries[1].payment

    # 总利息 < 等额本息
    ep_loan = engine.create_loan(
        principal=120000, annual_rate=0.06, term_months=12,
        method=LoanMethod.EQUAL_PAYMENT, start_date=date(2026, 1, 1),
    )
    ep_schedule = engine.calculate_amortization_schedule(ep_loan)
    assert schedule.total_interest < ep_schedule.total_interest
    print(f"✅ test_equal_principal passed (总利息={schedule.total_interest} < 等额本息={ep_schedule.total_interest})")


def test_interest_only():
    """测试先息后本"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=100000,
        annual_rate=0.06,
        term_months=12,
        method=LoanMethod.INTEREST_ONLY,
        start_date=date(2026, 1, 1),
    )

    schedule = engine.calculate_amortization_schedule(loan)

    # 前11期只还利息 = 500
    for i in range(11):
        assert schedule.entries[i].interest == Decimal("500.00")
        assert schedule.entries[i].principal == Decimal("0.00")

    # 最后一期还本+利息
    assert schedule.entries[11].principal == Decimal("100000.00")
    assert schedule.entries[11].interest == Decimal("500.00")

    print("✅ test_interest_only passed")


def test_flexible():
    """测试随借随还"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=100000,
        annual_rate=0.06,
        term_months=12,
        method=LoanMethod.FLEXIBLE,
        start_date=date(2026, 1, 1),
    )

    schedule = engine.calculate_amortization_schedule(loan)

    # 前11期只还利息
    for i in range(11):
        assert schedule.entries[i].principal == Decimal("0.00")

    # 最后一期还清
    assert schedule.entries[11].principal == Decimal("100000.00")
    print("✅ test_flexible passed")


def test_early_payoff():
    """测试提前还款"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=1000000,
        annual_rate=0.035,
        term_months=360,
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
        name="房贷",
    )

    # 第12期提前还20万
    result = engine.calculate_early_payoff(
        loan=loan,
        extra_payment=200000,
        payment_date=date(2027, 1, 1),
    )

    assert result.interest_saved > 0, f"应节省利息: {result.interest_saved}"
    assert result.new_total_interest < result.original_total_interest
    print(f"✅ test_early_payoff passed (节省利息={result.interest_saved})")


def test_early_payoff_with_fee():
    """测试有手续费的提前还款"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=1000000,
        annual_rate=0.035,
        term_months=360,
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
    )

    result = engine.calculate_early_payoff(
        loan=loan,
        extra_payment=200000,
        payment_date=date(2027, 1, 1),
        fee_rate=0.01,  # 1% 手续费
    )

    assert result.break_even_months is not None
    assert result.break_even_months > 0
    print(f"✅ test_early_payoff_with_fee passed (回本={result.break_even_months}月)")


def test_loan_summary():
    """测试贷款摘要"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=500000,
        annual_rate=0.04,
        term_months=240,
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
        name="经营贷",
    )

    summary = engine.get_loan_summary(loan, as_of_date=date(2026, 6, 1))

    assert summary.loan_name == "经营贷"
    assert summary.original_principal == Decimal("500000.00")
    assert summary.paid_periods == 5
    assert summary.remaining_periods == 235
    assert summary.next_payment_date is not None
    print(f"✅ test_loan_summary passed (已还={summary.paid_periods}期, 剩余={summary.remaining_periods}期)")


def test_amortization_schedule_total():
    """验证摊销计划总额"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=100000,
        annual_rate=0.05,
        term_months=60,
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
    )

    schedule = engine.calculate_amortization_schedule(loan)

    # 月供 × 期数 ≈ 总还款
    total_from_entries = sum(e.payment for e in schedule.entries)
    assert total_from_entries == schedule.total_payment

    # 总还款 - 本金 = 总利息
    assert schedule.total_payment - loan.principal == schedule.total_interest

    # 最后一期剩余本金 = 0
    assert schedule.entries[-1].remaining_balance == Decimal("0.00")

    print(f"✅ test_amortization_schedule_total passed (总还款={schedule.total_payment}, 总利息={schedule.total_interest})")


def test_extra_payments():
    """测试额外还款"""
    engine = LoanEngine()
    loan = engine.create_loan(
        principal=100000,
        annual_rate=0.06,
        term_months=60,
        method=LoanMethod.EQUAL_PAYMENT,
        start_date=date(2026, 1, 1),
    )

    # 无额外还款
    base_schedule = engine.calculate_amortization_schedule(loan)

    # 第12期额外还2万
    extra_schedule = engine.calculate_amortization_schedule(
        loan, extra_payments={12: 20000}
    )

    # 额外还款应缩短期限或减少利息
    assert extra_schedule.total_interest <= base_schedule.total_interest
    print(f"✅ test_extra_payments passed (基础利息={base_schedule.total_interest}, 额外还款后={extra_schedule.total_interest})")


if __name__ == "__main__":
    test_equal_payment()
    test_equal_payment_zero_rate()
    test_equal_principal()
    test_interest_only()
    test_flexible()
    test_early_payoff()
    test_early_payoff_with_fee()
    test_loan_summary()
    test_amortization_schedule_total()
    test_extra_payments()
    print("\n🎉 FIN-002 全部测试通过!")
