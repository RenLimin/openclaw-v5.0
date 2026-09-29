# DESIGN-DETAIL - finance-engine v1.0

> **版本**: v1.0  
> **层级**: L3 通用业务层  
> **组件**: finance-engine  
> **最后更新**: 2026-09-29

---

## 1. 接口契约

### 1.1 fin001 — 复式记账引擎

```python
class AccountType(Enum):
    ASSET = "asset"           # 资产（借增贷减）
    LIABILITY = "liability"   # 负债（贷增借减）
    INCOME = "income"         # 收入（贷增借减）
    EQUITY = "equity"         # 权益（贷增借减）
    EXPENSE = "expense"       # 费用（借增贷减）

class DebitCredit(Enum):
    DEBIT = "debit"
    CREDIT = "credit"

@dataclass
class Account:
    id: str
    name: str
    type: AccountType
    currency: str = "CNY"
    parent_id: Optional[str] = None
    balance: Decimal = Decimal("0")  # 自动 quantize 到 0.01
    created_at: date = date.today()
    metadata: dict = field(default_factory=dict)

@dataclass
class Transaction:
    id: str
    date: date
    debit_account_id: str
    credit_account_id: str
    amount: Decimal                 # 必须 > 0，自动 quantize
    note: str = ""
    created_at: datetime = datetime.now()
    source: str = "manual"

@dataclass
class AccountBalance:
    account_id: str
    account_name: str
    account_type: AccountType
    debit_balance: Decimal
    credit_balance: Decimal
    net_balance: Decimal

class AccountingEngine:
    """复式记账引擎。"""

    def __init__(self):
        self.accounts: Dict[str, Account] = {}
        self.transactions: List[Transaction] = []

    # 账户管理
    def create_account(self, name: str, type: AccountType, **kwargs) -> Account: ...
    def get_account(self, account_id: str) -> Optional[Account]: ...
    def list_accounts(self, type: Optional[AccountType] = None) -> List[Account]: ...

    # 记账
    def record_transaction(
        self,
        debit_account_id: str,
        credit_account_id: str,
        amount: Decimal,
        date: date = None,
        **kwargs,
    ) -> Transaction: ...

    # 查询
    def get_balance(self, account_id: str) -> AccountBalance: ...
    def trial_balance(self) -> List[AccountBalance]: ...
    def is_balanced(self) -> bool: ...
```

**关键行为**：
- 交易金额必须 > 0，否则抛 `ValueError`
- 借/贷账户必须存在，否则抛 `ValueError`
- `trial_balance()` 返回所有账户的借/贷/净余额
- `is_balanced()` 验证总借方 = 总贷方（借贷平衡）

### 1.2 fin002 — 贷款核算引擎

```python
class LoanMethod(Enum):
    EQUAL_PAYMENT = "equal_payment"       # 等额本息
    EQUAL_PRINCIPAL = "equal_principal"   # 等额本金
    INTEREST_ONLY = "interest_only"       # 先息后本
    FLEXIBLE = "flexible"                 # 随借随还

class LoanStatus(Enum):
    ACTIVE = "active"
    PAID_OFF = "paid_off"
    DEFAULTED = "defaulted"

@dataclass
class Loan:
    id: str
    name: str
    principal: Decimal        # 本金（自动 quantize）
    annual_rate: Decimal      # 年利率（如 0.035 = 3.5%，高精度）
    term_months: int
    method: LoanMethod
    start_date: date
    remaining_balance: Decimal = Decimal("0")  # 默认=principal
    status: LoanStatus = LoanStatus.ACTIVE
    metadata: dict = field(default_factory=dict)

@dataclass
class AmortizationEntry:
    period: int                        # 期数 1-based
    payment_date: date
    payment: Decimal                   # 月供
    principal: Decimal                 # 本金部分
    interest: Decimal                  # 利息部分
    remaining_balance: Decimal         # 剩余本金
    cumulative_interest: Decimal       # 累计利息

@dataclass
class AmortizationSchedule:
    loan_id: str
    entries: List[AmortizationEntry]
    total_payment: Decimal
    total_interest: Decimal
    generated_at: date = date.today()

@dataclass
class PrepayResult:
    original_schedule: AmortizationSchedule
    new_schedule: AmortizationSchedule
    prepay_amount: Decimal
    prepay_date: date
    interest_saved: Decimal
    new_term_months: int  # 缩短后的期数

class LoanEngine:
    """贷款核算引擎（纯函数）。"""

    @staticmethod
    def calculate_schedule(loan: Loan) -> AmortizationSchedule: ...

    @staticmethod
    def equal_payment(principal, annual_rate, term_months, start_date) -> AmortizationSchedule:
        """等额本息：月供 = P × r × (1+r)^n / ((1+r)^n - 1)"""

    @staticmethod
    def equal_principal(principal, annual_rate, term_months, start_date) -> AmortizationSchedule:
        """等额本金：每月本金 = P/n，利息逐月递减"""

    @staticmethod
    def interest_only(principal, annual_rate, term_months, start_date) -> AmortizationSchedule:
        """先息后本：每月还利息，期末还本金"""

    @staticmethod
    def flexible(principal, annual_rate, start_date, end_date) -> AmortizationSchedule:
        """随借随还：按日计息"""

    @staticmethod
    def prepay(
        loan: Loan,
        prepay_amount: Decimal,
        prepay_date: date,
        method: str = "reduce_term",  # reduce_term / reduce_payment
    ) -> PrepayResult:
        """提前还款模拟"""

    @staticmethod
    def compare_methods(principal, annual_rate, term_months, start_date) -> Dict[LoanMethod, dict]:
        """对比 4 种还款方式的总利息、月供等"""
```

**计算公式**：
- **等额本息月供**：`M = P × r × (1+r)^n / ((1+r)^n - 1)`，其中 r = 月利率 = 年利率/12
- **等额本金**：每月本金 = P/n，第 k 月利息 = (P - (k-1)×P/n) × r
- **先息后本**：每月利息 = P × r，最后一期还本金 + 利息
- **随借随还**：利息 = P × 年利率 × 天数 / 365

### 1.3 fin003 — 保险测算引擎

```python
# 常量
DIVIDEND_RATES = {"low": Decimal("0.025"), "mid": Decimal("0.045"), "high": Decimal("0.060")}
SURRENDER_FEE_RATES = {1: 0.05, 2: 0.04, 3: 0.03, 4: 0.02, 5: 0.01}
IRR_MAX_ITERATIONS = 200
IRR_CONVERGENCE = Decimal("1e-8")
IRR_INITIAL_GUESS = Decimal("0.03")

class InsuranceType(Enum):
    TERM_LIFE = "term_life"           # 定期寿险
    WHOLE_LIFE = "whole_life"         # 终身寿险
    ENDOWMENT = "endowment"           # 两全保险
    CRITICAL_ILLNESS = "critical_illness"  # 重疾险
    MEDICAL = "medical"               # 医疗险
    ANNUITY = "annuity"               # 年金险
    UNIVERSAL_LIFE = "universal_life" # 万能险
    TAX_DEFERRED = "tax_deferred"     # 税延养老险

class PolicyStatus(Enum):
    ACTIVE = "active"
    LAPSED = "lapsed"
    SURRENDERED = "surrendered"
    MATURED = "matured"
    CLAIMED = "claimed"

@dataclass
class InsurancePolicy:
    id: str
    type: InsuranceType
    product_name: str
    insured_name: str = ""
    premium: Decimal = Decimal("0")         # 年交保费
    payment_period_years: int = 20          # 缴费期
    policy_term_years: int = 20             # 保障期
    sum_assured: Decimal = Decimal("0")     # 基本保额
    issue_date: date = date.today()
    status: PolicyStatus = PolicyStatus.ACTIVE
    metadata: dict = field(default_factory=dict)

@dataclass
class CashValueRow:
    policy_year: int
    premium_paid: Decimal          # 累计已交保费
    sum_at_risk: Decimal           # 风险保额
    cash_value: Decimal            # 现金价值
    surrender_value: Decimal       # 退保价值 = 现金价值 - 退保手续费
    guaranteed_interest: Decimal   # 保证利息

@dataclass
class DividendDemo:
    year: int
    low: Decimal                   # 低档红利
    mid: Decimal                   # 中档
    high: Decimal                  # 高档
    cumulative_low: Decimal
    cumulative_mid: Decimal
    cumulative_high: Decimal

@dataclass
class IRRResult:
    irr: Decimal                    # 内部收益率
    iterations: int                 # 迭代次数
    converged: bool                 # 是否收敛
    final_error: Decimal            # 最终误差

class InsuranceEngine:
    """保险测算引擎。"""

    @staticmethod
    def cash_value_table(policy: InsurancePolicy, years: int) -> List[CashValueRow]:
        """生成现金价值表"""

    @staticmethod
    def surrender_value(policy: InsurancePolicy, policy_year: int) -> Decimal:
        """第 N 年退保价值"""

    @staticmethod
    def calculate_irr(cash_flows: List[Decimal], guess: Decimal = IRR_INITIAL_GUESS) -> IRRResult:
        """
        计算内部收益率（牛顿迭代法）
        NPV = Σ CF_t / (1+IRR)^t = 0
        """

    @staticmethod
    def dividend_demo(policy: InsurancePolicy, years: int) -> List[DividendDemo]:
        """三档红利演示（低/中/高）"""

    @staticmethod
    def compare_policies(policies: List[InsurancePolicy], metric: str) -> List[dict]:
        """多产品对比"""
```

**IRR 算法**：牛顿迭代法
- 目标：找到 r 使得 NPV(r) = Σ CF_t / (1+r)^t = 0
- 迭代：r_{n+1} = r_n - NPV(r_n) / NPV'(r_n)
- 收敛条件：|NPV(r)| < IRR_CONVERGENCE (1e-8)
- 最大迭代：200 次

### 1.4 fin004 — 利率服务

```python
CACHE_TTL_HOURS = 24
CACHE_DIR = "~/.openclaw/cache/fin004_rate"
DEFAULT_LPR_1Y = Decimal("0.0300")   # 3.00%
DEFAULT_LPR_5Y = Decimal("0.0350")   # 3.50%

@dataclass
class RateSnapshot:
    rate_type: str              # "lpr_1y" / "lpr_5y" / ...
    rate: Decimal               # 小数形式，如 0.035 = 3.5%
    effective_date: date
    source: str
    fetched_at: datetime
    is_cached: bool = False
    is_expired: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def rate_pct(self) -> Decimal:  # 百分比形式，如 3.5000
        return (rate * 100).quantize(Decimal("0.0001"))

@dataclass
class RateHistory:
    rate_type: str
    snapshots: List[RateSnapshot]

    def latest(self) -> RateSnapshot: ...
    def at_date(self, d: date) -> Optional[RateSnapshot]: ...

class RateEngine:
    """利率服务（唯一允许 IO 的模块）。"""

    # 查询
    def get_lpr(self, term: str = "1y") -> RateSnapshot: ...
    def get_central_bank_rate(self, country: str, rate_type: str) -> RateSnapshot: ...

    # 转换
    @staticmethod
    def annual_to_monthly(annual_rate: Decimal, compound: bool = True) -> Decimal:
        """年利率 → 月利率
        复利: (1+r)^(1/12) - 1
        单利: r / 12
        """

    @staticmethod
    def monthly_to_annual(monthly_rate: Decimal, compound: bool = True) -> Decimal: ...

    @staticmethod
    def annual_to_daily(annual_rate: Decimal, days: int = 365) -> Decimal: ...

    # 缓存管理
    def _load_cache(self, rate_type: str) -> Optional[RateSnapshot]: ...
    def _save_cache(self, snapshot: RateSnapshot) -> None: ...
    def _is_cache_valid(self, snapshot: RateSnapshot) -> bool: ...

    # 外部数据源
    def _fetch_from_api(self, rate_type: str) -> Optional[RateSnapshot]: ...
```

**缓存策略**：
- TTL 24 小时
- 本地 JSON 文件存储
- API 失败时返回缓存值（即使过期也返回），标记 `is_expired=True`
- 无缓存且 API 失败时返回默认值

### 1.5 fin005 — 投资组合引擎

```python
class AssetType(Enum):
    CASH = "cash"
    STOCK = "stock"
    FUND = "fund"
    BOND = "bond"
    REAL_ESTATE = "real_estate"
    INSURANCE_CV = "insurance_cv"
    OTHER = "other"

class RiskLevel(Enum):
    LOW = "low"
    LOW_MID = "low_mid"
    MID = "mid"
    MID_HIGH = "mid_high"
    HIGH = "high"

ASSET_RISK_MAP: Dict[AssetType, RiskLevel] = { ... }
ASSET_LIQUIDITY: Dict[AssetType, str] = { ... }
REBALANCE_DRIFT_THRESHOLD = Decimal("5.0")  # 5 个百分点

@dataclass
class Holding:
    id: str
    portfolio_id: str
    asset_type: AssetType
    name: str
    code: str = ""
    quantity: Decimal = Decimal("0")
    cost_price: Decimal = Decimal("0")       # 成本价
    current_price: Decimal = Decimal("0")    # 现价
    currency: str = "CNY"
    risk_level: Optional[RiskLevel] = None
    metadata: dict = field(default_factory=dict)

    @property
    def cost_value(self) -> Decimal: return quantity * cost_price
    @property
    def market_value(self) -> Decimal: return quantity * current_price
    @property
    def pnl(self) -> Decimal: return market_value - cost_value
    @property
    def pnl_ratio(self) -> Decimal: ...  # 收益率

@dataclass
class Portfolio:
    id: str
    name: str
    holdings: List[Holding] = field(default_factory=list)
    currency: str = "CNY"
    metadata: dict = field(default_factory=dict)

    @property
    def total_cost(self) -> Decimal: ...
    @property
    def total_market_value(self) -> Decimal: ...
    @property
    def total_pnl(self) -> Decimal: ...
    @property
    def total_pnl_ratio(self) -> Decimal: ...

@dataclass
class AllocationItem:
    asset_type: AssetType
    value: Decimal
    percentage: Decimal
    target_percentage: Optional[Decimal] = None
    drift: Optional[Decimal] = None  # 偏离度 = 当前% - 目标%

@dataclass
class RebalanceTrade:
    holding_id: str
    asset_type: AssetType
    action: str            # buy / sell
    amount: Decimal        # 金额
    reason: str = ""

class PortfolioEngine:
    """投资组合核算引擎。"""

    @staticmethod
    def add_holding(portfolio: Portfolio, holding: Holding) -> Portfolio: ...
    @staticmethod
    def remove_holding(portfolio, holding_id: str) -> Portfolio: ...
    @staticmethod
    def update_price(portfolio, holding_id, new_price) -> Portfolio: ...

    # 收益
    @staticmethod
    def calculate_pnl(portfolio: Portfolio) -> Portfolio: ...
    @staticmethod
    def annualized_return(portfolio, days_held: int) -> Decimal: ...

    # 资产配置
    @staticmethod
    def allocation_by_type(portfolio: Portfolio) -> List[AllocationItem]: ...
    @staticmethod
    def allocation_by_risk(portfolio: Portfolio) -> List[AllocationItem]: ...
    @staticmethod
    def concentration_ratio(portfolio, top_n: int = 5) -> Decimal: ...

    # 再平衡
    @staticmethod
    def rebalance_advice(
        portfolio: Portfolio,
        target_allocation: Dict[AssetType, Decimal],
        threshold: Decimal = REBALANCE_DRIFT_THRESHOLD,
    ) -> List[RebalanceTrade]: ...
```

### 1.6 fin006 — 理财建议引擎

```python
class RiskLevel(Enum):
    CONSERVATIVE = "conservative"    # 保守型
    MODERATE = "moderate"            # 稳健型
    AGGRESSIVE = "aggressive"        # 进取型

class KPIStatus(Enum):
    GOOD = "good"
    WARNING = "warning"
    DANGER = "danger"

class DebtStrategy(Enum):
    AVALANCHE = "avalanche"  # 雪崩法：优先高利率
    SNOWBALL = "snowball"    # 雪球法：优先小额
    HYBRID = "hybrid"        # 混合法

KPI_BENCHMARKS = {
    "savings_rate":     {"good": 20, "warning": 10, "unit": "%"},
    "dti":              {"good": 36, "warning": 50, "unit": "%"},
    "liquidity_ratio":  {"good": 6,  "warning": 3,  "unit": "months"},
    "emergency_fund":   {"good": 6,  "warning": 3,  "unit": "months"},
    "net_worth_growth": {"good": 0,   "warning": 0,  "unit": "%"},
    "diversification":  {"good": 25,  "warning": 40, "unit": "%"},
}

ALLOCATION_MAP = {
    RiskLevel.CONSERVATIVE: {"stock": {min:30,max:50}, "bond": {...}, ...},
    RiskLevel.MODERATE:     {"stock": {min:55,max:70}, "bond": {...}, ...},
    RiskLevel.AGGRESSIVE:   {"stock": {min:75,max:90}, "bond": {...}, ...},
}

@dataclass
class KPIResult:
    kpi_name: str
    display_name: str
    value: Decimal
    status: KPIStatus
    benchmark_good: Decimal
    benchmark_warning: Decimal
    unit: str
    description: str = ""
    advice: str = ""

@dataclass
class AllocationAdvice:
    risk_level: RiskLevel
    target_allocation: Dict[str, Dict[str, Decimal]]  # 资产类型 → {min, max}
    current_allocation: Dict[str, Decimal]
    gaps: List[str]

@dataclass
class DebtPayoffStep:
    month: int
    payment: Decimal
    debt_id: str
    remaining_balance: Decimal

@dataclass
class DebtPayoffPlan:
    strategy: DebtStrategy
    total_months: int
    total_interest: Decimal
    schedule: List[DebtPayoffStep]

@dataclass
class InsuranceGap:
    category: str          # 寿险 / 重疾 / 医疗 / 意外
    current_coverage: Decimal
    recommended_coverage: Decimal
    gap: Decimal
    description: str

@dataclass
class AdviceReport:
    kpis: List[KPIResult]
    overall_score: Decimal    # 0-100
    allocation_advice: AllocationAdvice
    debt_advice: Optional[DebtPayoffPlan]
    insurance_gaps: List[InsuranceGap]
    summary: str
    priorities: List[str]     # 优先级排序的行动项

class AdvisorEngine:
    """理财建议引擎。"""

    @staticmethod
    def diagnose_kpis(financial_data: dict) -> List[KPIResult]: ...
    @staticmethod
    def determine_risk_level(age, risk_tolerance, ...) -> RiskLevel: ...
    @staticmethod
    def allocation_advice(risk_level: RiskLevel, age: int) -> AllocationAdvice: ...
    @staticmethod
    def rule_of_110(age: int) -> Decimal:  # 股票占比 ≈ 110 - 年龄

    @staticmethod
    def debt_optimize(
        debts: List[dict],
        strategy: DebtStrategy,
        monthly_payment: Decimal,
    ) -> DebtPayoffPlan: ...

    @staticmethod
    def insurance_gap_analysis(profile: dict, coverage: dict) -> List[InsuranceGap]: ...

    @staticmethod
    def full_report(financial_data: dict) -> AdviceReport: ...
```

---

## 2. 数据模型

### 2.1 精度规范

| 类型 | 精度 | rounding | 示例 |
|---|---|---|---|
| 金额（本金/月供/保费） | 0.01 (2位小数) | ROUND_HALF_UP | 1234.56 |
| 利率（年利率） | 不 quantize（高精度） | - | 0.03456789 |
| 比率/百分比展示 | 0.0001 (4位小数) | ROUND_HALF_UP | 3.4567 % |
| IRR | 收敛精度 1e-8 | - | 0.04235678 |
| 份数（股/份额） | 0.0001 (4位小数) | ROUND_HALF_UP | 100.1234 |

### 2.2 数据转换工具

所有模块内部统一使用 `_to_decimal()` 工具函数：

```python
def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

- 支持 int / float / str / Decimal 输入
- 一律先转 `str` 再转 `Decimal`，避免 float 二进制精度问题
- dataclass `__post_init__` 中自动调用

---

## 3. 技术方案

### 3.1 纯函数式设计

**原则**：
- 不修改输入对象（计算返回新对象）
- 不持有全局状态（除 fin004 缓存）
- 相同输入 → 相同输出（幂等）
- 无副作用（除 fin004 缓存文件读写）

**实现方式**：
- dataclass 存储数据，计算函数返回新 dataclass
- Engine 类使用 `@staticmethod`，无需实例化
- 可变集合（list/dict）操作后返回新集合

### 3.2 模块独立性

- fin001~fin005 互相独立，互不 import
- fin006 可调用 fin002 和 fin005（单向）
- 每个模块可单独测试、单独发布

### 3.3 L4 集成方式

```python
# 方式 1：sys.path 注入（fin-l4 当前方式）
import sys, os
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    '../../L3-business/components/finance-engine'
)))
from fin002_loan import LoanEngine

# 方式 2：services 层直接调用
from services.loan_svc import calculate_loan_schedule
```

### 3.4 缓存机制（fin004 专用）

```
~/.openclaw/cache/fin004_rate/
├── lpr_1y.json
├── lpr_5y.json
└── central_bank_cn.json
```

JSON 结构：
```json
{
  "rate_type": "lpr_1y",
  "rate": "0.0300",
  "effective_date": "2026-09-20",
  "source": "api_ninjas",
  "fetched_at": "2026-09-29T10:00:00"
}
```

### 3.5 Web 演示层

- **框架**：Flask
- **模板**：Jinja2（12 个页面）
- **图表**：Chart.js (CDN)
- **用途**：仅供演示/调试，不作为生产部署
- **入口**：`run_web.py` → Flask app.run()

### 3.6 CLI 层

- 入口：`cli.py`
- 通过 `python -m finance-engine` 调用
- 子命令：`loan calculate`, `insurance irr`, `rate get`, 等

---

## 4. 错误处理

| 场景 | 异常类型 | 说明 |
|---|---|---|
| 交易金额 ≤ 0 | `ValueError` | 金额必须为正 |
| 账户不存在 | `ValueError` | 借贷账户必须预先创建 |
| 贷款期数 ≤ 0 | `ValueError` | 期数必须为正整数 |
| 利率 < 0 | `ValueError` | 利率不能为负 |
| IRR 不收敛 | 返回 `IRRResult(converged=False)` | 超过 200 次迭代 |
| 提前还款金额 > 剩余本金 | `ValueError` | 还款额不能超过剩余本金 |
| 利率 API 失败 | 返回默认值 + is_expired=True | 不抛异常，降级处理 |
| 持仓数量 < 0 | `ValueError` | 数量不能为负 |

### 4.1 降级策略

- fin004 外部 API 不可用时：先读缓存，缓存也没有时返回内置默认值
- 所有计算函数：参数校验失败时抛明确的 ValueError，不静默处理

---

## 5. 设计约束

### 5.1 L3 分层规则

- ✅ 允许：纯计算、数据模型、配置、常量
- ✅ 允许：fin004 的只读外部 API 调用 + 本地缓存
- ❌ 禁止：Web UI 作为生产能力（仅演示）
- ❌ 禁止：持久化用户数据
- ❌ 禁止：import 任何 L4 层代码
- ❌ 禁止：用户认证与权限控制

### 5.2 代码规范

- 模块命名：`fin{编号}_{名称}`
- 编号 3 位，从 001 开始
- 主入口文件：`__init__.py`（模块内所有公开导出）
- 数据类：`@dataclass`，不继承（除了 mixin）
- 引擎类：静态方法为主，不持有状态
