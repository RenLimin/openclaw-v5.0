"""
FIN-002 贷款/借款核算 — 债务摊销引擎

支持 4 种还款方式 + 提前还款测算。
纯函数式设计，不持有状态。
"""

from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple
from datetime import date, timedelta
import math
import uuid


class LoanMethod(Enum):
    """还款方式"""
    EQUAL_PAYMENT = "equal_payment"       # 等额本息
    EQUAL_PRINCIPAL = "equal_principal"   # 等额本金
    INTEREST_ONLY = "interest_only"       # 先息后本
    FLEXIBLE = "flexible"                 # 随借随还


class LoanStatus(Enum):
    """贷款状态"""
    ACTIVE = "active"
    PAID_OFF = "paid_off"
    DEFAULTED = "defaulted"


@dataclass
class Loan:
    """贷款"""
    id: str
    name: str
    principal: Decimal
    annual_rate: Decimal       # 年利率（如 0.035 表示 3.5%）
    term_months: int
    method: LoanMethod
    start_date: date
    remaining_balance: Decimal = Decimal("0")
    status: LoanStatus = LoanStatus.ACTIVE
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.principal, (int, float, str)):
            self.principal = _to_decimal(self.principal)
        if isinstance(self.annual_rate, (int, float, str)):
            # 利率保持高精度，不 quantize
            self.annual_rate = Decimal(str(self.annual_rate))
        if isinstance(self.remaining_balance, (int, float, str)):
            self.remaining_balance = _to_decimal(self.remaining_balance)
        if self.remaining_balance == 0:
            self.remaining_balance = self.principal


@dataclass
class AmortizationEntry:
    """摊销明细（一期）"""
    period: int                 # 期数（1-based）
    payment_date: date          # 还款日
    payment: Decimal            # 月供
    principal: Decimal          # 本金部分
    interest: Decimal           # 利息部分
    remaining_balance: Decimal  # 剩余本金
    cumulative_interest: Decimal  # 累计利息


@dataclass
class AmortizationSchedule:
    """摊销计划"""
    loan_id: str
    entries: List[AmortizationEntry]
    total_payment: Decimal
    total_interest: Decimal
    generated_at: date = field(default_factory=date.today)


@dataclass
class EarlyPayoffResult:
    """提前还款结果"""
    original_total_interest: Decimal
    new_total_interest: Decimal
    interest_saved: Decimal
    new_schedule: Optional[AmortizationSchedule]
    break_even_months: Optional[int]  # 回本月数（如有手续费）


@dataclass
class LoanSummary:
    """贷款摘要"""
    loan_id: str
    loan_name: str
    original_principal: Decimal
    remaining_balance: Decimal
    total_paid: Decimal
    total_interest_paid: Decimal
    paid_periods: int
    remaining_periods: int
    next_payment_date: Optional[date]
    next_payment_amount: Decimal
    status: LoanStatus


# ========== 核心引擎 ==========

class LoanEngine:
    """贷款核算引擎"""

    def create_loan(
        self,
        principal,
        annual_rate,
        term_months: int,
        method: LoanMethod,
        start_date: date,
        name: str = "",
        loan_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Loan:
        """创建贷款"""
        principal = _to_decimal(principal)
        # 利率保持高精度
        annual_rate = Decimal(str(annual_rate)) if not isinstance(annual_rate, Decimal) else annual_rate

        if principal <= 0:
            raise ValueError(f"本金必须 > 0，收到: {principal}")
        if annual_rate < 0:
            raise ValueError(f"利率不能为负: {annual_rate}")
        if term_months <= 0:
            raise ValueError(f"期限必须 > 0，收到: {term_months}")

        return Loan(
            id=loan_id or f"LOAN-{uuid.uuid4().hex[:8].upper()}",
            name=name,
            principal=principal,
            annual_rate=annual_rate,
            term_months=term_months,
            method=method,
            start_date=start_date,
            remaining_balance=principal,
            metadata=metadata or {},
        )

    def calculate_amortization_schedule(
        self,
        loan: Loan,
        extra_payments: Optional[dict] = None,  # {period: extra_amount}
    ) -> AmortizationSchedule:
        """
        计算摊销计划

        extra_payments: 额外还款字典 {期数: 金额}
        """
        method_map = {
            LoanMethod.EQUAL_PAYMENT: self._calc_equal_payment,
            LoanMethod.EQUAL_PRINCIPAL: self._calc_equal_principal,
            LoanMethod.INTEREST_ONLY: self._calc_interest_only,
            LoanMethod.FLEXIBLE: self._calc_flexible,
        }

        calc_fn = method_map.get(loan.method)
        if not calc_fn:
            raise ValueError(f"不支持的还款方式: {loan.method}")

        return calc_fn(loan, extra_payments or {})

    def _calc_equal_payment(self, loan: Loan, extra_payments: dict) -> AmortizationSchedule:
        """
        等额本息

        公式: M = P × [i(1+i)^n] / [(1+i)^n - 1]
        """
        P = loan.principal
        i = loan.annual_rate / Decimal("12")  # 月利率
        n = loan.term_months

        entries = []
        remaining = P
        cumulative_interest = Decimal("0")

        if i == 0:
            # 零利率
            monthly_payment = (P / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for period in range(1, n + 1):
                principal_part = monthly_payment
                interest_part = Decimal("0")
                remaining -= principal_part
                if period == n:
                    principal_part += remaining
                    remaining = Decimal("0")
                cumulative_interest += interest_part
                entries.append(AmortizationEntry(
                    period=period,
                    payment_date=_add_months(loan.start_date, period),
                    payment=monthly_payment,
                    principal=principal_part.quantize(Decimal("0.01")),
                    interest=interest_part.quantize(Decimal("0.01")),
                    remaining_balance=remaining.quantize(Decimal("0.01")),
                    cumulative_interest=cumulative_interest.quantize(Decimal("0.01")),
                ))
        else:
            # PMT 公式: M = P * [i(1+i)^n] / [(1+i)^n - 1]
            # 使用 Decimal 高精度计算
            one_plus_i = Decimal("1") + i
            one_plus_i_n = one_plus_i ** n
            pmt = P * (i * one_plus_i_n) / (one_plus_i_n - Decimal("1"))
            monthly_payment = pmt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            for period in range(1, n + 1):
                interest_part = (remaining * i).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                principal_part = monthly_payment - interest_part

                # 额外还款
                extra = _to_decimal(extra_payments.get(period, 0))
                principal_part += extra

                # 修正：不超过剩余本金
                if principal_part > remaining:
                    principal_part = remaining

                remaining -= principal_part
                cumulative_interest += interest_part

                payment = monthly_payment + extra

                # 最后一期修正尾差
                if period == n or remaining <= 0:
                    principal_part = principal_part + remaining
                    remaining = Decimal("0")
                    payment = principal_part + interest_part

                entries.append(AmortizationEntry(
                    period=period,
                    payment_date=_add_months(loan.start_date, period),
                    payment=payment.quantize(Decimal("0.01")),
                    principal=principal_part.quantize(Decimal("0.01")),
                    interest=interest_part.quantize(Decimal("0.01")),
                    remaining_balance=remaining.quantize(Decimal("0.01")),
                    cumulative_interest=cumulative_interest.quantize(Decimal("0.01")),
                ))

                if remaining <= 0:
                    break

        total_payment = sum(e.payment for e in entries)
        total_interest = cumulative_interest

        return AmortizationSchedule(
            loan_id=loan.id,
            entries=entries,
            total_payment=total_payment.quantize(Decimal("0.01")),
            total_interest=total_interest.quantize(Decimal("0.01")),
        )

    def _calc_equal_principal(self, loan: Loan, extra_payments: dict) -> AmortizationSchedule:
        """
        等额本金

        每月本金 = P / n
        第 k 月利息 = (P - P*(k-1)/n) × i
        """
        P = loan.principal
        i = loan.annual_rate / Decimal("12")
        n = loan.term_months
        monthly_principal = (P / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        entries = []
        remaining = P
        cumulative_interest = Decimal("0")

        for period in range(1, n + 1):
            interest_part = (remaining * i).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            principal_part = monthly_principal

            extra = _to_decimal(extra_payments.get(period, 0))
            principal_part += extra

            if principal_part > remaining:
                principal_part = remaining

            remaining -= principal_part
            cumulative_interest += interest_part
            payment = principal_part + interest_part

            entries.append(AmortizationEntry(
                period=period,
                payment_date=_add_months(loan.start_date, period),
                payment=payment.quantize(Decimal("0.01")),
                principal=principal_part.quantize(Decimal("0.01")),
                interest=interest_part.quantize(Decimal("0.01")),
                remaining_balance=remaining.quantize(Decimal("0.01")),
                cumulative_interest=cumulative_interest.quantize(Decimal("0.01")),
            ))

            if remaining <= 0:
                break

        total_payment = sum(e.payment for e in entries)

        return AmortizationSchedule(
            loan_id=loan.id,
            entries=entries,
            total_payment=total_payment.quantize(Decimal("0.01")),
            total_interest=cumulative_interest.quantize(Decimal("0.01")),
        )

    def _calc_interest_only(self, loan: Loan, extra_payments: dict) -> AmortizationSchedule:
        """
        先息后本

        每月利息 = P × i
        最后一期 = P + P × i
        """
        P = loan.principal
        i = loan.annual_rate / Decimal("12")
        n = loan.term_months

        entries = []
        remaining = P
        cumulative_interest = Decimal("0")
        monthly_interest = (P * i).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        for period in range(1, n + 1):
            interest_part = monthly_interest
            principal_part = Decimal("0")

            if period == n:
                # 最后一期还本
                principal_part = P
                # 额外还款
                extra = _to_decimal(extra_payments.get(period, 0))
                principal_part += extra
                if principal_part > remaining:
                    principal_part = remaining
                remaining -= principal_part
            else:
                extra = _to_decimal(extra_payments.get(period, 0))
                principal_part = extra
                remaining -= principal_part

            cumulative_interest += interest_part
            payment = principal_part + interest_part

            entries.append(AmortizationEntry(
                period=period,
                payment_date=_add_months(loan.start_date, period),
                payment=payment.quantize(Decimal("0.01")),
                principal=principal_part.quantize(Decimal("0.01")),
                interest=interest_part.quantize(Decimal("0.01")),
                remaining_balance=remaining.quantize(Decimal("0.01")),
                cumulative_interest=cumulative_interest.quantize(Decimal("0.01")),
            ))

            if remaining <= 0:
                break

        total_payment = sum(e.payment for e in entries)

        return AmortizationSchedule(
            loan_id=loan.id,
            entries=entries,
            total_payment=total_payment.quantize(Decimal("0.01")),
            total_interest=cumulative_interest.quantize(Decimal("0.01")),
        )

    def _calc_flexible(self, loan: Loan, extra_payments: dict) -> AmortizationSchedule:
        """
        随借随还（按日计息）

        简化模型：假设每月按 30 天计息
        利息 = 本金 × 日利率 × 天数
        """
        P = loan.principal
        daily_rate = loan.annual_rate / Decimal("365")
        n = loan.term_months

        entries = []
        remaining = P
        cumulative_interest = Decimal("0")

        for period in range(1, n + 1):
            # 按 30 天计息
            interest_part = (remaining * daily_rate * Decimal("30")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            principal_part = Decimal("0")

            if period == n:
                principal_part = remaining  # 最后一期还清
            else:
                # 额外还款 = 提前还本
                extra = _to_decimal(extra_payments.get(period, 0))
                principal_part = extra

            if principal_part > remaining:
                principal_part = remaining

            remaining -= principal_part
            cumulative_interest += interest_part
            payment = principal_part + interest_part

            entries.append(AmortizationEntry(
                period=period,
                payment_date=_add_months(loan.start_date, period),
                payment=payment.quantize(Decimal("0.01")),
                principal=principal_part.quantize(Decimal("0.01")),
                interest=interest_part.quantize(Decimal("0.01")),
                remaining_balance=remaining.quantize(Decimal("0.01")),
                cumulative_interest=cumulative_interest.quantize(Decimal("0.01")),
            ))

            if remaining <= 0:
                break

        total_payment = sum(e.payment for e in entries)

        return AmortizationSchedule(
            loan_id=loan.id,
            entries=entries,
            total_payment=total_payment.quantize(Decimal("0.01")),
            total_interest=cumulative_interest.quantize(Decimal("0.01")),
        )

    # ---------- 提前还款 ----------

    def calculate_early_payoff(
        self,
        loan: Loan,
        extra_payment,
        payment_date: date,
        fee_rate: Decimal = Decimal("0"),  # 提前还款手续费率
    ) -> EarlyPayoffResult:
        """
        计算提前还款效果

        extra_payment: 额外还款金额
        payment_date: 提前还款日期
        fee_rate: 提前还款手续费率（如 0.01 表示 1%）
        """
        extra_payment = _to_decimal(extra_payment)
        fee_rate = _to_decimal(fee_rate)

        # 原计划
        original_schedule = self.calculate_amortization_schedule(loan)
        original_interest = original_schedule.total_interest

        # 计算已还期数
        months_paid = _months_between(loan.start_date, payment_date)

        # 计算提前还款时的剩余本金
        remaining_at_payoff = loan.principal
        for entry in original_schedule.entries:
            if entry.period <= months_paid:
                remaining_at_payoff -= entry.principal

        if remaining_at_payoff <= 0:
            return EarlyPayoffResult(
                original_total_interest=original_interest,
                new_total_interest=original_interest,
                interest_saved=Decimal("0"),
                new_schedule=original_schedule,
                break_even_months=0,
            )

        # 手续费
        fee = (extra_payment * fee_rate).quantize(Decimal("0.01"))

        # 新剩余本金
        new_remaining = remaining_at_payoff - extra_payment
        if new_remaining < 0:
            new_remaining = Decimal("0")
            extra_payment = remaining_at_payoff

        # 新贷款（剩余期限）
        remaining_months = loan.term_months - months_paid
        if remaining_months <= 0 or new_remaining <= 0:
            new_schedule = AmortizationSchedule(
                loan_id=loan.id,
                entries=[], total_payment=Decimal("0"), total_interest=Decimal("0"))
            new_interest = Decimal("0")
        else:
            new_loan = Loan(
                id=f"{loan.id}-REFI",
                name=f"{loan.name} (提前还款后)",
                principal=new_remaining,
                annual_rate=loan.annual_rate,
                term_months=remaining_months,
                method=loan.method,
                start_date=payment_date,
            )
            new_schedule = self.calculate_amortization_schedule(new_loan)
            new_interest = new_schedule.total_interest

        # 已付利息
        paid_interest = sum(
            e.interest for e in original_schedule.entries if e.period <= months_paid
        )

        total_new_interest = paid_interest + new_interest
        interest_saved = original_interest - total_new_interest

        # 回本月数
        break_even = None
        if fee > 0 and interest_saved > 0:
            monthly_saving = interest_saved / Decimal(str(max(remaining_months, 1)))
            if monthly_saving > 0:
                break_even = int((fee / monthly_saving).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        return EarlyPayoffResult(
            original_total_interest=original_interest,
            new_total_interest=total_new_interest.quantize(Decimal("0.01")),
            interest_saved=interest_saved.quantize(Decimal("0.01")),
            new_schedule=new_schedule,
            break_even_months=break_even,
        )

    # ---------- 贷款摘要 ----------

    def get_loan_summary(self, loan: Loan, as_of_date: Optional[date] = None) -> LoanSummary:
        """获取贷款摘要"""
        schedule = self.calculate_amortization_schedule(loan)
        as_of = as_of_date or date.today()

        # 计算已还期数
        paid_periods = 0
        total_paid = Decimal("0")
        total_interest_paid = Decimal("0")

        for entry in schedule.entries:
            if entry.payment_date <= as_of:
                paid_periods += 1
                total_paid += entry.payment
                total_interest_paid += entry.interest

        remaining_periods = loan.term_months - paid_periods
        next_payment = None
        next_amount = Decimal("0")

        for entry in schedule.entries:
            if entry.payment_date > as_of:
                next_payment = entry.payment_date
                next_amount = entry.payment
                break

        # 剩余本金
        remaining_balance = loan.principal
        for entry in schedule.entries:
            if entry.period <= paid_periods:
                remaining_balance -= entry.principal

        return LoanSummary(
            loan_id=loan.id,
            loan_name=loan.name,
            original_principal=loan.principal,
            remaining_balance=remaining_balance.quantize(Decimal("0.01")),
            total_paid=total_paid.quantize(Decimal("0.01")),
            total_interest_paid=total_interest_paid.quantize(Decimal("0.01")),
            paid_periods=paid_periods,
            remaining_periods=max(remaining_periods, 0),
            next_payment_date=next_payment,
            next_payment_amount=next_amount.quantize(Decimal("0.01")),
            status=loan.status,
        )


# ========== 辅助函数 ==========

def _to_decimal(value) -> Decimal:
    """转换为 Decimal"""
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _add_months(d: date, months: int) -> date:
    """日期加月份"""
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    day = min(d.day, [31, 29 if _is_leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _is_leap(year: int) -> bool:
    """闰年"""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def _months_between(start: date, end: date) -> int:
    """计算月份差"""
    if end < start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month)
