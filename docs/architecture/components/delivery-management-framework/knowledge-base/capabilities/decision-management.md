---
title: "决策管理知识"
description: "项目决策的记录、审批、替代和审计追踪的完整生命周期方法论"
source: "PMBOK Guide 7th Edition; TOGAF Decision Management; RFC Process (Rust/Python)"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["decision_management", "approval", "supersede", "audit_trail", "adr"]
capability: "decision_management"
xref:
  - path: "roles/delivery-director/capability-map.md"
    relation: "referenced_by"
  - path: "roles/product-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/risk-management.md"
    relation: "related_to"
last_reviewed: "2026-09-04"
---

# 决策管理知识 Decision Management

## 概述 Overview

决策管理是交付管理框架中对项目关键决策进行结构化记录、审批和追踪的能力。项目中的决策（Decision）是影响项目方向的技术或管理选择，如架构选型、工具链确定、优先级排序等。

在 DMS 框架中，决策管理确保每个关键决策都有**提案→审批→执行→审计**的完整闭环，避免"拍脑袋"和"决策黑箱"。决策管理与 ADR（Architecture Decision Record）互补：ADR 是决策的文档形式，决策管理是决策的流程引擎。

## 核心概念 Key Concepts

### 1. 决策类型 Decision Types
- **技术决策 Technical**：架构选型、技术栈确定、接口设计
- **管理决策 Management**：资源分配、优先级调整、范围变更
- **战略决策 Strategic**：项目方向、目标调整、终止决策

### 2. 决策状态 Decision States
- **proposed**：已提议，等待审批
- **approved**：已通过（终态），可执行
- **rejected**：已否决（终态），不再执行
- **superseded**：已被替代（终态），被新决策取代

### 3. 决策日志 Decision Log
按时间倒序排列的完整决策历史，提供审计追踪能力。每个决策记录包含：标题、描述、优先级、决策结果、时间戳。

### 4. 决策替代 Supersede
当新决策取代旧决策时，旧决策状态变为 superseded（而非删除），保留完整历史。替代只能从 approved 状态发起。

### 5. 决策审计 Audit Trail
通过决策日志可追溯：谁在什么时候做了什么决策、为什么被否决、哪些决策被替代。是项目复盘和合规审查的基础。

## 方法/流程 Methodology

DMS 框架下决策管理采用 **三态分支模型**：

### 1. 提议 Propose
- 创建决策记录，描述决策背景、选项、建议方案
- 初始状态：`proposed`
- 可设置优先级（priority）和审批人（assignee）

### 2. 审批 Decide
- **批准 Approve**：`proposed → approved`（终态）
- **否决 Reject**：`proposed → rejected`（终态）
- 审批人基于决策描述和上下文做出判断

### 3. 替代 Supersede
- `approved → superseded`（终态）
- 新决策取代旧决策时，旧决策标记为 superseded
- superseded 的决策仍保留在日志中，供审计参考

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 决策周期 Time to Decide | 从 proposed 到 approved/rejected 的平均天数 | ≤ 3 天 |
| 决策通过率 Approval Rate | approved / (approved + rejected) | 60-80% |
| 替代率 Supersede Rate | superseded / approved | ≤ 20% |
| 待决策积压 Pending Decisions | 处于 proposed 状态的决策数量 | ≤ 5 |
| 决策覆盖率 Decision Coverage | 有决策记录的关键决策 / 总关键决策 | ≥ 80% |

## 常见陷阱 Common Pitfalls

1. **决策黑箱**：决策做了但没有记录，事后无法追溯"为什么这么做"。所有关键决策必须有书面记录。
2. **不定义决策权限**：谁可以批准什么级别的决策不清晰，导致审批瓶颈或越权审批。应建立决策权限矩阵。
3. **否决不记录原因**：rejected 的决策没有记录否决原因，同样的问题反复被提议。否决必须附带原因。
4. **替代不保留历史**：直接删除旧决策而非标记 superseded，丢失审计线索。superseded 是终态但不可删除。
5. **所有决策走正式流程**：芝麻小事也走完整决策流程，消耗团队精力。按影响范围分级管理。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `decision` 模块 | 决策生命周期状态机 + 决策日志 + 事件联动 |
| `decision.log()` | 按时间倒序的决策日志，支持审计追踪 |
| `decision.transition_decision()` | 状态迁移：approve/reject/supersede |
| `project.cancelled` | 项目取消时，proposed 决策自动 reject |
| ADR 文档 | 决策的详细文档化形式，与 decision 模块互补 |
| `quality` 模块 | 质量评审触发的技术决策记录 |

## 参考 References

- PMI, *PMBOK® Guide*, 7th Edition, 2021
- The Open Group, *TOGAF® Standard, 10th Edition*, 2022
- Rust RFC Process, *rfcs.repository*, 2023
- Nygard, M., *Documenting Architecture Decisions*, 2011
