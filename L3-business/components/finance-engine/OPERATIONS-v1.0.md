# finance-engine — 操作手册 (OPERATIONS)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 安装与启动

### 1.1 环境依赖

- Python 3.12+

### 1.2 安装步骤

```bash
cd L3-business/components/finance-engine
# 纯逻辑层，无需额外依赖
```

### 1.3 启动命令

本组件为库模式，由 L4 层调用，无独立启动命令。

### 1.4 健康检查

```bash
python3 -c "from finance_engine import *; print('OK')"
```

## 2. 操作指南

### 2.1 场景一：复式记账

```python
from finance_engine.fin001_account import AccountingEngine
engine = AccountingEngine()
engine.record_entry("现金", "收入", 1000)
balance = engine.trial_balance()
```

### 2.2 场景二：贷款计算

```python
from finance_engine.fin002_loan import LoanEngine
engine = LoanEngine()
schedule = engine.calculate_schedule(1000000, 0.049, 30, "等额本息")
```

### 2.3 场景三：保险测算

```python
from finance_engine.fin003_insurance import InsuranceEngine
engine = InsuranceEngine()
cash_value = engine.cash_value(policy, year=5)
```

## 3. 配置说明

无外部配置，纯计算引擎。

## 4. 故障排查

### 4.1 计算结果异常

- **症状**: 结果与预期不符
- **原因**: 输入数据格式错误
- **解决**: 检查输入数据类型和范围

## 5. FAQ

**Q1: 如何扩展新引擎？**
A: 在 `finance-engine/` 下创建新目录 fin00x_xxx，定义 Engine 类

**Q2: 支持实时数据吗？**
A: 当前为纯计算，数据由 L4 注入

## 6. 附录

### 6.1 接口清单

- `AccountingEngine`: record_entry / trial_balance
- `LoanEngine`: calculate_schedule / prepay
- `InsuranceEngine`: cash_value / irr / dividend
- `RateEngine`: get_rate / convert
- `PortfolioEngine`: calculate_return / rebalance
- `AdvisorEngine`: diagnose / asset_allocation / debt_optimize
