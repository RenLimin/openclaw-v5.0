---
title: "预算管理知识"
description: "项目成本预算编制、执行监控、偏差分析与决算的完整方法论"
source: "PMBOK Guide 7th Edition; Earned Value Management; CIMA Cost Management"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["budget_management", "cost_control", "earned_value", "forecasting", "cost_baseline"]
capability: "budget_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/resource-management.md"
    relation: "depends_on"
last_reviewed: "2026-09-03"
---

# 预算管理知识 Budget Management

## 概述 Overview

预算管理是交付管理框架中对项目成本进行估算、预算编制、执行监控、偏差分析和预测调整的能力。项目预算是交付铁三角（范围、进度、成本）的核心维度之一，超支是交付失败最直观的表现形式。

在 DMS 框架中，预算管理与合同管理、资源管理、采购管理紧密联动，形成 **预算编制→执行监控→偏差预警→调整决策** 的闭环控制。

## 核心概念 Key Concepts

### 1. 成本类型 Cost Types
- **直接成本 Direct Cost**：可直接归因于项目的成本，如项目人员工资、专用设备、差旅
- **间接成本 Indirect Cost**：组织运营分摊到项目的成本，如管理层工资、办公场地、水电
- **固定成本 Fixed Cost**：不随工作量变化的成本，如设备采购
- **可变成本 Variable Cost**：随工作量变化的成本，如人工费、材料费

### 2. 成本基线 Cost Baseline
经批准的按时间段分配的项目预算，用于度量和监控项目成本绩效。成本基线 = 各工作包成本估算 + 应急储备。管理储备不包含在成本基线中。

### 3. 挣值管理三要素 EVM Core Values
- **PV 计划值 Planned Value**：在某时点计划完成工作的预算价值
- **EV 挣值 Earned Value**：在某时点实际已完成工作的预算价值
- **AC 实际成本 Actual Cost**：在某时点实际花费的成本

### 4. 成本绩效指标 EVM Derived Metrics
- **CV 成本偏差 Cost Variance** = EV - AC（正=省钱，负=超支）
- **CPI 成本绩效指数 Cost Performance Index** = EV / AC（>1=好，<1=差）
- **EAC 完工估算 Estimate at Completion** = BAC / CPI（典型偏差）
- **ETC 完工尚需估算 Estimate to Complete** = EAC - AC

### 5. 应急储备 vs 管理储备 Contingency vs Management Reserve
- **应急储备 Contingency Reserve**：应对已知风险（known-unknowns），项目经理可动用，纳入成本基线
- **管理储备 Management Reserve**：应对未知风险（unknown-unknowns），需高层审批，不纳入成本基线
- 项目总预算 = 成本基线 + 管理储备

## 方法/流程 Methodology

DMS 框架下预算管理采用 **四阶段闭环**：

### 1. 规划成本管理 Plan Cost Management
- 确定成本估算精度（粗略量级估算 ROM ±50% → 预算级估算 ±10% → 确定性估算 ±5%）
- 制定成本管理计划：计量单位、准确度、精确度、控制阈值、报告格式
- 输出：成本管理计划

### 2. 估算成本 Estimate Costs
- 基于 WBS 自下而上估算各工作包成本
- 方法：类比估算、参数估算、三点估算（PERT）、自下而上估算、储备分析
- 考虑资源费率、通货膨胀、汇率波动等因素
- 输出：活动成本估算、估算依据、更新的项目文件

### 3. 制定预算 Determine Budget
- 汇总各活动和工作包的成本估算
- 进行成本汇总，建立成本基线（S 曲线）
- 确定应急储备和管理储备
- 输出：成本基线、项目资金需求、更新的项目文件

### 4. 控制成本 Control Costs
- 监控成本绩效，计算 CV、CPI、SV、SPI
- 分析偏差原因，预测 EAC、ETC、TCPI
- 超阈值时启动纠偏措施或变更请求
- 输出：工作绩效信息、成本预测、变更请求

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 成本绩效指数 CPI | EV / AC | ≥ 0.95 |
| 成本偏差率 CV% | (EV - AC) / PV × 100% | ≥ -5% |
| 预算执行率 Budget Execution Rate | AC / BAC × 100% | 与进度匹配 |
| 预测完工偏差 VAC | BAC - EAC | ≥ 0 |
| 变更成本占比 Change Cost Ratio | 变更导致的成本增加 / 原始预算 | ≤ 10% |

## 常见陷阱 Common Pitfalls

1. **预算拍脑袋**：没有详细 WBS 和资源估算，仅凭经验拍数字，偏差可达 50% 以上。必须基于分解和估算做预算。
2. **只看花钱不看价值**：误以为"钱花得慢就是好"，可能是进度严重滞后。必须结合挣值（EV）一起看，CPI 才是真实绩效。
3. **预算不分层**：只给一个总账，没有工作包级预算，发现超支时找不到具体哪里超了。预算必须分解到可控粒度。
4. **变更不走预算流程**：范围变更了但预算不调整，项目经理"自己扛"，最后酿成大超支。所有变更必须同步评估成本影响。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `cost-baseline` 模块 | 成本基线数据模型，含 baseline_id, time_phased_budget, contingency_reserve 字段 |
| `earned-value` 引擎 | EVM 指标自动计算，PV/EV/AC 聚合与 CPI/SPI 衍生指标 |
| `procurement-management` 模块 | 采购合同金额纳入项目成本跟踪 |
| `timesheet` 模块 | 人工成本实际值采集基础（工时 × 费率） |
| `change-request` 模块 | CR 批准后自动更新成本基线（cost_baseline_version 递增） |

## 参考 References

- PMI, *PMBOK® Guide*, 7th Edition, 2021
- PMI, *Practice Standard for Earned Value Management*, 3rd Edition, 2019
- CIMA, *Official Terminology*, 2020 Edition
