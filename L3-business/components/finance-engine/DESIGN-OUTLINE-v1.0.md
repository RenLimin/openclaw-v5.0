# finance-engine — 设计大纲 (DESIGN-OUTLINE)

> 版本: v1.0 · 日期: 2026-09-28

## 1. 整体架构

```
fin001_account/  → 复式记账引擎
fin002_loan/     → 贷款/借款核算引擎
fin003_insurance/ → 保险产品核算引擎
fin004_rate/     → 利率服务引擎
fin005_portfolio/ → 投资持仓核算引擎
fin006_advisor/  → 理财建议引擎
```

## 2. 模块划分

| 模块 | 职责 | 输入 | 输出 |
|---|---|---|---|
| fin001_account | 复式记账 | 借贷记录 | 余额/试算平衡 |
| fin002_loan | 贷款计算 | 本金/利率/期限 | 还款计划 |
| fin003_insurance | 保险测算 | 保单信息 | 现金价值/IRR |
| fin004_rate | 利率服务 | 利率类型 | 利率数据 |
| fin005_portfolio | 投资核算 | 持仓数据 | 收益/配置建议 |
| fin006_advisor | 理财建议 | KPI 数据 | 诊断报告 |

## 3. 接口契约

- `AccountingEngine.record_entry(debit, credit, amount)`
- `AccountingEngine.trial_balance() → balance`
- `LoanEngine.calculate_schedule(principal, rate, term, method)`
- `LoanEngine.prepay(amount) → new_schedule`
- `InsuranceEngine.cash_value(policy, year) → value`
- `RateEngine.get_rate(type) → rate`
- `PortfolioEngine.calculate_return(holdings) → return_rate`
- `AdvisorEngine.diagnose(kpi) → suggestions`

## 4. 技术选型

- 纯函数式设计（零副作用）
- 无状态计算，数据由 L4 注入
- 利率服务允许本地文件缓存（TTL 24h）

## 5. 分层约束

- L3 纯逻辑层：不直接访问 DB
- 被 L4 fin-l4 继承
