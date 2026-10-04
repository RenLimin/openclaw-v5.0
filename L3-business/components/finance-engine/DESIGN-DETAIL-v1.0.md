# 家庭理财引擎 — 详细设计

> 组件：finance-engine (L3)
> 版本：v1.0
> 日期：2026-09-03

## 1. 概述

家庭理财引擎的详细设计，包含账户、贷款、保险、投资、利率和建议 6 大核心引擎。

## 2. 接口契约

### 2.1 账户引擎

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| create_account | POST | account_data | account_id |
| get_balance | GET | account_id | balance |
| transfer | POST | from, to, amount | result |

### 2.2 投资引擎

| 接口 | 方法 | 输入 | 输出 |
|---|---|---|---|
| analyze_portfolio | GET | user_id | analysis |
| calculate_return | POST | investment_data | return_rate |
| rebalance | POST | portfolio, target | trades |

## 3. 数据模型

### 3.1 账户模型

```python
@dataclass
class Account:
    id: str
    user_id: str
    type: AccountType
    balance: float
    currency: str
    created_at: datetime
```

### 3.2 投资组合模型

```python
@dataclass
class Portfolio:
    id: str
    user_id: str
    holdings: List[Holding]
    risk_profile: RiskProfile
    target_allocation: Dict[str, float]
```

## 4. 技术方案

### 4.1 6 大引擎

1. **账户引擎**：账户管理、余额查询、转账
2. **贷款引擎**：贷款计算、还款计划、利率比较
3. **保险引擎**：保险需求分析、产品比较
4. **投资引擎**：投资组合分析、风险评估、再平衡
5. **利率引擎**：利率计算、趋势分析
6. **建议引擎**：个性化理财建议生成

### 4.2 Web UI

基于模板的 Web 界面，支持：
- 仪表盘视图
- 账户管理
- 投资分析
- 报表生成

## 5. 依赖关系

- L2 持久化适配 (SQLite)
- L2 知识库 (理财知识)
- L2 Web 通用组件

## 6. 测试方案

- 单元测试：各引擎核心逻辑
- 集成测试：跨引擎协作
- E2E 测试：完整用户流程
