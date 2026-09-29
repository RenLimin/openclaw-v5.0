# OPERATIONS - finance-engine v1.0

> **版本**: v1.0  
> **组件**: finance-engine  
> **层级**: L3 通用业务层  
> **最后更新**: 2026-09-29

---

## 1. 安装与初始化

### 1.1 环境要求

| 依赖 | 最低版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 需要 match / 新 typing |
| decimal (stdlib) | - | 高精度计算 |
| Flask | 2.0+ | Web 演示（可选） |
| requests | 2.0+ | fin004 外部 API（可选） |
| Chart.js (CDN) | - | Web 演示图表 |

### 1.2 安装步骤

```bash
# 1. 确认 Python 版本
python3 --version  # 需 >= 3.10

# 2. 安装依赖（如需 Web 演示）
pip install -r L3-business/components/finance-engine/requirements.txt

# 3. 验证组件位置
ls L3-business/components/finance-engine/
# 预期: fin001_account/ fin002_loan/ ... services/ web/ ...
```

### 1.3 L4 层接入

在 L4 业务层通过 sys.path 注入后 import：

```python
import sys
import os

# 将 L3 组件加入 Python 路径
sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    '../../L3-business/components/finance-engine'
)))

# 导入需要的模块
from fin002_loan import LoanEngine, Loan, LoanMethod
from fin003_insurance import InsuranceEngine, InsurancePolicy
from services.loan_svc import calculate_loan_schedule
```

> **注意**：确保单向依赖（L4 → L3），L3 代码中不 import 任何 L4 模块。

### 1.4 Web 演示启动

```bash
cd L3-business/components/finance-engine
python run_web.py
# 访问 http://localhost:5000
```

### 1.5 CLI 使用

```bash
cd L3-business/components/finance-engine
python cli.py loan calculate --principal 1000000 --rate 0.042 --term 360 --method equal_payment
python cli.py insurance irr --premium 10000 --years 20 --benefit 300000
python cli.py rate get --type lpr_1y
```

---

## 2. 快速上手

### 2.1 贷款计算

```python
from fin002_loan import LoanEngine, Loan, LoanMethod
from decimal import Decimal
from datetime import date

# 创建贷款
loan = Loan(
    id="loan-001",
    name="首套房贷",
    principal=Decimal("1000000"),
    annual_rate=Decimal("0.042"),
    term_months=360,
    method=LoanMethod.EQUAL_PAYMENT,
    start_date=date(2026, 10, 1),
)

# 计算还款计划
schedule = LoanEngine.calculate_schedule(loan)

print(f"月供: {schedule.entries[0].payment} 元")
print(f"总还款: {schedule.total_payment} 元")
print(f"总利息: {schedule.total_interest} 元")
print(f"期数: {len(schedule.entries)} 期")

# 查看前 3 期
for entry in schedule.entries[:3]:
    print(f"第{entry.period}期: {entry.payment_date} "
          f"月供={entry.payment} 本金={entry.principal} 利息={entry.interest}")

# 对比 4 种还款方式
comparison = LoanEngine.compare_methods(
    principal=Decimal("1000000"),
    annual_rate=Decimal("0.042"),
    term_months=360,
    start_date=date(2026, 10, 1),
)
for method, info in comparison.items():
    print(f"{method}: 总利息={info['total_interest']}")
```

### 2.2 提前还款测算

```python
from fin002_loan import LoanEngine, Loan, LoanMethod
from decimal import Decimal
from datetime import date

loan = Loan(
    id="loan-001",
    name="提前还款测试",
    principal=Decimal("1000000"),
    annual_rate=Decimal("0.042"),
    term_months=360,
    method=LoanMethod.EQUAL_PAYMENT,
    start_date=date(2026, 10, 1),
)

# 还款 5 年后（第 60 期）提前还 20 万，缩短期限
result = LoanEngine.prepay(
    loan,
    prepay_amount=Decimal("200000"),
    prepay_date=date(2031, 10, 1),  # 5 年后
    method="reduce_term",          # reduce_term / reduce_payment
)

print(f"原总利息: {result.original_schedule.total_interest}")
print(f"新总利息: {result.new_schedule.total_interest}")
print(f"节省利息: {result.interest_saved}")
print(f"缩短后期数: {result.new_term_months} 期")
```

### 2.3 保险 IRR 计算

```python
from fin003_insurance import InsuranceEngine
from decimal import Decimal

# 现金流：负=支出（保费），正=收入（领取/赔付）
# 示例：年交 1 万 × 10 年，第 20 年末领 20 万
cash_flows = []
for year in range(10):
    cash_flows.append(Decimal("-10000"))     # 前 10 年交保费
for year in range(10):
    cash_flows.append(Decimal("0"))          # 第 11-19 年 0
cash_flows.append(Decimal("200000"))         # 第 20 年领 20 万

result = InsuranceEngine.calculate_irr(cash_flows)
print(f"IRR: {result.irr * 100:.4f}%")
print(f"迭代次数: {result.iterations}")
print(f"是否收敛: {result.converged}")
```

### 2.4 投资组合核算

```python
from fin005_portfolio import PortfolioEngine, Portfolio, Holding, AssetType
from decimal import Decimal

# 创建组合
portfolio = Portfolio(id="port-001", name="我的投资组合")

# 添加持仓
portfolio = PortfolioEngine.add_holding(portfolio, Holding(
    id="h001", portfolio_id="port-001",
    asset_type=AssetType.STOCK, name="贵州茅台", code="600519",
    quantity=Decimal("100"), cost_price=Decimal("1800"), current_price=Decimal("1650"),
))
portfolio = PortfolioEngine.add_holding(portfolio, Holding(
    id="h002", portfolio_id="port-001",
    asset_type=AssetType.FUND, name="易方达蓝筹", code="005827",
    quantity=Decimal("10000"), cost_price=Decimal("2.5"), current_price=Decimal("2.3"),
))
portfolio = PortfolioEngine.add_holding(portfolio, Holding(
    id="h003", portfolio_id="port-001",
    asset_type=AssetType.BOND, name="国债ETF", code="511010",
    quantity=Decimal("5000"), cost_price=Decimal("100"), current_price=Decimal("102"),
))

# 收益概览
print(f"总成本: {portfolio.total_cost}")
print(f"总市值: {portfolio.total_market_value}")
print(f"总盈亏: {portfolio.total_pnl}")
print(f"收益率: {portfolio.total_pnl_ratio * 100:.2f}%")

# 资产配置
allocation = PortfolioEngine.allocation_by_type(portfolio)
for item in allocation:
    print(f"{item.asset_type.value}: {item.value} ({item.percentage * 100:.1f}%)")

# 再平衡建议（目标 60% 股票 + 30% 债券 + 10% 现金）
target = {
    AssetType.STOCK: Decimal("0.60"),
    AssetType.BOND: Decimal("0.30"),
    AssetType.CASH: Decimal("0.10"),
}
trades = PortfolioEngine.rebalance_advice(portfolio, target)
for trade in trades:
    print(f"{trade.action} {trade.asset_type.value} {trade.amount}: {trade.reason}")
```

### 2.5 复式记账

```python
from fin001_account import AccountingEngine, AccountType, DebitCredit

engine = AccountingEngine()

# 创建账户
cash = engine.create_account("现金", AccountType.ASSET)
salary = engine.create_account("工资收入", AccountType.INCOME)
food = engine.create_account("餐饮支出", AccountType.EXPENSE)

# 发工资：借 现金 + 贷 工资收入
tx1 = engine.record_transaction(
    debit_account_id=cash.id,
    credit_account_id=salary.id,
    amount=20000,
)

# 吃饭：借 餐饮支出 + 贷 现金
tx2 = engine.record_transaction(
    debit_account_id=food.id,
    credit_account_id=cash.id,
    amount=500,
)

# 试算平衡
print(f"借贷平衡? {engine.is_balanced()}")
balances = engine.trial_balance()
for b in balances:
    print(f"{b.account_name}: 借={b.debit_balance} 贷={b.credit_balance} 净={b.net_balance}")
```

### 2.6 财务健康诊断

```python
from fin006_advisor import AdvisorEngine, RiskLevel, DebtStrategy

financial_data = {
    "monthly_income": 20000,
    "monthly_savings": 5000,
    "monthly_debt_payment": 5000,
    "liquid_assets": 120000,
    "monthly_expenses": 10000,
    "net_worth": 500000,
    "net_worth_last_year": 450000,
    "top_asset_concentration": 0.6,
    "age": 35,
    "risk_tolerance": "moderate",
}

# KPI 诊断
kpis = AdvisorEngine.diagnose_kpis(financial_data)
for kpi in kpis:
    print(f"[{kpi.status.value}] {kpi.display_name}: "
          f"{kpi.value} {kpi.unit} (基准: {kpi.benchmark_good})")
    if kpi.advice:
        print(f"  建议: {kpi.advice}")

# 资产配置建议（基于年龄 + 风险偏好）
risk_level = AdvisorEngine.determine_risk_level(
    age=35, risk_tolerance="moderate"
)
stock_ratio = AdvisorEngine.rule_of_110(age=35)
print(f"\n风险等级: {risk_level.value}")
print(f"Rule of 110 股票建议占比: {stock_ratio}%")
```

---

## 3. 配置指南

### 3.1 利率服务配置

```python
from fin004_rate import RateEngine

# 创建实例（首次自动创建缓存目录）
rate_engine = RateEngine()

# 查询 LPR
lpr_1y = rate_engine.get_lpr("1y")
print(f"LPR 1Y: {lpr_1y.rate_pct}% (来源: {lpr_1y.source})")
print(f"是否缓存: {lpr_1y.is_cached}")

# 利率转换
from fin004_rate import RateEngine
annual = Decimal("0.042")
monthly_compound = RateEngine.annual_to_monthly(annual, compound=True)
monthly_simple = RateEngine.annual_to_monthly(annual, compound=False)
print(f"复利月利率: {monthly_compound}")
print(f"单利月利率: {monthly_simple}")
```

**缓存目录**：`~/.openclaw/cache/fin004_rate/`  
**缓存 TTL**：24 小时

### 3.2 保险产品参数配置

新增险种：
1. 扩展 `InsuranceType` 枚举
2. 在 `InsuranceEngine` 中添加对应测算方法
3. 补充现金价值表或计算公式

### 3.3 KPI 基准调整

修改 `KPI_BENCHMARKS` 字典中的 good/warning 阈值即可，无需改动计算逻辑。

---

## 4. 测试运行

```bash
# 进入组件目录
cd L3-business/components/finance-engine

# 运行全部测试
python -m pytest tests/ -v

# 运行指定模块
python -m pytest tests/test_loan.py -v
python -m pytest tests/test_insurance.py -v

# 运行并生成覆盖率报告
python -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html

# 运行特定测试用例
python -m pytest tests/test_loan.py::test_equal_payment -v
```

---

## 5. 故障排查

### 5.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|---|---|---|
| ImportError: No module named 'fin002_loan' | Python 路径未配置 | 确认 sys.path 包含 finance-engine 目录 |
| 金额精度问题（浮点误差） | 输入用了 float | 一律用 `Decimal("1.23")` 或字符串，不要用 float |
| 贷款计算尾差（最后一期不为 0） | 等额本息舍入累积 | 最后一期已做尾差处理，确认使用最新版本 |
| IRR 不收敛（converged=False） | 现金流复杂，初始猜测不合适 | 尝试传入不同的 guess 参数，或检查现金流 |
| 利率查询返回默认值 | 缓存过期 + API 不可用 | 检查网络连接，或设置更长的缓存 TTL |
| 投资组合收益率为 NaN | 成本为 0（空组合） | 先检查 total_cost > 0 再算 ratio |
| 试算不平衡 | 单边记账 | 每笔交易必须有借有贷，金额相等 |
| Decimal 运算报错 | 混合了 float 和 Decimal | 所有金额用 Decimal，不要用 float |

### 5.2 调试技巧

```python
# 1. 检查输入数据类型
from decimal import Decimal
assert isinstance(amount, Decimal), f"金额应为 Decimal，实际为 {type(amount)}"

# 2. 打印中间结果（贷款摊销）
for entry in schedule.entries:
    if entry.period <= 3 or entry.period > 357:
        print(f"第{entry.period}期: 本金={entry.principal} "
              f"利息={entry.interest} 剩余={entry.remaining_balance}")

# 3. 验证借贷平衡
assert engine.is_balanced(), "借贷不平衡！"

# 4. 查看 IRR 迭代过程
result = InsuranceEngine.calculate_irr(cash_flows)
if not result.converged:
    print(f"IRR 不收敛，迭代 {result.iterations} 次，最终误差 {result.final_error}")
```

### 5.3 性能问题排查

| 现象 | 可能原因 | 排查方法 |
|---|---|---|
| 贷款摊销慢 | 期数极大（>10000） | 正常，期数多时用向量化计算（优化项） |
| IRR 迭代次数多 | 现金流波动大 | 提供更好的初始 guess |
| 组合计算慢 | 持仓数极多（>1万） | 考虑批量计算接口（优化项） |

---

## 6. 升级与迁移

### 6.1 版本升级

本组件遵循语义化版本（SemVer）：
- **PATCH** (x.y.Z)：bug 修复，向后兼容
- **MINOR** (x.Y.z)：新增功能，向后兼容
- **MAJOR** (X.y.z)：不兼容变更

### 6.2 数据迁移

- v1.0 为纯计算引擎，不持久化数据，升级无数据迁移问题
- 若 L4 层存储了引擎输出数据格式，升级时检查字段兼容性

---

## 7. 架构边界

### 7.1 本组件负责

- ✅ 金融计算核心逻辑（借贷、摊销、IRR、收益等）
- ✅ 数据模型定义（Loan, Holding, Account 等）
- ✅ 计算精度控制（Decimal）
- ✅ 利率查询与缓存
- ✅ 财务诊断算法

### 7.2 本组件不负责

- ❌ Web UI（仅演示用，不作为生产能力）
- ❌ 用户认证与权限控制
- ❌ 数据持久化（由 L4 层实现）
- ❌ 风控审批流程
- ❌ 实际交易执行（仅计算模拟）
- ❌ 接入真实证券/银行账户

---

## 8. FAQ

**Q: 为什么用 dataclass 而不是 Pydantic？**  
A: 纯计算场景下 dataclass 更轻量、更快。本组件不做输入验证（由 L4 层负责），用 Pydantic 是过度设计。

**Q: 为什么全部用 Decimal？用 float 不行吗？**  
A: 金融计算对精度要求高。float 二进制浮点有精度误差（如 0.1 + 0.2 ≠ 0.3），金额计算必须用 Decimal。

**Q: fin004_rate 是唯一有副作用的模块，安全吗？**  
A: 它只做只读操作（查利率、写本地缓存文件），不修改用户数据。缓存文件权限 600，不涉及敏感信息。

**Q: 能接入真实券商/银行数据吗？**  
A: L3 层不做。可以在 L4 层接入真实 API，然后把数据传给本引擎计算。

**Q: 新增一个金融产品类型需要改多少？**  
A: 取决于复杂度。新增一种还款方式：加枚举 + 加函数，约 20 行。新增一个险种：加枚举 + 加测算方法 + 现价表，约 100-200 行。

**Q: 支持多币种吗？**  
A: 模型设计预留了 currency 字段，但汇率换算和多币种合并报表由 L4 层或专门模块实现。
