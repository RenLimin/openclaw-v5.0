# L3 家庭及个人理财通用框架 — DESIGN.md

> 本文档是 [ADR-202609-026](../../knowledge-base/by-category/project-experience/adr/ADR-202609-026-personal-finance-framework-L3.md) 的详细设计。
>
> **维护原则**：设计变了 → 改本文档；实现变了 → 验证本文档是否需要更新

## 0. 元信息

| 字段 | 值 |
|---|---|
| 文档版本 | 1.0 (2026-09-03) |
| 文档状态 | active |
| 决策 | ADR-202609-026 (accepted) |
| 层级 | L3 通用业务层 |
| 配套 ADR | ADR-202609-026 |
| 依赖 L2 | 持久化适配(006)、Office 文档生成(011)、知识库工具链(010) |
| 依赖 L1 | Agent Loop、工具执行、记忆、配置管理 |

---

## 1. 定位

### 1.1 L3 理财框架在分层架构中的位置

```
横切关注点
┌─────────────────────────────────────────────────────────────┐
│  L4  专有业务层 — Rex 家庭理财系统 (FIN-L4-PF01)             │
│      继承 L3 引擎 + 灌家庭数据 + 展示报表/建议               │
├─────────────────────────────────────────────────────────────┤
│  L3  通用业务层 ★ 本文件                                     │
│      FIN-001 账户体系                                        │
│      FIN-002 贷款/借款核算                                   │
│      FIN-003 保险产品核算                                    │
│      FIN-004 利率服务                                        │
│      FIN-005 投资持仓核算                                    │
│      FIN-006 理财建议引擎                                    │
├─────────────────────────────────────────────────────────────┤
│  L2  基础设施层 — 持久化/文档生成/知识库/配置/凭据           │
├─────────────────────────────────────────────────────────────┤
│  L1  运行时抽象层 — OpenClaw                                │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

| 原则 | 说明 |
|---|---|
| **引擎模式** | L3 是计算引擎，不持有家庭数据，传入参数即返回结果 |
| **纯函数优先** | 核算逻辑尽量设计为纯函数（输入确定 → 输出确定），便于测试 |
| **契约稳定** | L3 ↔ L4 通过稳定接口通信，接口变更需 ADR |
| **可审计** | 每步计算可追溯、可复现，中间结果可检查 |
| **标注估算** | 所有输出标注"精确值"或"估算值"，保险计算必须标注 |
| **零副作用** | L3 引擎不写数据库、不发网络请求（利率服务除外）、不修改配置 |

---

## 2. L3 ↔ L4 契约

### 2.1 接口定义

```python
# L3 引擎接口（L4 调用方视角）

# ========== FIN-001 账户体系 ==========
def create_account(name, type, currency="CNY", initial_balance=0) -> Account:
def record_transaction(debit_account, credit_account, amount, date, note="") -> Transaction:
def get_account_balance(account_id, as_of_date=None) -> Decimal:
def get_trial_balance(as_of_date=None) -> TrialBalance:
def reconcile_account(account_id, external_statement) -> ReconciliationResult:

# ========== FIN-002 贷款/借款核算 ==========
def create_loan(principal, annual_rate, term_months, method, start_date, name="") -> Loan:
def calculate_amortization_schedule(loan_id) -> AmortizationSchedule:
def calculate_early_payoff(loan_id, extra_payment, payment_date) -> EarlyPayoffResult:
def get_loan_summary(loan_id, as_of_date=None) -> LoanSummary:

# ========== FIN-003 保险产品核算 ==========
def create_policy(policy_type, premium, sum_assured, term_years, payment_years, insured_age, insured_gender) -> Policy:
def calculate_cash_value(policy_id, as_of_year) -> CashValueResult:
def calculate_surrender_value(policy_id, as_of_year) -> SurrenderValueResult:
def calculate_irr(policy_id, as_of_year) -> IRRResult:
def project_dividend(policy_id, rate_scenario="mid") -> DividendProjection:

# ========== FIN-004 利率服务 ==========
def get_current_lpr(term="5y") -> RateSnapshot:
def get_central_bank_rate(country="CN") -> RateSnapshot:
def get_rate_history(rate_type, start_date, end_date) -> List[RateSnapshot]:
def convert_annual_to_monthly(annual_rate) -> Decimal:
def convert_rate(annual_rate, from_period, to_period) -> Decimal:

# ========== FIN-005 投资持仓核算 ==========
def create_portfolio(name, base_currency="CNY") -> Portfolio:
def add_holding(portfolio_id, asset_type, asset_name, shares, cost_basis, current_price) -> Holding:
def update_price(portfolio_id, asset_name, new_price) -> Holding:
def get_portfolio_summary(portfolio_id) -> PortfolioSummary:
def get_asset_allocation(portfolio_id) -> AllocationResult:
def calculate_return(portfolio_id, period="1y") -> ReturnResult:

# ========== FIN-006 理财建议引擎 ==========
def diagnose_financial_health(income, expenses, assets, liabilities, emergency_fund) -> HealthReport:
def suggest_asset_allocation(age, risk_capacity, risk_tolerance, investment_horizon) -> AllocationAdvice:
def optimize_debt_payoff(debts, monthly_budget, strategy="avalanche") -> PayoffPlan:
def analyze_insurance_gap(income, liabilities, existing_coverage, dependents) -> InsuranceGapReport:
def generate_financial_report(portfolio_id, loans, policies, income, expenses) -> FinancialReport:
```

### 2.2 数据契约

```python
# 核心数据类型
from decimal import Decimal
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from datetime import date

class AccountType(Enum):
    ASSET = "asset"           # 资产
    LIABILITY = "liability"   # 负债
    INCOME = "income"         # 收入
    EQUITY = "equity"         # 权益
    EXPENSE = "expense"       # 费用

class LoanMethod(Enum):
    EQUAL_PAYMENT = "equal_payment"       # 等额本息
    EQUAL_PRINCIPAL = "equal_principal"   # 等额本金
    INTEREST_ONLY = "interest_only"       # 先息后本
    FLEXIBLE = "flexible"                 # 随借随还

class InsuranceType(Enum):
    TERM_LIFE = "term_life"               # 定期寿险
    WHOLE_LIFE = "whole_life"             # 终身寿险
    ENDOWMENT = "endowment"               # 两全保险
    CRITICAL_ILLNESS = "critical_illness" # 重疾险
    MEDICAL = "medical"                   # 医疗险
    ANNUITY = "annuity"                   # 年金险
    UNIVERSAL_LIFE = "universal_life"     # 万能险
    TAX_DEFERRED = "tax_deferred"         # 税延养老险

class AssetType(Enum):
    CASH = "cash"                 # 现金/存款
    STOCK = "stock"               # 股票
    FUND = "fund"                 # 基金
    BOND = "bond"                 # 债券
    REAL_ESTATE = "real_estate"   # 房产
    INSURANCE_CV = "insurance_cv" # 保险现金价值
    OTHER = "other"               # 其他
```

---

## 3. 各组件详细设计

### 3.1 FIN-001 账户体系

#### 3.1.1 模型

```
Account（账户）
├── id: str
├── name: str
├── type: AccountType
├── currency: str (ISO 4217, default "CNY")
├── parent_id: Optional[str]  (支持账户树)
├── balance: Decimal
├── created_at: date
└── metadata: dict

Transaction（交易）
├── id: str
├── date: date
├── debit_account_id: str
├── credit_account_id: str
├── amount: Decimal
├── note: str
├── created_at: datetime
└── source: str  (manual / imported / system)

TrialBalance（试算平衡）
├── date: date
├── debit_total: Decimal
├── credit_total: Decimal
├── is_balanced: bool
└── accounts: List[AccountBalance]
```

#### 3.1.2 核心规则

| 规则 | 说明 |
|---|---|
| 复式记账 | 每笔交易借方 = 贷方，否则拒绝入账 |
| 账户树 | 支持多级账户（如"资产 > 流动资产 > 银行存款 > 招行"） |
| 多币种 | 每账户独立币种，报表合并时按汇率折算 |
| 对账 | 账户余额 vs 外部对账单逐笔核对，输出差异 |
| 试算平衡 | 所有账户借方余额 = 贷方余额 |

#### 3.1.3 精度处理

- 所有金额使用 `Decimal` 类型，避免浮点误差
- 舍入规则：`ROUND_HALF_UP`，保留 2 位小数
- 汇率折算：中间精度 6 位，最终结果 2 位

### 3.2 FIN-002 贷款/借款核算

#### 3.2.1 模型

```
Loan（贷款）
├── id: str
├── name: str
├── principal: Decimal          # 本金
├── annual_rate: Decimal        # 年利率
├── term_months: int            # 期限（月）
├── method: LoanMethod          # 还款方式
├── start_date: date            # 起始日
├── remaining_balance: Decimal  # 剩余本金
├── status: LoanStatus
└── metadata: dict

AmortizationEntry（摊销明细）
├── period: int                 # 期数
├── payment_date: date
├── payment: Decimal            # 月供
├── principal: Decimal          # 本金部分
├── interest: Decimal           # 利息部分
├── remaining_balance: Decimal  # 剩余本金
└── cumulative_interest: Decimal # 累计利息

AmortizationSchedule（摊销计划）
├── loan_id: str
├── entries: List[AmortizationEntry]
├── total_payment: Decimal
├── total_interest: Decimal
└── generated_at: datetime
```

#### 3.2.2 计算公式

| 还款方式 | 公式 | 说明 |
|---|---|---|
| **等额本息** | `M = P × [i(1+i)^n] / [(1+i)^n - 1]` | 月供固定，前期利息多 |
| **等额本金** | `M_k = P/n + (P - P×(k-1)/n) × i` | 本金固定，月供递减 |
| **先息后本** | 每月 `M = P × i`，最后一期 `M = P + P × i` | 前期压力小，末期大额 |
| **随借随还** | `利息 = 本金 × 日利率 × 天数` | 按日计息，灵活还款 |

其中：`P` = 本金，`i` = 月利率（年利率/12），`n` = 总期数，`k` = 当前期数

#### 3.2.3 提前还款

```
EarlyPayoffResult
├── original_total_interest: Decimal   # 原总利息
├── new_total_interest: Decimal        # 新总利息
├── interest_saved: Decimal            # 节省利息
├── new_schedule: AmortizationSchedule # 新摊销计划
└── break_even_months: Optional[int]   # 回本月数（如有手续费）
```

- 支持部分提前还款（缩短期限 or 减少月供）
- 支持全额提前还款
- 考虑提前还款手续费（参数化）

#### 3.2.4 利率联动

- 浮动利率贷款可绑定 FIN-004 利率源
- 利率变更时自动重算剩余期数的月供
- 固定利率贷款不受影响

### 3.3 FIN-003 保险产品核算

#### 3.3.1 模型

```
Policy（保单）
├── id: str
├── policy_number: str          # 保单号
├── policy_type: InsuranceType
├── product_name: str           # 产品名称
├── sum_assured: Decimal        # 保额
├── annual_premium: Decimal     # 年保费
├── term_years: int             # 保障期限
├── payment_years: int          # 缴费期限
├── start_date: date
├── insured_name: str
├── insured_age: int
├── insured_gender: str
├── status: PolicyStatus
└── metadata: dict              # 产品特有参数

CashValueResult（现金价值）
├── policy_id: str
├── as_of_year: int
├── guaranteed_cv: Decimal      # 保证现金价值
├── non_guaranteed_cv: Decimal  # 非保证现金价值（中档演示）
├── total_cv: Decimal           # 合计
├── is_estimate: bool           # 是否估算
└── disclaimer: str             # 免责声明

SurrenderValueResult（退保价值）
├── policy_id: str
├── as_of_year: int
├── surrender_value: Decimal
├── surrender_fee: Decimal
├── is_estimate: bool
└── disclaimer: str

IRRResult（内部收益率）
├── policy_id: str
├── as_of_year: int
├── irr: Decimal                # 年化 IRR
├── calculation_method: str     # "newton" / "bisection"
├── converged: bool
├── is_estimate: bool
└── disclaimer: str
```

#### 3.3.2 计算逻辑

**现金价值**：
```
CV(t) = Σ[k=1 to t] (premium_k - expense_k - risk_premium_k) + accumulated_interest(t)

其中：
- expense_k = 初始费用（首年高，后续低）+ 管理费
- risk_premium = 保障成本（按险种费率表）
- accumulated_interest = 累积红利/利息（按演示利率）
```

**退保价值**：
```
SV(t) = CV(t) × (1 - surrender_fee_rate(t))

surrender_fee_rate:
- 年 1: 5%（或不可退保）
- 年 2: 4%
- 年 3: 3%
- 年 4: 2%
- 年 5+: 0%
```

**IRR 计算**（牛顿迭代法）：
```
现金流: [-P1, -P2, -P3, ..., -Pn, +CV(n)]
求解 IRR: Σ[t=0 to n] CF_t / (1+IRR)^t = 0

迭代: r_{k+1} = r_k - f(r_k) / f'(r_k)
收敛: |r_{k+1} - r_k| < 1e-8
```

**红利演示**（三档）：
| 档 | 演示利率 | 说明 |
|---|---|---|
| 低档 | 2.5% | 保守估计 |
| 中档 | 4.5% | 基准估计 |
| 高档 | 6.0% | 乐观估计 |

#### 3.3.3 险种差异

| 险种 | 现金价值 | 退保 | IRR | 特殊 |
|---|---|---|---|---|
| 定期寿险 | ❌ | ❌ | ❌ | 纯保障 |
| 终身寿险 | ✅ | ✅ | ✅ | 终身保障+储蓄 |
| 两全保险 | ✅ | ✅ | ✅ | 生存/身故都赔 |
| 重疾险 | ✅（部分） | ✅ | ✅ | 含轻症/中症 |
| 医疗险 | ❌ | ❌ | ❌ | 消费型 |
| 年金险 | ✅ | ✅ | ✅ | 定期领取 |
| 万能险 | ✅ | ✅ | ✅ | 保底+结算利率 |
| 税延养老险 | ✅ | ✅ | ✅ | A/B/C 三类 |

#### 3.3.4 免责声明

所有保险计算输出必须包含：
```
⚠️ 本计算为估算值，基于标准精算假设。
实际价值以保险公司出具的保单现金价值表为准。
演示红利非保证，实际分红可能低于演示。
```

### 3.4 FIN-004 利率服务

#### 3.4.1 模型

```
RateSnapshot（利率快照）
├── rate_type: str             # "lpr_1y" / "lpr_5y" / "central_bank_cn" / ...
├── rate: Decimal              # 利率值（%）
├── effective_date: date       # 生效日期
├── source: str                # 数据来源
├── fetched_at: datetime       # 获取时间
└── metadata: dict             # 额外信息

RateHistory（利率历史）
├── rate_type: str
├── rates: List[RateSnapshot]
├── start_date: date
└── end_date: date
```

#### 3.4.2 数据源

| 优先级 | 数据源 | 覆盖 | 方式 | 成本 |
|---|---|---|---|---|
| 1 | API Ninjas | 22 国央行 + 基准利率 | REST API | 免费额度 10K/月 |
| 2 | Trading Economics | 全球宏观指标 | REST API | 付费（有免费层） |
| 3 | 央行/银行官网 | LPR、基准利率 | 爬虫 | 免费 |

#### 3.4.3 利率类型

| 类型 | 标识 | 说明 |
|---|---|---|
| LPR 1 年期 | `lpr_1y` | 1 年期贷款市场报价利率 |
| LPR 5 年期+ | `lpr_5y` | 5 年期以上 LPR（房贷参考） |
| 央行基准利率 | `central_bank_cn` | 中国人民银行基准利率 |
| 存款基准利率 | `deposit_base_cn` | 各期限存款基准 |
| 商业银行利率 | `bank_prime_{bank}` | 各银行实际执行利率 |
| SHIBOR | `shibor_{period}` | 上海银行间同业拆放利率 |
| SOFR | `sofr` | 担保隔夜融资利率（国际参考） |

#### 3.4.4 获取策略

```
获取流程：
1. 检查本地缓存（TTL=24h）
2. 缓存命中 → 直接返回
3. 缓存未命中 → 调用 API Ninjas
4. API 失败 → 尝试 Trading Economics
5. 全部失败 → 返回最近一次缓存（标注"过期"）
6. 更新缓存 + 记录获取日志
```

#### 3.4.5 利率转换

| 转换 | 公式 |
|---|---|
| 年→月 | `r_monthly = (1 + r_annual)^(1/12) - 1` |
| 年→日 | `r_daily = (1 + r_annual)^(1/365) - 1` |
| 月→年 | `r_annual = (1 + r_monthly)^12 - 1` |
| 日→年 | `r_annual = (1 + r_daily)^365 - 1` |

> 注意：金融场景中有时用简单除法（`r_monthly = r_annual / 12`），本引擎同时支持两种模式，默认复利换算。

### 3.5 FIN-005 投资持仓核算

#### 3.5.1 模型

```
Portfolio（投资组合）
├── id: str
├── name: str
├── base_currency: str
├── created_at: date
└── metadata: dict

Holding（持仓）
├── id: str
├── portfolio_id: str
├── asset_type: AssetType
├── asset_name: str
├── asset_code: str             # 代码（如 000001.SZ / 110011）
├── shares: Decimal             # 份额
├── avg_cost: Decimal           # 平均成本
├── current_price: Decimal      # 当前价格
├── updated_at: datetime
└── metadata: dict

PortfolioSummary（组合摘要）
├── portfolio_id: str
├── total_value: Decimal        # 总市值
├── total_cost: Decimal         # 总成本
├── total_gain: Decimal         # 总盈亏
├── total_return_pct: Decimal   # 总收益率
├── holdings: List[HoldingSummary]
└── generated_at: datetime

AllocationResult（资产配置）
├── by_asset_type: Dict[AssetType, Decimal]     # 按资产类型
├── by_risk_level: Dict[str, Decimal]            # 按风险等级
├── concentration_risk: Dict[str, Decimal]        # 集中度风险
└── rebalancing_suggestion: Optional[List]
```

#### 3.5.2 计算逻辑

| 指标 | 公式 |
|---|---|
| 持仓市值 | `shares × current_price` |
| 浮动盈亏 | `shares × (current_price - avg_cost)` |
| 收益率 | `(current_price - avg_cost) / avg_cost × 100%` |
| 组合总收益 | `Σ(持仓市值) - Σ(持仓成本)` |
| 年化收益率 | `(1 + total_return)^(365/holding_days) - 1` |
| 资产配置比 | `某类资产市值 / 总市值 × 100%` |

#### 3.5.3 资产类型

| 类型 | 风险等级 | 流动性 | 说明 |
|---|---|---|---|
| 现金/存款 | 低 | 高 | 活期/定期/货币基金 |
| 债券 | 低-中 | 中 | 国债/企业债/债基 |
| 基金 | 中-高 | 高 | 指数/主动/ETF/LOF/QDII |
| 股票 | 高 | 高 | A 股/港股/美股 |
| 房产 | 中 | 低 | 投资性房产 |
| 保险现金价值 | 低 | 低 | 来自 FIN-003 |
| 其他 | 不定 | 不定 | 黄金/数字货币/P2P |

#### 3.5.4 再平衡

```
再平衡触发条件：
1. 日历触发：每 6 个月或 12 个月
2. 漂移触发：某类资产偏离目标 ≥ 5 个百分点

再平衡建议：
- 输出：当前配比 vs 目标配比 vs 调整量
- 考虑：交易成本、税收影响、市场时机（不预测）
```

### 3.6 FIN-006 理财建议引擎

#### 3.6.1 模型

```
HealthReport（健康报告）
├── overall_score: int                    # 0-100
├── kpi_scores: Dict[str, KPIResult]      # 各 KPI 评分
├── strengths: List[str]                  # 优势
├── weaknesses: List[str]                 # 不足
├── recommendations: List[Recommendation] # 改进建议
└── generated_at: datetime

KPIResult（KPI 结果）
├── name: str
├── value: Decimal
                                # 实际值
├── benchmark: Decimal                    # 基准值
├── status: str                           # "good" / "warning" / "danger"
└── suggestion: str

AllocationAdvice（配置建议）
├── risk_level: str                       # "conservative" / "moderate" / "aggressive"
├── target_allocation: Dict[AssetType, Decimal]
├── current_allocation: Dict[AssetType, Decimal]
├── adjustment_needed: List[Adjustment]
└── rationale: str

PayoffPlan（还款计划）
├── strategy: str                         # "avalanche" / "snowball" / "hybrid"
├── total_interest: Decimal
├── total_months: int
├── interest_saved_vs_minimum: Decimal
├── schedule: List[PayoffStep]
└── rationale: str

InsuranceGapReport（保障缺口）
├── life_insurance_gap: Decimal           # 寿险缺口
├── critical_illness_gap: Decimal         # 重疾缺口
├── medical_insurance_gap: Decimal        # 医疗缺口
├── total_annual_premium_budget: Decimal  # 建议保费预算
└── recommendations: List[Recommendation]
```

#### 3.6.2 财务健康 KPI

| KPI | 公式 | 良好 | 警告 | 危险 |
|---|---|---|---|---|
| 储蓄率 | 月储蓄/月收入 | ≥20% | 10-20% | <10% |
| 负债收入比(DTI) | 月还款/月收入 | ≤36% | 36-50% | >50% |
| 流动性比率 | 流动资产/月支出 | ≥6月 | 3-6月 | <3月 |
| 应急储备 | 应急资金/月支出 | ≥6月 | 3-6月 | <3月 |
| 净资产增长率 | (本期-上期)/上期 | >0% | 0% | <0% |
| 投资多样化 | 单一资产占比 | ≤25% | 25-40% | >40% |

#### 3.6.3 资产配置建议

**风险等级评估**（双维度）：

| 维度 | 评分项 | 1-5 分 |
|---|---|---|
| **Risk Capacity**（数学） | 时间 horizon / 收入稳定性 / 应急储备 / 负债负担 | 1=低, 5=高 |
| **Risk Tolerance**（情绪） | 对下跌反应 / 熊市买入意愿 / 稳定性需求 | 1=低, 5=高 |

取**较低分**作为实际风险等级。

**配置映射**：

| 风险等级 | 股票 | 债券 | 现金 | 其他 |
|---|---|---|---|---|
| 保守 (1-2) | 30-50% | 40-55% | 10-15% | 0-5% |
| 稳健 (3) | 55-70% | 25-35% | 5-10% | 0-5% |
| 积极 (4-5) | 75-90% | 10-20% | 0-5% | 0-5% |

**年龄调整**（Rule of 110）：
```
股票% = 110 - 年龄
债券% = 100 - 股票%
```

#### 3.6.4 债务优化

| 策略 | 排序依据 | 优点 | 缺点 |
|---|---|---|---|
| Avalanche | 利率从高到低 | 省利息总额 | 可能长期无进展感 |
| Snowball | 余额从小到大 | 心理激励 | 总利息可能更多 |
| Hybrid | 高息小额优先 | 兼顾两者 | 逻辑较复杂 |

输出：两种策略对比（总利息/总月数/心理激励度），让用户选择。

#### 3.6.5 保障缺口分析

```
寿险保额建议 = 年收入 × 10 + 总负债 - 流动资产
重疾险保额建议 = 年收入 × 3 + 医疗备用金(30万)
医疗险 = 根据已有保障评估（社保/百万医疗/高端医疗）
总保费预算建议 = 年收入 × 10-15%
```

---

## 4. 与现有系统的关系

### 4.1 L2 依赖

| L2 组件 | 使用方式 | 说明 |
|---|---|---|
| 持久化适配 (006) | SQLite 存储交易/持仓/贷款/保单 | Repository 模式 |
| Office 文档生成 (011) | 生成 Excel 报表/Word 分析报告 | openpyxl / python-docx |
| 知识库工具链 (010) | 理财知识 Markdown 索引/查询 | kb_index.py |
| 配置管理 (007) | 利率 API Key、计算参数配置 | config.sh |
| 凭据管理 (005) | 利率 API Key 安全存储 | SecretRef |

### 4.2 避免系统冲突

| 冲突点 | 规避措施 |
|---|---|
| 新建 cron | ❌ 不建 cron。利率获取由 L4 触发或手动调用 |
| 运行时配置 | ❌ 不改 openclaw.json。配置走 config.sh 治理通道 |
| 端口占用 | ❌ 不启动任何服务。纯计算引擎，无监听 |
| 数据库冲突 | ✅ 使用独立 SQLite 表前缀 `fin_`，不与现有表冲突 |
| 工具注册 | ❌ 不注册新工具。以 Python 库形式提供，L4 通过 skill 调用 |

### 4.3 知识库配套

| 知识文档 | 路径 | 说明 |
|---|---|---|
| 贷款核算方法 | `knowledge-base/by-category/industry/loan-amortization.md` | PMT 公式/摊销表/提前还款 |
| 保险产品精算 | `knowledge-base/by-category/industry/insurance-valuation.md` | 现金价值/IRR/红利演示 |
| 资产配置理论 | `knowledge-base/by-category/industry/asset-allocation.md` | 标准普尔/Rule of 100/再平衡 |
| 债务优化策略 | `knowledge-base/by-category/industry/debt-optimization.md` | 雪崩/雪球/混合 |
| 财务健康指标 | `knowledge-base/by-category/industry/financial-health-kpi.md` | 6 KPI + 基准 |

---

## 5. 实施计划

### P0 架构（当前）
- [x] ADR-026 创建
- [x] DESIGN.md 编写
- [ ] 架构 v3.0 同步

### P1 核心引擎
- [x] FIN-001 账户体系（复式记账 + 试算平衡 + 对账）— ✅ 已实现 + 测试通过
- [x] FIN-002 贷款/借款核算（4 种还款方式 + 提前还款）— ✅ 已实现 + 测试通过

### P2 保险+利率
- [ ] FIN-003 保险产品核算（现金价值/退保/IRR/红利演示）
- [ ] FIN-004 利率服务（API Ninjas + 缓存 + 利率转换）

### P3 投资+建议
- [ ] FIN-005 投资持仓核算（持仓/收益/资产配置/再平衡）
- [ ] FIN-006 理财建议引擎（健康诊断/资产配置/债务优化/保障缺口）

### P4 L4 实例
- [ ] FIN-L4-PF01 Rex 家庭理财系统
- [ ] 数据导入（手动 + CSV）
- [ ] 报表输出（Excel/Word）
- [ ] 理财建议生成

---

## 6. 验证标准

| 阶段 | 验证项 | 方法 |
|---|---|---|
| P1 | 复式记账平衡 | 试算平衡 = 0 |
| P1 | 贷款摊销正确 | 对比银行标准还款计划 |
| P2 | 保险 IRR 收敛 | 对比 Excel IRR() 函数 |
| P2 | 利率获取成功 | API 调用 + 缓存命中 |
| P3 | 投资组合收益 | 对比手动计算 |
| P3 | 建议逻辑合理 | 3 个典型家庭案例测试 |
| P4 | 端到端 | 灌数据 → 出报表 → 出建议 |

---

## 7. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-03 | 1.1 | P1 核心引擎落地：FIN-001 + FIN-002 实现 + 20 测试通过 + 端到端验证 |
| 2026-09-03 | 1.0 | 初版（6 个 FIN 组件 + L4 契约 + 实施计划） |
