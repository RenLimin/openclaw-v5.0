---
id: FIN-000
title: "家庭理财维度索引"
description: "L3 家庭理财维度总索引：账户/预算/贷款/利率/债务/健康 + 投资/税务/保险/遗产知识，三角色与七类交付物模板"
source: "CFP Board / 中国人民银行 / 标准普尔家庭资产象限 / 中国银保监会"
version: "1.0"
category: "business"
dimension: "finance"
stage: "manage"
sub_area: "index"
type: "index"
tags: ["family-finance", "index", "accounting", "budget", "loan", "insurance", "investment", "tax"]
last_reviewed: "2026-09-06"
---

# 家庭理财维度索引

> L3 家庭理财维度（P0）—— 覆盖账户、预算、贷款、利率、债务、健康六大基础领域 + 投资、税务、保险、遗产四大规划领域。
> 建设遵循 [L3 建设方法论](../methodology/README.md)（维度设计 → 角色定义 → 知识文档）。

## 维度定位

家庭理财维度为个人/家庭财务场景提供知识支撑：从账户体系与记账基础，到贷款核算、预算管理、财务健康诊断，再到资产配置、税务筹划、保险规划与遗产传承。

## 知识结构

### 账户与预算

| 文档 | 说明 |
|------|------|
| [家庭账户体系与记账方法](knowledge/accounting/account-system.md) | 账户分类、复式记账、工具选型 |
| [家庭预算管理](knowledge/budgeting/budget-management.md) | 50/30/20 法则、预算编制、偏差控制 |

### 贷款与利率

| 文档 | 说明 |
|------|------|
| [贷款核算与还款方式](knowledge/loan/loan-accounting.md) | 等额本息/等额本金、PMT、提前还款 |
| [利率服务与实时利率获取](knowledge/interest-rate/interest-rate-service.md) | LPR、数据源、利率敏感性 |

### 债务与健康

| 文档 | 说明 |
|------|------|
| [家庭债务优化策略](knowledge/debt-optimization/debt-optimization.md) | 雪崩/雪球/混合法、DTI |
| [家庭财务健康诊断](knowledge/financial-health/family-financial-health.md) | 六大健康指标、红黄绿分级 |

### 投资规划

| 文档 | 说明 |
|------|------|
| [资产配置策略](knowledge/investment/portfolio-allocation.md) | MPT、SAA/TAA、再平衡 |
| [投资风险管理](knowledge/investment/risk-management.md) | 风险识别、评估、应对 |
| [退休规划](knowledge/investment/retirement-planning.md) | 养老金测算、提取策略 |

### 税务筹划

| 文档 | 说明 |
|------|------|
| [个人所得税筹划](knowledge/tax-planning/individual-income-tax.md) | 专项附加扣除、年终奖优化 |
| [企业税务筹划](knowledge/tax-planning/enterprise-tax.md) | 经营所得、企业税务基础 |

### 保险配置

| 文档 | 说明 |
|------|------|
| [人寿保险配置](knowledge/insurance/life-insurance.md) | 寿险类型、保额测算 |
| [健康保险配置](knowledge/insurance/health-insurance.md) | 医疗/重疾/长护险、配置策略 |

### 遗产规划

| 文档 | 说明 |
|------|------|
| [遗嘱与信托](knowledge/estate-planning/will-trust.md) | 遗嘱、信托、传承架构 |

## 角色

| 角色 | 定位 | 文件 |
|------|------|------|
| [理财顾问](roles/financial-advisor/IDENTITY.md) | 综合理财规划与建议 | SOUL / AGENTS / IDENTITY / references |
| [财务规划师](roles/financial-planner/IDENTITY.md) | 财务体检、目标测算、资产配置 | SOUL / AGENTS / IDENTITY / references |
| [保险顾问](roles/insurance-advisor/IDENTITY.md) | 保障缺口分析、方案设计 | SOUL / AGENTS / IDENTITY / references |

## 模板

| 模板 | 说明 |
|------|------|
| [家庭资产负债表](templates/balance-sheet.md) | 资产/负债/净资产盘点 |
| [月度收支表](templates/monthly-cashflow.md) | 收入/支出/结余统计 |
| [家庭预算表](templates/budget-template.md) | 预算编制与偏差跟踪 |
| [家庭保险清单](templates/insurance-checklist.md) | 保单总览与缺口核对 |
| [理财规划报告](templates/financial-plan-report.md) | 体检→目标→方案→行动 |
| [财务体检表](templates/financial-checkup.md) | 健康指标检查 |
| [投资政策声明（IPS）](templates/investment-policy.md) | 投资目标与约束 |

## 适用场景

- 家庭财务体检与健康诊断
- 预算编制与储蓄目标达成
- 贷款方案对比与债务优化
- 保险需求分析与产品选型
- 资产配置与退休规划
- 税务优化与遗产传承

## 交叉引用

- **方法论**：建设遵循 [L3 建设方法论](../methodology/README.md)
- **项目经验**：设计决策见 [ADR-026](../../project-experience/adr/ADR-202609-026-personal-finance-framework-L3.md)
- **行业知识**：复式记账/贷款/保险/配置等可交叉引用 [行业个人理财](../../industry/personal-finance/README.md)

## 变更历史

- 2026-09-06: 家庭理财维度 P0 建设完成 — 14 知识 + 3 角色（4 文件标准）+ 7 模板
- 2026-08-26: 初始骨架（8 知识 + 1 角色 + 2 模板）
