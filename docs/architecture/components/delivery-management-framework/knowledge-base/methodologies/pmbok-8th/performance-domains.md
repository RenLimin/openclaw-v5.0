---
title: "PMBOK 8th 8 大绩效域"
description: "PMBOK 第 8 版的 8 个绩效域及其在交付管理中的映射"
source: "PMI PMBOK Guide 8th Edition"
version: "8th"
category: "business"
dimension: "delivery-management"
sub_area: "methodologies"
type: "industry"
tags: ["pmbok", "performance-domains", "项目管理"]
last_reviewed: "2026-09-03"
---

# PMBOK 8th — 8 大绩效域

## 概述
绩效域（Performance Domain）是一组对实现项目目标有重大影响的相关活动。8 个绩效域相互作用，共同决定项目成果。

**与过程组的区别**：
- 过程组：按时间顺序划分（启动/规划/执行/监控/收尾）
- 绩效域：按活动领域划分，贯穿项目始终，持续交互

## 8 大绩效域

### 1. 干系人绩效域 (Stakeholder)
**目标**：有效识别干系人，促进参与，管理期望。
- 关键活动：识别、分析、优先级排序、参与计划、持续评估
- 输出：干系人登记册、参与度评估矩阵
- **DMS 映射**：stakeholder_management 能力域

### 2. 团队绩效域 (Team)
**目标**：打造高绩效团队，实现项目目标。
- 关键活动：组建、发展、赋能、领导、团队健康度
- 输出：团队章程、技能矩阵、团队健康度指标
- **DMS 映射**：resource_management 能力域 + 角色模板

### 3. 开发方法和生命周期绩效域 (Development Approach & Life Cycle)
**目标**：选择合适的开发方法和生命周期模型。
- 关键活动：方法选择、阶段定义、交付节奏、裁剪
- 输出：项目生命周期定义、阶段关口标准
- **DMS 映射**：workflow_scheme 引擎 + project 状态机

### 4. 规划绩效域 (Planning)
**目标**：为项目制定清晰的路线图。
- 关键活动：范围定义、进度编制、预算估算、资源规划、风险规划
- 输出：项目管理计划、范围基准、进度基准、成本基准
- **DMS 映射**：scope_management / schedule_management / budget_management

### 5. 项目工作绩效域 (Project Work)
**目标**：高效执行项目工作，满足需求。
- 关键活动：任务分配、进度跟踪、问题管理、变更控制、知识管理
- 输出：工作绩效数据、变更请求、经验教训
- **DMS 映射**：milestone_tracking + deliverable_management

### 6. 交付绩效域 (Delivery)
**目标**：按计划交付预期范围和质量的成果。
- 关键活动：需求管理、范围控制、质量保证、验收管理
- 输出：可交付成果、验收文件、交付报告
- **DMS 映射**：deliverable 模块 + quality_management

### 7. 测量绩效域 (Measurement)
**目标**：跟踪绩效，识别偏差，采取纠正措施。
- 关键活动：基线建立、指标定义、数据收集、偏差分析、预测
- 输出：绩效报告、EVM 指标、预测、纠正措施
- **DMS 映射**：milestone 状态跟踪 + 度量指标体系

### 8. 不确定性绩效域 (Uncertainty)
**目标**：识别并应对项目不确定性。
- 关键活动：风险识别、定性/定量分析、应对规划、风险监控
- 输出：风险登记册、风险应对计划、风险报告
- **DMS 映射**：risk 模块 + risk_management 能力域

## 绩效域之间的交互

```
干系人 ──→ 团队 ──→ 开发方法
   ↑          ↑          ↑
   └── 规划 ──┴── 项目工作 ──┤
          ↑          ↑        │
          └── 测量 ──┴── 交付 ┘
               ↑
            不确定性
```

## 与 12 原则的对应
| 绩效域 | 核心原则 |
|--------|---------|
| 干系人 | 原则 3（干系人有效参与） |
| 团队 | 原则 2（协作团队）+ 原则 6（领导力） |
| 开发方法 | 原则 7（裁剪）+ 原则 11（适应性） |
| 规划 | 原则 4（价值聚焦）+ 原则 9（复杂性） |
| 项目工作 | 原则 1（管家）+ 原则 8（质量） |
| 交付 | 原则 4（价值）+ 原则 8（质量）+ 原则 12（未来状态） |
| 测量 | 原则 5（系统思维）+ 原则 10（风险） |
| 不确定性 | 原则 5（系统）+ 原则 10（风险）+ 原则 11（适应） |

## 在交付管理中的应用
1. **用绩效域评估项目健康度**：8 个维度打分，识别短板
2. **用绩效域对齐团队分工**：每个绩效域对应 RACI 中的 R
3. **用绩效域设计仪表盘**：每个绩效域 2-3 个核心指标

## 与 DMS 框架的映射
DMS 的 12 个能力原子分布在 8 个绩效域中：
| 绩效域 | DMS 能力原子 |
|--------|-------------|
| 干系人 | stakeholder_management, communication_management |
| 团队 | resource_management |
| 开发方法 | (框架内置：状态机可配置) |
| 规划 | scope_management, schedule_management, budget_management |
| 项目工作 | milestone_tracking |
| 交付 | deliverable_management, quality_management, contract_interface, sla_tracking |
| 测量 | (通过各模块状态自动计算) |
| 不确定性 | risk_management |

## 参考
- PMI, *PMBOK® Guide*, 8th ed., Ch. 3-10
