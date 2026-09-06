"""
FIN-006 理财建议引擎

功能:
- 财务健康诊断（6 KPI）
- 资产配置建议（风险双维度 + Rule of 110）
- 债务优化（Avalanche/Snowball/Hybrid）
- 保障缺口分析
- 综合理财报告
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional, Dict
from datetime import datetime


# ========== 工具函数 ==========

def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ========== 枚举 ==========

class RiskLevel(Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class KPIStatus(Enum):
    GOOD = "good"
    WARNING = "warning"
    DANGER = "danger"


class DebtStrategy(Enum):
    AVALANCHE = "avalanche"
    SNOWBALL = "snowball"
    HYBRID = "hybrid"


# ========== KPI 基准 ==========

KPI_BENCHMARKS = {
    "savings_rate":      {"good": Decimal("20"),  "warning": Decimal("10"),  "unit": "%"},
    "dti":               {"good": Decimal("36"),  "warning": Decimal("50"),  "unit": "%"},
    "liquidity_ratio":   {"good": Decimal("6"),   "warning": Decimal("3"),   "unit": "months"},
    "emergency_fund":    {"good": Decimal("6"),   "warning": Decimal("3"),   "unit": "months"},
    "net_worth_growth":  {"good": Decimal("0"),   "warning": Decimal("0"),   "unit": "%"},
    "diversification":   {"good": Decimal("25"),  "warning": Decimal("40"),  "unit": "%"},
}

# 资产配置映射（风险等级 → 股票/债券/现金/其他）
ALLOCATION_MAP = {
    RiskLevel.CONSERVATIVE: {
        "stock": {"min": Decimal("30"), "max": Decimal("50")},
        "bond": {"min": Decimal("40"), "max": Decimal("55")},
        "cash": {"min": Decimal("10"), "max": Decimal("15")},
        "other": {"min": Decimal("0"), "max": Decimal("5")},
    },
    RiskLevel.MODERATE: {
        "stock": {"min": Decimal("55"), "max": Decimal("70")},
        "bond": {"min": Decimal("25"), "max": Decimal("35")},
        "cash": {"min": Decimal("5"), "max": Decimal("10")},
        "other": {"min": Decimal("0"), "max": Decimal("5")},
    },
    RiskLevel.AGGRESSIVE: {
        "stock": {"min": Decimal("75"), "max": Decimal("90")},
        "bond": {"min": Decimal("10"), "max": Decimal("20")},
        "cash": {"min": Decimal("0"), "max": Decimal("5")},
        "other": {"min": Decimal("0"), "max": Decimal("5")},
    },
}


# ========== 数据模型 ==========

@dataclass
class KPIResult:
    name: str
    value: Decimal
    benchmark: Decimal
    status: KPIStatus
    suggestion: str


@dataclass
class HealthReport:
    overall_score: int
    kpi_scores: List[KPIResult]
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class AllocationAdvice:
    risk_level: RiskLevel
    risk_capacity_score: int
    risk_tolerance_score: int
    target_allocation: Dict[str, Decimal]
    age_adjusted_allocation: Optional[Dict[str, Decimal]]
    rationale: str


@dataclass
class DebtInfo:
    """债务信息"""
    name: str
    balance: Decimal
    annual_rate: Decimal
    min_payment: Decimal


@dataclass
class PayoffStep:
    month: int
    debt_name: str
    payment: Decimal
    principal: Decimal
    interest: Decimal
    remaining: Decimal


@dataclass
class PayoffPlan:
    strategy: DebtStrategy
    total_interest: Decimal
    total_months: int
    interest_saved_vs_minimum: Decimal
    schedule: List[PayoffStep]
    rationale: str


@dataclass
class InsuranceGap:
    life_gap: Decimal
    ci_gap: Decimal
    medical_gap: Decimal
    total_premium_budget: Decimal
    recommendations: List[str]


@dataclass
class FinancialReport:
    """综合理财报告"""
    health_score: int
    allocation_advice: Optional[AllocationAdvice]
    debt_plan: Optional[PayoffPlan]
    insurance_gap: Optional[InsuranceGap]
    summary: str
    generated_at: datetime = field(default_factory=datetime.now)


# ========== 引擎 ==========

class AdvisorEngine:
    """理财建议引擎"""

    # ---------- 财务健康诊断 ----------

    def diagnose_financial_health(
        self,
        monthly_income,
        monthly_expenses,
        total_assets: Decimal,
        total_liabilities: Decimal,
        emergency_fund: Decimal,
        monthly_savings: Optional[Decimal] = None,
        investment_concentration: Optional[Decimal] = None,
    ) -> HealthReport:
        """
        财务健康诊断（6 KPI）

        monthly_income: 月收入
        monthly_expenses: 月支出
        total_assets: 总资产
        total_liabilities: 总负债
        emergency_fund: 应急资金
        monthly_savings: 月储蓄（可选，默认 = income - expenses）
        investment_concentration: 最大单一投资占比 %（可选）
        """
        income = _to_decimal(monthly_income)
        expenses = _to_decimal(monthly_expenses)
        assets = _to_decimal(total_assets)
        liabilities = _to_decimal(total_liabilities)
        emergency = _to_decimal(emergency_fund)

        if monthly_savings is not None:
            savings = _to_decimal(monthly_savings)
        else:
            savings = income - expenses

        kpi_scores = []

        # 1. 储蓄率
        if income > 0:
            savings_rate = (savings / income * Decimal("100")).quantize(Decimal("0.01"))
        else:
            savings_rate = Decimal("0")

        if savings_rate >= KPI_BENCHMARKS["savings_rate"]["good"]:
            status = KPIStatus.GOOD
            suggestion = "储蓄率健康，继续保持"
        elif savings_rate >= KPI_BENCHMARKS["savings_rate"]["warning"]:
            status = KPIStatus.WARNING
            suggestion = "储蓄率偏低，建议控制非必要支出"
        else:
            status = KPIStatus.DANGER
            suggestion = "储蓄率过低，需立即调整收支结构"
        kpi_scores.append(KPIResult("储蓄率", savings_rate, KPI_BENCHMARKS["savings_rate"]["good"], status, suggestion))

        # 2. DTI（负债收入比）
        # 简化：月还款 ≈ 负债 × 0.01（假设平均 1% 月还款率）
        monthly_debt_payment = liabilities * Decimal("0.01")
        if income > 0:
            dti = (monthly_debt_payment / income * Decimal("100")).quantize(Decimal("0.01"))
        else:
            dti = Decimal("0")

        if dti <= KPI_BENCHMARKS["dti"]["good"]:
            status = KPIStatus.GOOD
            suggestion = "负债水平可控"
        elif dti <= KPI_BENCHMARKS["dti"]["warning"]:
            status = KPIStatus.WARNING
            suggestion = "负债偏高，避免新增高息债务"
        else:
            status = KPIStatus.DANGER
            suggestion = "负债过高，优先偿还高息债务"
        kpi_scores.append(KPIResult("负债收入比(DTI)", dti, KPI_BENCHMARKS["dti"]["good"], status, suggestion))

        # 3. 流动性比率
        if expenses > 0:
            liquidity = (assets / expenses).quantize(Decimal("0.01"))
        else:
            liquidity = Decimal("0")

        if liquidity >= KPI_BENCHMARKS["liquidity_ratio"]["good"]:
            status = KPIStatus.GOOD
            suggestion = "流动性充足"
        elif liquidity >= KPI_BENCHMARKS["liquidity_ratio"]["warning"]:
            status = KPIStatus.WARNING
            suggestion = "流动性一般，增加现金储备"
        else:
            status = KPIStatus.DANGER
            suggestion = "流动性不足，优先建立应急资金"
        kpi_scores.append(KPIResult("流动性比率(月)", liquidity, KPI_BENCHMARKS["liquidity_ratio"]["good"], status, suggestion))

        # 4. 应急储备
        if expenses > 0:
            emergency_months = (emergency / expenses).quantize(Decimal("0.01"))
        else:
            emergency_months = Decimal("0")

        if emergency_months >= KPI_BENCHMARKS["emergency_fund"]["good"]:
            status = KPIStatus.GOOD
            suggestion = "应急储备充足"
        elif emergency_months >= KPI_BENCHMARKS["emergency_fund"]["warning"]:
            status = KPIStatus.WARNING
            suggestion = "应急储备不足，目标 6 个月支出"
        else:
            status = KPIStatus.DANGER
            suggestion = "应急储备严重不足，优先补足"
        kpi_scores.append(KPIResult("应急储备(月)", emergency_months, KPI_BENCHMARKS["emergency_fund"]["good"], status, suggestion))

        # 5. 净资产增长率（简化：基于储蓄率估算）
        if assets > 0:
            net_worth_growth = (savings * Decimal("12") / assets * Decimal("100")).quantize(Decimal("0.01"))
        else:
            net_worth_growth = Decimal("0")

        if net_worth_growth > 0:
            status = KPIStatus.GOOD
            suggestion = "净资产正增长"
        else:
            status = KPIStatus.DANGER
            suggestion = "净资产负增长，需调整"
        kpi_scores.append(KPIResult("净资产增长率", net_worth_growth, KPI_BENCHMARKS["net_worth_growth"]["good"], status, suggestion))

        # 6. 投资多样化
        if investment_concentration is not None:
            conc = _to_decimal(investment_concentration)
            if conc <= KPI_BENCHMARKS["diversification"]["good"]:
                status = KPIStatus.GOOD
                suggestion = "投资分散良好"
            elif conc <= KPI_BENCHMARKS["diversification"]["warning"]:
                status = KPIStatus.WARNING
                suggestion = "单一资产偏高，适当分散"
            else:
                status = KPIStatus.DANGER
                suggestion = "过度集中，需立即分散"
            kpi_scores.append(KPIResult("最大单一资产占比", conc, KPI_BENCHMARKS["diversification"]["good"], status, suggestion))

        # 计算总分
        score_map = {KPIStatus.GOOD: 100, KPIStatus.WARNING: 60, KPIStatus.DANGER: 20}
        if kpi_scores:
            overall_score = sum(score_map.get(k.status, 0) for k in kpi_scores) // len(kpi_scores)
        else:
            overall_score = 0

        strengths = [k.name for k in kpi_scores if k.status == KPIStatus.GOOD]
        weaknesses = [f"{k.name}: {k.suggestion}" for k in kpi_scores if k.status != KPIStatus.GOOD]
        recommendations = [k.suggestion for k in kpi_scores if k.status == KPIStatus.DANGER]

        return HealthReport(
            overall_score=overall_score,
            kpi_scores=kpi_scores,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
        )

    # ---------- 资产配置建议 ----------

    def suggest_asset_allocation(
        self,
        age: int,
        risk_capacity: int,
        risk_tolerance: int,
        investment_horizon: int = 10,
    ) -> AllocationAdvice:
        """
        资产配置建议

        risk_capacity: 1-5（数学维度）
        risk_tolerance: 1-5（情绪维度）
        """
        # 取较低分
        effective_score = min(risk_capacity, risk_tolerance)

        if effective_score <= 2:
            risk_level = RiskLevel.CONSERVATIVE
        elif effective_score == 3:
            risk_level = RiskLevel.MODERATE
        else:
            risk_level = RiskLevel.AGGRESSIVE

        alloc = ALLOCATION_MAP[risk_level]

        # 取中间值作为建议
        target = {}
        for k, v in alloc.items():
            mid = (v["min"] + v["max"]) / Decimal("2")
            target[k] = mid.quantize(Decimal("0.01"))

        # Rule of 110 年龄调整
        stock_pct = Decimal(str(110 - age))
        bond_pct = Decimal("100") - stock_pct
        age_adjusted = {
            "stock": stock_pct.quantize(Decimal("0.01")),
            "bond": bond_pct.quantize(Decimal("0.01")),
            "cash": Decimal("0"),
            "other": Decimal("0"),
        }

        rationale = (
            f"风险等级: {risk_level.value}（Risk Capacity={risk_capacity}, "
            f"Risk Tolerance={risk_tolerance}, 取较低分={effective_score}）。"
            f"投资期限 {investment_horizon} 年。"
            f"年龄 {age} 岁，Rule of 110 建议股票 {stock_pct}%。"
        )

        return AllocationAdvice(
            risk_level=risk_level,
            risk_capacity_score=risk_capacity,
            risk_tolerance_score=risk_tolerance,
            target_allocation=target,
            age_adjusted_allocation=age_adjusted,
            rationale=rationale,
        )

    # ---------- 债务优化 ----------

    def optimize_debt_payoff(
        self,
        debts: List[DebtInfo],
        monthly_budget,
        strategy: str = "avalanche",
    ) -> PayoffPlan:
        """
        债务优化

        strategy: "avalanche" / "snowball" / "hybrid"
        """
        budget = _to_decimal(monthly_budget)

        if not debts:
            return PayoffPlan(
                strategy=DebtStrategy(strategy), total_interest=Decimal("0"),
                total_months=0, interest_saved_vs_minimum=Decimal("0"),
                schedule=[], rationale="无债务",
            )

        # 排序
        if strategy == "avalanche":
            sorted_debts = sorted(debts, key=lambda d: d.annual_rate, reverse=True)
        elif strategy == "snowball":
            sorted_debts = sorted(debts, key=lambda d: d.balance)
        else:  # hybrid
            # 高息 + 小额优先
            sorted_debts = sorted(
                debts,
                key=lambda d: (d.annual_rate * Decimal("0.6") - d.balance * Decimal("0.00004")),
                reverse=True,
            )

        # 模拟还款
        remaining = {d.name: d.balance for d in debts}
        min_payments = {d.name: d.min_payment for d in debts}
        rates = {d.name: d.annual_rate for d in debts}
        schedule = []
        total_interest = Decimal("0")
        month = 0

        while any(v > 0 for v in remaining.values()) and month < 600:
            month += 1
            available = budget

            # 最低还款
            for d in sorted_debts:
                if remaining[d.name] <= 0:
                    continue
                min_pay = min(min_payments[d.name], remaining[d.name])
                interest = (remaining[d.name] * rates[d.name] / Decimal("12")).quantize(Decimal("0.01"))
                principal = min_pay - interest
                if principal < 0:
                    principal = Decimal("0")
                remaining[d.name] -= principal
                remaining[d.name] = max(remaining[d.name], Decimal("0"))
                total_interest += interest
                available -= min_pay

            # 额外还款（按策略排序）
            if available > 0:
                for d in sorted_debts:
                    if remaining[d.name] <= 0:
                        continue
                    extra = min(available, remaining[d.name])
                    remaining[d.name] -= extra
                    remaining[d.name] = max(remaining[d.name], Decimal("0"))
                    available -= extra

                    schedule.append(PayoffStep(
                        month=month,
                        debt_name=d.name,
                        payment=min_payments[d.name] + extra,
                        principal=extra,
                        interest=(remaining[d.name] * rates[d.name] / Decimal("12")).quantize(Decimal("0.01")),
                        remaining=remaining[d.name],
                    ))

                    if available <= 0:
                        break

        # 最低还款对比（简化）
        min_total_interest = total_interest * Decimal("1.2")  # 估算
        interest_saved = (min_total_interest - total_interest).quantize(Decimal("0.01"))

        rationale_map = {
            "avalanche": "雪崩法：优先偿还高息债务，总利息最少",
            "snowball": "雪球法：优先偿还小额债务，心理激励强",
            "hybrid": "混合法：兼顾高息与小额，平衡效率与心理",
        }

        return PayoffPlan(
            strategy=DebtStrategy(strategy),
            total_interest=total_interest.quantize(Decimal("0.01")),
            total_months=month,
            interest_saved_vs_minimum=interest_saved,
            schedule=schedule,
            rationale=rationale_map.get(strategy, ""),
        )

    # ---------- 保障缺口分析 ----------

    def analyze_insurance_gap(
        self,
        annual_income,
        total_liabilities: Decimal,
        liquid_assets: Decimal,
        existing_life_coverage: Decimal = Decimal("0"),
        existing_ci_coverage: Decimal = Decimal("0"),
        has_medical: bool = False,
        dependents: int = 0,
    ) -> InsuranceGap:
        """
        保障缺口分析

        寿险保额建议 = 年收入 × 10 + 总负债 - 流动资产
        重疾险保额建议 = 年收入 × 3 + 30万
        """
        income = _to_decimal(annual_income)
        liabilities = _to_decimal(total_liabilities)
        assets = _to_decimal(liquid_assets)
        life_cov = _to_decimal(existing_life_coverage)
        ci_cov = _to_decimal(existing_ci_coverage)

        # 寿险缺口
        life_needed = income * Decimal("10") + liabilities - assets
        life_gap = max(life_needed - life_cov, Decimal("0"))

        # 重疾缺口
        ci_needed = income * Decimal("3") + Decimal("300000")
        ci_gap = max(ci_needed - ci_cov, Decimal("0"))

        # 医疗缺口
        medical_gap = Decimal("0") if has_medical else Decimal("300000")

        # 保费预算建议
        premium_budget = income * Decimal("0.10")  # 10%

        recommendations = []
        if life_gap > 0:
            recommendations.append(f"建议补充定期寿险 {life_gap.quantize(Decimal('0.01'))} 元保额")
        if ci_gap > 0:
            recommendations.append(f"建议补充重疾险 {ci_gap.quantize(Decimal('0.01'))} 元保额")
        if medical_gap > 0:
            recommendations.append("建议配置百万医疗险")
        if dependents > 0:
            recommendations.append(f"有 {dependents} 位依赖人，寿险保额需充足")
        recommendations.append(f"总保费预算建议: 年收入的 10-15% = {premium_budget.quantize(Decimal('0.01'))} 元")

        return InsuranceGap(
            life_gap=life_gap.quantize(Decimal("0.01")),
            ci_gap=ci_gap.quantize(Decimal("0.01")),
            medical_gap=medical_gap,
            total_premium_budget=premium_budget.quantize(Decimal("0.01")),
            recommendations=recommendations,
        )

    # ---------- 综合报告 ----------

    def generate_financial_report(
        self,
        monthly_income,
        monthly_expenses,
        total_assets: Decimal,
        total_liabilities: Decimal,
        emergency_fund: Decimal,
        debts: Optional[List[DebtInfo]] = None,
        monthly_budget: Optional[Decimal] = None,
        age: int = 30,
        risk_capacity: int = 3,
        risk_tolerance: int = 3,
        investment_concentration: Optional[Decimal] = None,
    ) -> FinancialReport:
        """生成综合理财报告"""
        health = self.diagnose_financial_health(
            monthly_income=monthly_income,
            monthly_expenses=monthly_expenses,
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            emergency_fund=emergency_fund,
            investment_concentration=investment_concentration,
        )

        allocation = self.suggest_asset_allocation(age, risk_capacity, risk_tolerance)

        debt_plan = None
        if debts and monthly_budget:
            debt_plan = self.optimize_debt_payoff(debts, monthly_budget)

        insurance = self.analyze_insurance_gap(
            annual_income=monthly_income * Decimal("12"),
            total_liabilities=total_liabilities,
            liquid_assets=emergency_fund,
        )

        summary = (
            f"财务健康评分: {health.overall_score}/100。"
            f"风险等级: {allocation.risk_level.value}。"
            f"建议股票配置: {allocation.target_allocation.get('stock', 0)}%。"
        )
        if debt_plan:
            summary += f"债务清偿计划: {debt_plan.total_months} 个月，总利息 {debt_plan.total_interest}。"

        return FinancialReport(
            health_score=health.overall_score,
            allocation_advice=allocation,
            debt_plan=debt_plan,
            insurance_gap=insurance,
            summary=summary,
        )
