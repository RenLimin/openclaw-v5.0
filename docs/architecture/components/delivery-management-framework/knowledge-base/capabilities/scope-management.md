---
title: "范围管理知识"
description: "项目交付范围的定义、确认、控制与变更管理方法体系"
source: "PMBOK Guide 6th/7th Edition; ISO 21500:2021"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["scope_management", "WBS", "change_control", "requirements", "delivery_scope"]
capability: "scope_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/change-management.md"
    relation: "related_to"
last_reviewed: "2026-09-03"
---

# 范围管理知识 Scope Management

## 概述 Overview

范围管理是交付管理框架中定义、确认和控制项目交付边界的核心能力。它确保交付团队只做被授权的工作（do the right things），防止范围蔓延（scope creep）导致进度超期、预算超支和质量下降。

在 DMS 框架中，范围管理贯穿 **需求接收 → 交付计划 → 执行控制 → 验收关闭** 全生命周期，是所有交付决策的基线锚点。

## 核心概念 Key Concepts

### 1. 项目范围 vs 产品范围 Project Scope vs Product Scope
- **产品范围 Product Scope**：交付物本身具备的功能、特性和性能指标
- **项目范围 Project Scope**：为交付产品所执行的全部工作范围，含管理活动
- 两者必须对齐；项目范围过大或产品范围缺失均为风险信号

### 2. 工作分解结构 Work Breakdown Structure (WBS)
将交付范围逐层分解为可管理、可分配、可追踪的工作包（work package），最底层为活动级（activity）。WBS 是进度、成本、资源估算的共同基线。

### 3. 范围基线 Scope Baseline
经批准的范围说明书 + WBS + WBS 词典，构成范围基线。任何变更必须通过正式变更控制流程后方可更新基线。

### 4. 范围蔓延 Scope Creep
未经过变更控制流程的隐性范围扩大，常以"小需求""帮忙改一下"形式出现，是交付失败的 Top 3 原因之一。

### 5. 需求可追溯矩阵 Requirements Traceability Matrix (RTM)
将每条需求关联到来源、设计、实现、测试用例和验收结果，确保需求全链路可追踪。

## 方法/流程 Methodology

DMS 框架下范围管理采用 **五步法**：

1. **范围规划 Plan Scope**：在 `delivery-initiation` 阶段输出范围管理计划，明确 WBS 分解规则、变更审批层级、验收标准
2. **需求收集 Collect Requirements**：通过访谈、研讨会、原型法等获取干系人需求，形成需求规格说明书（SRS）
3. **范围定义 Define Scope**：编写详细范围说明书，明确包含项（in-scope）、排除项（out-of-scope）、假设条件和约束
4. **创建 WBS Create WBS**：自上而下分解至工作包层级，每个工作包定义唯一 ID、负责人、交付物、估算工时
5. **范围控制 Control Scope**：在执行阶段通过偏差分析（variance analysis）监控范围偏差，触发变更请求（CR）并更新基线

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 目标值参考 |
|---------|-------------|-----------|
| 范围偏差率 Scope Variance % | (实际范围点数 - 基线范围点数) / 基线范围点数 × 100% | ≤ 5% |
| 变更请求通过率 CR Approval Rate | 批准的 CR 数 / 总 CR 数 | 视项目而定，健康值 30%-60% |
| 需求覆盖率 Requirements Coverage | 已实现需求数 / 总需求数 × 100% | 100%（验收时） |
| 范围蔓延指数 Scope Creep Index | 非正式变更导致的工作量 / 总工作量 | ≤ 3% |
| WBS 分解完整度 WBS Completeness | 已分解工作包 / 预计工作包总数 | 规划阶段 ≥ 95% |

## 常见陷阱 Common Pitfalls

1. **范围说明书模糊**：使用"大致""大概""等"等模糊表述，导致后期理解偏差。必须用可测试、可验证的语言描述验收标准。
2. **跳过 WBS 直接排期**：没有分解到工作包就做进度计划，估算偏差通常 >40%。WBS 是估算的前提。
3. **变更"先做后批"**：客户或销售口头答应新需求，团队先做再走流程。一旦形成惯例，范围基线形同虚设。
4. **Out-of-scope 不签字确认**：范围排除项未获干系人书面确认，后期容易出现"这不是应该包含的吗"的争议。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `delivery-initiation` 状态机 | `scope_defined` 状态标记范围基线冻结 |
| `change-request` 模块 | 范围变更通过 CR 流程流转，关联 `impact_scope` 字段 |
| `deliverable-baseline` 表 | 存储范围基线版本（scope_baseline_version） |
| `requirements` 子模块 | RTM 数据来源，关联 `requirement_id` 外键 |
| `milestone-tracking` 能力 | 关键范围节点对应里程碑验收 |

## 参考 References

- PMI, *A Guide to the Project Management Body of Knowledge (PMBOK® Guide)*, 7th Edition, 2021
- ISO 21500:2021, *Guidance on project management*
- IEEE 830-1998, *Recommended Practice for Software Requirements Specifications*
