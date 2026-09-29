# DESIGN-OUTLINE - finance-engine v1.0

> **版本**: v1.0  
> **层级**: L3 通用业务层  
> **组件**: finance-engine  
> **最后更新**: 2026-09-29

---

## 1. 架构定位

```
┌─────────────────────────────────────┐
│  L4 专有业务层                        │
│  (fin-l4 家庭理财 / 保险工具 / ...)    │
└────────────┬────────────────────────┘
             │ import (单向依赖)
             ▼
┌─────────────────────────────────────┐
│  L3 通用业务层 — finance-engine       │
│  复式记账 · 贷款 · 保险 · 利率         │
│  投资组合 · 理财建议                   │
└────────────┬────────────────────────┘
             │ 依赖
             ▼
┌─────────────────────────────────────┐
│  L2 基础设施层                        │
│  持久化 · 精度计算 · 可观测性          │
└─────────────────────────────────────┘
```

**核心定位**：纯函数式理财计算引擎库——给数据就出结果，不存数据、不做 UI、不碰权限。

---

## 2. 总体架构

### 2.1 模块结构

```
finance-engine/
├── fin001_account/            # 复式记账引擎
│   └── __init__.py            #   Account, Transaction, AccountingEngine
├── fin002_loan/               # 贷款/借款核算
│   └── __init__.py            #   Loan, AmortizationSchedule, LoanEngine
├── fin003_insurance/          # 保险产品核算
│   └── __init__.py            #   InsurancePolicy, InsuranceEngine, IRR
├── fin004_rate/               # 利率服务（唯一允许 IO）
│   └── __init__.py            #   RateEngine, LPR, 利率转换, 本地缓存
├── fin005_portfolio/          # 投资持仓核算
│   └── __init__.py            #   Portfolio, Holding, PortfolioEngine
├── fin006_advisor/            # 理财建议引擎
│   └── __init__.py            #   AdvisorEngine, KPI诊断, 资产配置, 债务优化
├── core/                       # 内部基础设施
│   ├── db/repositories.py     #   仓储基类（供 L4 注入数据）
│   ├── external/               #   外部数据源
│   │   ├── base.py            #     外部源基类
│   │   └── fx_source.py       #     外汇数据源
│   └── security/              #   安全模块
├── services/                   # 业务服务层（L4 直接调用）
│   ├── account_svc.py
│   ├── loan_svc.py
│   ├── insurance_svc.py
│   ├── rate_svc.py
│   ├── portfolio_svc.py
│   ├── advise_svc.py
│   ├── txn_svc.py
│   ├── category_engine.py
│   ├── budget_svc.py
│   ├── import_svc.py
│   ├── export_svc.py
│   └── report_svc.py
├── web/                        # 独立 Web 演示
│   ├── main.py                #   Flask 入口
│   ├── api.py                 #   REST API
│   ├── templates/             #   Jinja2 模板（12 页面）
│   └── static/                #   静态资源
├── integration/                # L4 集成辅助
│   └── links.py               #   L4 → L3 链接管理
├── config.py                   # 全局配置
├── cli.py                      # 命令行入口
├── load_demo_data.py          # 演示数据加载
├── run_web.py                  # Web 启动脚本
├── requirements.txt            # 依赖清单
└── tests/                      # 单元测试
```

### 2.2 架构风格

- **纯函数式核心**：fin001~fin006 六大引擎为纯函数，输入 → 计算 → 输出
- **模块独立**：每个 fin00x 可单独使用，互不依赖（fin006 可能调用其他模块做综合分析）
- **数据模型不可变**：dataclass 承载数据，计算返回新对象，不修改输入
- **Decimal 精度**：所有金额、利率使用 `decimal.Decimal`，避免浮点误差
- **服务层薄封装**：services/ 层编排多个引擎，提供面向业务的组合接口
- **唯一 IO 例外**：fin004_rate 含本地文件缓存，是全组件唯一允许的副作用

---

## 3. 模块划分与职责

### 3.1 六大核心引擎

| 模块 | 职责 | 核心类/函数 | 依赖 |
|---|---|---|---|
| `fin001_account` | 复式记账：账户体系、借贷分录、科目余额、试算平衡 | Account, Transaction, AccountingEngine | 无（基础设施层） |
| `fin002_loan` | 贷款核算：4 种还款方式 + 提前还款 + 摊销表 | Loan, AmortizationSchedule, LoanEngine | 无 |
| `fin003_insurance` | 保险测算：8 险种 + 现金价值 + IRR + 红利演示 | InsurancePolicy, InsuranceEngine, IRR 迭代 | 无 |
| `fin004_rate` | 利率服务：LPR/基准利率 + 利率转换 + 本地缓存（TTL 24h） | RateEngine, RateSnapshot | 外部 API（唯一 IO） |
| `fin005_portfolio` | 投资组合：持仓管理 + 收益计算 + 资产配置 + 再平衡 | Portfolio, Holding, PortfolioEngine | 无 |
| `fin006_advisor` | 理财建议：6 KPI 诊断 + 资产配置建议 + 债务优化 + 综合报告 | AdvisorEngine, KPIResult | fin002, fin005 |

### 3.2 支撑模块

| 模块 | 职责 |
|---|---|
| `core/` | 内部基础设施：仓储基类、外部数据源、安全模块 |
| `services/` | 业务服务层，面向 L4 的组合接口（12 个 service） |
| `web/` | 独立 Web 演示（Flask + Jinja2 + Chart.js），仅供演示/调试 |
| `integration/` | L4 集成辅助工具 |
| `cli.py` | 命令行接口 |
| `config.py` | 全局配置 |

### 3.3 模块间依赖规则

```
fin001  fin002  fin003  fin004  fin005
  │       │       │       │       │
  └───────┴───────┴───┬───┴───────┘
                      ▼
                   fin006  (综合分析，依赖 002/005)
                      │
                      ▼
                  services/  (业务编排)
                      │
                      ▼
                   L4 业务层
```

**规则**：
- fin001~fin005 互相独立，互不 import
- fin006 可调用 fin002、fin005 做综合分析（单向依赖）
- services/ 层编排多个引擎，提供面向业务的组合接口
- 所有模块不依赖 L4 层代码

---

## 4. 核心数据流

### 4.1 计算数据流（典型场景）

```
L4 Service 调用
    │
    │ 1. 构造输入 dataclass（如 Loan 对象）
    ▼
finance-engine Service 层
    │
    │ 2. 校验输入，调用对应引擎
    ▼
Core Engine (纯函数)
    │
    │ 3. 执行计算（Decimal 精度）
    ▼
返回结果 dataclass
```

### 4.2 贷款计算流程

```
输入: Loan(principal, rate, term, method, start_date)
    │
    ▼
LoanEngine.calculate_schedule()
    ├─ 等额本息 → 公式计算月供 → 逐期摊销
    ├─ 等额本金 → 每月本金固定 → 利息递减
    ├─ 先息后本 → 每月利息 → 期末还本金
    └─ 随借随还 → 按日计息 → 灵活还款
    │
    ▼
输出: AmortizationSchedule(entries[], total_payment, total_interest)
```

### 4.3 保险 IRR 计算流程

```
输入: 现金流数组 [premium, benefit, ...]
    │
    ▼
InsuranceEngine.calculate_irr()
    ├─ 牛顿迭代法
    ├─ 初始猜测 3%
    ├─ 收敛条件: 1e-8
    └─ 最大迭代: 200 次
    │
    ▼
输出: IRR 值 (Decimal)
```

### 4.4 利率服务流程

```
请求: get_lpr("1y")
    │
    ├─ 检查本地缓存
    │   ├─ 命中且未过期 → 返回缓存
    │   └─ 未命中/已过期 → 继续
    │
    ▼
请求外部 API
    │
    ├─ 成功 → 写入缓存 → 返回
    └─ 失败 → 返回默认值 + 标记 is_expired
    │
    ▼
输出: RateSnapshot(rate, effective_date, source, is_cached)
```

---

## 5. 数据模型大纲

### 5.1 设计原则

- 全部使用 `@dataclass`，轻量快速
- 金额字段使用 `Decimal`，构造时自动转换 + quantize 到 2 位小数
- 利率使用 `Decimal`，保持高精度（不 quantize）
- 模型纯数据，不含业务逻辑（计算逻辑在 Engine 类/函数中）

### 5.2 核心数据模型

| 模块 | 模型 | 关键字段 |
|---|---|---|
| fin001 | `Account` | id, name, type(asset/liability/income/equity/expense), currency, balance |
| fin001 | `Transaction` | id, date, debit_account_id, credit_account_id, amount, note |
| fin001 | `AccountBalance` | account_id, debit_balance, credit_balance, net_balance |
| fin002 | `Loan` | id, principal, annual_rate, term_months, method, start_date, remaining_balance |
| fin002 | `AmortizationEntry` | period, payment_date, payment, principal, interest, remaining_balance |
| fin002 | `AmortizationSchedule` | loan_id, entries[], total_payment, total_interest |
| fin003 | `InsurancePolicy` | id, type, premium, sum_assured, term, payment_period, status |
| fin003 | `CashValueRow` | policy_year, premium_paid, sum_at_risk, cash_value, surrender_value |
| fin003 | `DividendDemo` | year, low, mid, high, cumulative_low/mid/high |
| fin004 | `RateSnapshot` | rate_type, rate, effective_date, source, fetched_at, is_cached |
| fin004 | `RateHistory` | rate_type, snapshots[] |
| fin005 | `Holding` | id, asset_type, name, quantity, cost_price, current_price, market_value |
| fin005 | `Portfolio` | id, name, holdings[], total_cost, total_market_value, total_pnl |
| fin005 | `AllocationItem` | asset_type, value, percentage, target_percentage, drift |
| fin006 | `KPIResult` | kpi_name, value, status(good/warning/danger), benchmark, unit |
| fin006 | `AdviceReport` | kpis[], allocation_advice, debt_advice, insurance_gap, summary |

---

## 6. 对外接口

### 6.1 核心引擎接口

```python
# fin001 — 复式记账
class AccountingEngine:
    def create_account(...) -> Account
    def record_transaction(...) -> Transaction
    def get_balance(account_id) -> AccountBalance
    def trial_balance() -> List[AccountBalance]  # 试算平衡

# fin002 — 贷款
class LoanEngine:
    def calculate_schedule(loan: Loan) -> AmortizationSchedule
    def prepay(loan: Loan, amount: Decimal, date: date) -> AmortizationSchedule
    def compare_methods(...) -> Dict[LoanMethod, AmortizationSchedule]

# fin003 — 保险
class InsuranceEngine:
    def cash_value(policy, year: int) -> Decimal
    def surrender_value(policy, year: int) -> Decimal
    def calculate_irr(cash_flows: List[Decimal]) -> Decimal
    def dividend_demo(policy, years: int) -> DividendDemo

# fin004 — 利率
class RateEngine:
    def get_lpr(term: str = "1y") -> RateSnapshot
    def get_central_bank_rate(country: str, rate_type: str) -> RateSnapshot
    def convert_rate(rate, from_period, to_period, compound: bool) -> Decimal

# fin005 — 投资组合
class PortfolioEngine:
    def add_holding(portfolio, holding: Holding) -> Portfolio
    def calculate_pnl(portfolio) -> Portfolio  # 浮动盈亏
    def allocation(portfolio) -> List[AllocationItem]
    def rebalance_advice(portfolio, target_alloc) -> List[Trade]

# fin006 — 理财建议
class AdvisorEngine:
    def diagnose_kpis(financial_data) -> List[KPIResult]
    def allocation_advice(risk_level, age) -> AllocationTarget
    def debt_optimize(debts, strategy) -> DebtPayoffPlan
    def full_report(financial_data) -> AdviceReport
```

### 6.2 Service 层接口

services/ 层提供更面向业务的组合接口，L4 层通常直接调用 service 而非底层 engine。

---

## 7. 非功能设计

### 7.1 性能

| 操作 | 预期性能 |
|---|---|
| 贷款 30 年期摊销表（360 期） | < 5ms |
| 保险 IRR 计算（20 年期） | < 10ms |
| 试算平衡（100 账户） | < 1ms |
| 投资组合收益计算（100 持仓） | < 5ms |
| 综合理财报告 | < 50ms |

### 7.2 精度

- 金额：`Decimal`，2 位小数，`ROUND_HALF_UP`
- 利率：`Decimal`，保留原始精度（不 truncate）
- IRR：收敛精度 `1e-8`，最大 200 次迭代
- 比率/百分比：`Decimal`，4 位小数

### 7.3 可扩展性

- 新增还款方式：扩展 `LoanMethod` 枚举 + 新增计算函数
- 新增险种：扩展 `InsuranceType` 枚举 + 新增测算方法
- 新增 KPI：扩展 `KPI_BENCHMARKS` + 新增诊断函数
- 新增利率源：实现新的数据源类，接入 RateEngine

### 7.4 可测试性

- 纯函数设计：给定输入必有确定输出，测试用例好写
- 无外部依赖（除 fin004）：无需 mock 即可测试核心计算
- 数据驱动：测试用例用表格化输入输出

### 7.5 安全

- fin004 外部 API：仅读操作，不写数据
- 本地缓存：JSON 文件，权限 600
- 无用户数据持久化（L4 负责）

---

## 8. 依赖关系

### 8.1 外部依赖

| 依赖 | 用途 |
|---|---|
| Python 3.10+ | 运行时 |
| decimal (stdlib) | 高精度计算 |
| Flask（可选） | Web 演示 |
| requests（可选） | fin004 外部 API 调用 |
| Chart.js（CDN） | Web 演示图表 |

### 8.2 下游调用方

| 调用方 | 用途 |
|---|---|
| fin-l4 (L4 家庭理财) | 全部 6 大引擎 + services 层 |
| 未来 L4 保险工具 | fin003 保险测算引擎 |
| 未来 L4 贷款计算器 | fin002 贷款核算引擎 |

---

## 9. 演进方向

1. **新增模块**：税务引擎（fin007）、退休规划（fin008）
2. **性能优化**：批量计算接口、计算结果缓存
3. **精度提升**：引入更多金融数学模型（Monte Carlo 模拟、Black-Scholes）
4. **标准化发布**：独立 PyPI 包，供外部项目使用
5. **多语言 SDK**：JavaScript / TypeScript 版本
6. **保险精算深化**：更完整的精算模型，支持更多险种
