"""
FIN-003 保险产品核算引擎

支持险种:
- 定期寿险 (term_life): 纯保障，无现金价值
- 终身寿险 (whole_life): 终身保障 + 储蓄
- 两全保险 (endowment): 生存/身故都赔
- 重疾险 (critical_illness): 含轻症/中症
- 医疗险 (medical): 消费型
- 年金险 (annuity): 定期领取
- 万能险 (universal_life): 保底 + 结算利率
- 税延养老险 (tax_deferred): A/B/C 三类

核心计算:
- 现金价值 (cash_value)
- 退保价值 (surrender_value)
- 内部收益率 (IRR, 牛顿迭代法)
- 红利演示 (三档: 低/中/高)
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional, Dict
from datetime import date, datetime
import uuid


# ========== 常量 ==========

# 红利演示三档利率
DIVIDEND_RATES = {
    "low": Decimal("0.025"),     # 低档 2.5%
    "mid": Decimal("0.045"),      # 中档 4.5%
    "high": Decimal("0.060"),     # 高档 6.0%
}

# 退保手续费率（按保单年度）
SURRENDER_FEE_RATES = {
    1: Decimal("0.05"),   # 首年 5%
    2: Decimal("0.04"),
    3: Decimal("0.03"),
    4: Decimal("0.02"),
    5: Decimal("0.01"),
}

# IRR 迭代参数
IRR_MAX_ITERATIONS = 200
IRR_CONVERGENCE = Decimal("1e-8")
IRR_INITIAL_GUESS = Decimal("0.03")

# 免责声明
DISCLAIMER = (
    "⚠️ 本计算为估算值，基于标准精算假设。"
    "实际价值以保险公司出具的保单现金价值表为准。"
    "演示红利非保证，实际分红可能低于演示。"
)


# ========== 枚举 ==========

class InsuranceType(Enum):
    """险种类型"""
    TERM_LIFE = "term_life"
    WHOLE_LIFE = "whole_life"
    ENDOWMENT = "endowment"
    CRITICAL_ILLNESS = "critical_illness"
    MEDICAL = "medical"
    ANNUITY = "annuity"
    UNIVERSAL_LIFE = "universal_life"
    TAX_DEFERRED = "tax_deferred"


class PolicyStatus(Enum):
    """保单状态"""
    ACTIVE = "active"
    LAPSED = "lapsed"
    SURRENDERED = "surrendered"
    MATURED = "matured"
    CLAIMED = "claimed"


# 险种能力矩阵
INSURANCE_CAPABILITIES: Dict[InsuranceType, Dict[str, bool]] = {
    InsuranceType.TERM_LIFE:      {"cash_value": False, "surrender": False, "irr": False},
    InsuranceType.WHOLE_LIFE:     {"cash_value": True,  "surrender": True,  "irr": True},
    InsuranceType.ENDOWMENT:      {"cash_value": True,  "surrender": True,  "irr": True},
    InsuranceType.CRITICAL_ILLNESS: {"cash_value": True, "surrender": True, "irr": True},
    InsuranceType.MEDICAL:        {"cash_value": False, "surrender": False, "irr": False},
    InsuranceType.ANNUITY:        {"cash_value": True,  "surrender": True,  "irr": True},
    InsuranceType.UNIVERSAL_LIFE: {"cash_value": True,  "surrender": True,  "irr": True},
    InsuranceType.TAX_DEFERRED:   {"cash_value": True,  "surrender": True,  "irr": True},
}


# ========== 工具函数 ==========

def _to_decimal(value) -> Decimal:
    """转换为 Decimal（金额精度 2 位）"""
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_decimal_raw(value) -> Decimal:
    """转换为 Decimal（保持原始精度，用于利率等）"""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# ========== 数据模型 ==========

@dataclass
class Policy:
    """保单"""
    id: str
    policy_number: str
    policy_type: InsuranceType
    product_name: str
    sum_assured: Decimal        # 保额
    annual_premium: Decimal     # 年保费
    term_years: int             # 保障期限
    payment_years: int          # 缴费期限
    start_date: date
    insured_name: str
    insured_age: int
    insured_gender: str
    status: PolicyStatus
    created_at: datetime
    metadata: dict = field(default_factory=dict)

    @property
    def supports_cash_value(self) -> bool:
        return INSURANCE_CAPABILITIES.get(self.policy_type, {}).get("cash_value", False)

    @property
    def supports_surrender(self) -> bool:
        return INSURANCE_CAPABILITIES.get(self.policy_type, {}).get("surrender", False)

    @property
    def supports_irr(self) -> bool:
        return INSURANCE_CAPABILITIES.get(self.policy_type, {}).get("irr", False)


@dataclass
class CashValueResult:
    """现金价值结果"""
    policy_id: str
    as_of_year: int
    guaranteed_cv: Decimal          # 保证现金价值
    non_guaranteed_cv: Decimal      # 非保证现金价值（中档演示）
    total_cv: Decimal               # 合计
    dividend_details: Dict[str, Decimal] = field(default_factory=dict)  # 各档演示
    is_estimate: bool = True
    disclaimer: str = DISCLAIMER


@dataclass
class SurrenderValueResult:
    """退保价值结果"""
    policy_id: str
    as_of_year: int
    cash_value: Decimal
    surrender_fee: Decimal
    surrender_value: Decimal
    surrender_fee_rate: Decimal
    is_estimate: bool = True
    disclaimer: str = DISCLAIMER


@dataclass
class IRRResult:
    """IRR 结果"""
    policy_id: str
    as_of_year: int
    irr: Decimal
    calculation_method: str
    converged: bool
    iterations: int
    is_estimate: bool = True
    disclaimer: str = DISCLAIMER


@dataclass
class DividendProjection:
    """红利演示结果"""
    policy_id: str
    as_of_year: int
    scenario: str                   # "low" / "mid" / "high"
    dividend_rate: Decimal
    annual_dividend: Decimal        # 当年红利
    cumulative_dividend: Decimal    # 累计红利
    total_cv: Decimal               # 含红利的总现金价值
    is_estimate: bool = True
    disclaimer: str = DISCLAIMER


# ========== 精算参数（简化模型） ==========

# 初始费用率（占保费比例，首年高后续低）
INITIAL_EXPENSE_RATE = {
    1: Decimal("0.50"),     # 首年 50%
    2: Decimal("0.25"),     # 次年 25%
    3: Decimal("0.10"),     # 第 3 年 10%
}

# 后续年份管理费用率
MAINTENANCE_EXPENSE_RATE = Decimal("0.02")  # 2%

# 风险保费率（简化：按保额比例）
RISK_PREMIUM_RATE = {
    InsuranceType.TERM_LIFE:        Decimal("0.001"),    # 0.1%
    InsuranceType.WHOLE_LIFE:       Decimal("0.002"),    # 0.2%
    InsuranceType.ENDOWMENT:        Decimal("0.0015"),   # 0.15%
    InsuranceType.CRITICAL_ILLNESS: Decimal("0.003"),    # 0.3%
    InsuranceType.MEDICAL:          Decimal("0.002"),    # 0.2%
    InsuranceType.ANNUITY:          Decimal("0.001"),    # 0.1%
    InsuranceType.UNIVERSAL_LIFE:   Decimal("0.0015"),   # 0.15%
    InsuranceType.TAX_DEFERRED:     Decimal("0.001"),    # 0.1%
}


# ========== 引擎 ==========

class InsuranceEngine:
    """保险产品核算引擎"""

    def __init__(self):
        self._policies: Dict[str, Policy] = {}

    # ---------- 保单管理 ----------

    def create_policy(
        self,
        policy_type: InsuranceType,
        product_name: str,
        sum_assured,
        annual_premium,
        term_years: int,
        payment_years: int,
        insured_age: int,
        insured_gender: str = "M",
        insured_name: str = "",
        start_date: Optional[date] = None,
        policy_number: str = "",
        metadata: Optional[dict] = None,
    ) -> Policy:
        """创建保单"""
        policy_id = f"POL-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now()

        policy = Policy(
            id=policy_id,
            policy_number=policy_number or policy_id,
            policy_type=policy_type,
            product_name=product_name,
            sum_assured=_to_decimal(sum_assured),
            annual_premium=_to_decimal(annual_premium),
            term_years=term_years,
            payment_years=payment_years,
            start_date=start_date or date.today(),
            insured_name=insured_name or "被保险人",
            insured_age=insured_age,
            insured_gender=insured_gender,
            status=PolicyStatus.ACTIVE,
            created_at=now,
            metadata=metadata or {},
        )
        self._policies[policy_id] = policy
        return policy

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        return self._policies.get(policy_id)

    def get_all_policies(self) -> List[Policy]:
        return list(self._policies.values())

    # ---------- 现金价值 ----------

    def calculate_cash_value(
        self,
        policy_id: str,
        as_of_year: int,
        rate_scenario: str = "mid",
    ) -> CashValueResult:
        """
        计算现金价值

        CV(t) = Σ[k=1 to min(t, payment_years)] (premium_k - expense_k - risk_premium_k) + accumulated_interest(t)
        """
        policy = self._policies.get(policy_id)
        if not policy:
            raise ValueError(f"保单不存在: {policy_id}")

        if not policy.supports_cash_value:
            raise ValueError(f"险种 {policy.policy_type.value} 不支持现金价值计算")

        if as_of_year < 1 or as_of_year > policy.term_years:
            raise ValueError(f"年度 {as_of_year} 超出保障期限 {policy.term_years}")

        dividend_rate = DIVIDEND_RATES.get(rate_scenario, DIVIDEND_RATES["mid"])

        # 逐年计算
        guaranteed_cv = Decimal("0")
        total_dividend = Decimal("0")

        for year in range(1, as_of_year + 1):
            if year <= policy.payment_years:
                # 缴费期内
                premium = policy.annual_premium

                # 费用扣除
                if year in INITIAL_EXPENSE_RATE:
                    expense = premium * INITIAL_EXPENSE_RATE[year]
                else:
                    expense = premium * MAINTENANCE_EXPENSE_RATE

                # 风险保费
                risk_rate = RISK_PREMIUM_RATE.get(policy.policy_type, Decimal("0.001"))
                risk_premium = policy.sum_assured * risk_rate

                # 净现金流
                net = premium - expense - risk_premium
                guaranteed_cv += net

            # 累积利息（保证利率 2.5%）
            guaranteed_cv *= (Decimal("1") + DIVIDEND_RATES["low"])

            # 红利（非保证）
            if year <= policy.payment_years:
                annual_div = guaranteed_cv * (dividend_rate - DIVIDEND_RATES["low"])
                total_dividend += annual_div

        # 各档演示
        dividend_details = {}
        for scenario, rate in DIVIDEND_RATES.items():
            cv_at_rate = Decimal("0")
            for year in range(1, as_of_year + 1):
                if year <= policy.payment_years:
                    premium = policy.annual_premium
                    if year in INITIAL_EXPENSE_RATE:
                        expense = premium * INITIAL_EXPENSE_RATE[year]
                    else:
                        expense = premium * MAINTENANCE_EXPENSE_RATE
                    risk_rate = RISK_PREMIUM_RATE.get(policy.policy_type, Decimal("0.001"))
                    risk_premium = policy.sum_assured * risk_rate
                    net = premium - expense - risk_premium
                    cv_at_rate += net
                cv_at_rate *= (Decimal("1") + rate)
            dividend_details[scenario] = cv_at_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        non_guaranteed_cv = dividend_details.get(rate_scenario, guaranteed_cv)
        total_cv = non_guaranteed_cv

        return CashValueResult(
            policy_id=policy_id,
            as_of_year=as_of_year,
            guaranteed_cv=guaranteed_cv.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            non_guaranteed_cv=non_guaranteed_cv.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            total_cv=total_cv.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            dividend_details=dividend_details,
        )

    # ---------- 退保价值 ----------

    def calculate_surrender_value(
        self,
        policy_id: str,
        as_of_year: int,
        rate_scenario: str = "mid",
    ) -> SurrenderValueResult:
        """
        计算退保价值

        SV(t) = CV(t) × (1 - surrender_fee_rate(t))
        """
        policy = self._policies.get(policy_id)
        if not policy:
            raise ValueError(f"保单不存在: {policy_id}")

        if not policy.supports_surrender:
            raise ValueError(f"险种 {policy.policy_type.value} 不支持退保计算")

        cv_result = self.calculate_cash_value(policy_id, as_of_year, rate_scenario)
        cash_value = cv_result.total_cv

        # 退保手续费率
        if as_of_year in SURRENDER_FEE_RATES:
            fee_rate = SURRENDER_FEE_RATES[as_of_year]
        else:
            fee_rate = Decimal("0")  # 5 年后无手续费

        surrender_fee = (cash_value * fee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        surrender_value = cash_value - surrender_fee

        return SurrenderValueResult(
            policy_id=policy_id,
            as_of_year=as_of_year,
            cash_value=cash_value,
            surrender_fee=surrender_fee,
            surrender_value=surrender_value,
            surrender_fee_rate=fee_rate,
        )

    # ---------- IRR（牛顿迭代法） ----------

    def calculate_irr(
        self,
        policy_id: str,
        as_of_year: int,
        rate_scenario: str = "mid",
    ) -> IRRResult:
        """
        计算保险 IRR（牛顿迭代法）

        现金流: [-P1, -P2, ..., -Pn, +CV(n)]
        求解: Σ[t=0 to N] CF_t / (1+r)^t = 0
        """
        policy = self._policies.get(policy_id)
        if not policy:
            raise ValueError(f"保单不存在: {policy_id}")

        if not policy.supports_irr:
            raise ValueError(f"险种 {policy.policy_type.value} 不支持 IRR 计算")

        # 构建现金流
        cash_flows: List[Decimal] = []
        for year in range(1, as_of_year + 1):
            if year <= policy.payment_years:
                cash_flows.append(-policy.annual_premium)  # 缴费（流出）
            else:
                cash_flows.append(Decimal("0"))

        # 最后一年的现金价值（流入）
        cv_result = self.calculate_cash_value(policy_id, as_of_year, rate_scenario)
        cash_flows[-1] += cv_result.total_cv

        # 牛顿迭代法
        r = IRR_INITIAL_GUESS
        converged = False
        iterations = 0

        for i in range(IRR_MAX_ITERATIONS):
            iterations = i + 1

            # f(r) = Σ CF_t / (1+r)^t
            f_r = Decimal("0")
            for t, cf in enumerate(cash_flows):
                f_r += cf / ((Decimal("1") + r) ** t)

            # f'(r) = Σ -t * CF_t / (1+r)^(t+1)
            f_prime = Decimal("0")
            for t, cf in enumerate(cash_flows):
                if t > 0:
                    f_prime += Decimal(str(-t)) * cf / ((Decimal("1") + r) ** (t + 1))

            if f_prime == 0:
                break

            r_new = r - f_r / f_prime

            if abs(r_new - r) < IRR_CONVERGENCE:
                converged = True
                r = r_new
                break

            r = r_new

        return IRRResult(
            policy_id=policy_id,
            as_of_year=as_of_year,
            irr=(r * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            calculation_method="newton",
            converged=converged,
            iterations=iterations,
        )

    # ---------- 红利演示 ----------

    def project_dividend(
        self,
        policy_id: str,
        as_of_year: int,
        rate_scenario: str = "mid",
    ) -> DividendProjection:
        """红利演示"""
        policy = self._policies.get(policy_id)
        if not policy:
            raise ValueError(f"保单不存在: {policy_id}")

        if not policy.supports_cash_value:
            raise ValueError(f"险种 {policy.policy_type.value} 不支持红利演示")

        dividend_rate = DIVIDEND_RATES.get(rate_scenario, DIVIDEND_RATES["mid"])
        cv_result = self.calculate_cash_value(policy_id, as_of_year, rate_scenario)

        # 当年红利（简化：基于当年末保证 CV 的增量）
        if as_of_year == 1:
            prev_guaranteed = Decimal("0")
        else:
            prev_result = self.calculate_cash_value(policy_id, as_of_year - 1, "low")
            prev_guaranteed = prev_result.guaranteed_cv

        annual_dividend = (cv_result.guaranteed_cv - prev_guaranteed) * (
            dividend_rate - DIVIDEND_RATES["low"]
        )

        # 累计红利
        cumulative = Decimal("0")
        for y in range(1, as_of_year + 1):
            if y == 1:
                prev_g = Decimal("0")
            else:
                prev_r = self.calculate_cash_value(policy_id, y - 1, "low")
                prev_g = prev_r.guaranteed_cv
            curr_r = self.calculate_cash_value(policy_id, y, "low")
            cumulative += (curr_r.guaranteed_cv - prev_g) * (dividend_rate - DIVIDEND_RATES["low"])

        return DividendProjection(
            policy_id=policy_id,
            as_of_year=as_of_year,
            scenario=rate_scenario,
            dividend_rate=dividend_rate,
            annual_dividend=annual_dividend.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            cumulative_dividend=cumulative.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            total_cv=cv_result.total_cv,
        )

    # ---------- 三档演示汇总 ----------

    def project_all_scenarios(
        self,
        policy_id: str,
        as_of_year: int,
    ) -> Dict[str, CashValueResult]:
        """输出三档演示汇总"""
        results = {}
        for scenario in ("low", "mid", "high"):
            results[scenario] = self.calculate_cash_value(policy_id, as_of_year, scenario)
        return results
