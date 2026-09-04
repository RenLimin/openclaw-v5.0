---
title: "Scrum 框架指南"
description: "Scrum 框架的 3 角色、5 事件、3 工件，及在交付管理中的应用"
source: "Scrum Guide 2020"
version: "2020"
category: "business"
dimension: "delivery-management"
sub_area: "methodologies"
type: "industry"
tags: ["scrum", "agile", "敏捷", "sprint"]
last_reviewed: "2026-09-03"
---

# Scrum 框架

## 概述
Scrum 是一个轻量级框架，用于在复杂问题中高效交付产品。它不是一个方法论或技术，而是一个可以在其上应用各种流程和技术的框架。

**核心价值观**（Scrum 的 5 个价值观）：
- **承诺（Commitment）**：对目标的承诺
- **专注（Focus）**：专注于 Sprint 的工作
- **开放（Openness）**：对工作和挑战保持开放
- **尊重（Respect）**：团队成员互相尊重
- **勇气（Courage）**：有勇气做正确的事

## 3 个角色

### 1. 产品负责人 (Product Owner, PO)
- **职责**：最大化产品价值、管理产品待办列表（Product Backlog）
- **核心权力**：决定做什么、不做什么、优先级排序
- **关键技能**：业务理解、需求表达、优先级判断、利益相关者管理
- **DMS 映射**：product-manager 角色模板

### 2. Scrum Master (SM)
- **职责**：促进 Scrum 流程、移除障碍、服务团队
- **核心权力**：没有权力，只有影响力；通过服务领导
- **关键技能**：教练技术、冲突解决、引导技术、敏捷知识
- **DMS 映射**：scrum-master 角色模板

### 3. 开发团队 (Developers)
- **职责**：在每个 Sprint 交付"完成"的增量
- **特征**：自组织、跨职能、5-9 人
- **关键能力**：技术专业、协作、质量内建
- **DMS 映射**：项目成员（RACI 中的 R）

## 5 个事件

### 1. Sprint（冲刺）
- **时长**：1-4 周，固定长度
- **目标**：Sprint Goal（冲刺目标）
- **关键约束**：Sprint 期间不改变 Sprint Goal
- **DMS 映射**：milestone 中的迭代里程碑

### 2. Sprint Planning（冲刺规划）
- **时长**：1 个月 Sprint = 最多 8 小时；2 周 = 最多 4 小时
- **议题**：为什么（价值）、做什么（范围）、怎么做（计划）
- **输出**：Sprint Goal + Sprint Backlog

### 3. Daily Scrum（每日站会）
- **时长**：≤ 15 分钟，每天同一时间同一地点
- **目的**：同步进展、调整计划、识别障碍
- **形式**：自由形式，不只是三个问题
- **DMS 映射**：communication_management 中的定期沟通

### 4. Sprint Review（冲刺评审）
- **时长**：1 个月 Sprint = 最多 4 小时
- **目的**：展示产品增量、收集反馈、调整 Backlog
- **参与者**：Scrum 团队 + 利益相关者
- **DMS 映射**：deliverable 评审流程

### 5. Sprint Retrospective（冲刺回顾）
- **时长**：1 个月 Sprint = 最多 3 小时
- **目的**：检视团队流程、识别改进点、制定改进计划
- **焦点**：人、关系、过程、工具
- **DMS 映射**：经验教训模板

## 3 个工件

### 1. Product Backlog（产品待办列表）
- 所有需要做的事情的有序列表
- PO 负责，任何人都可以添加
- 持续细化（Refinement），不是一次性完成
- **DMS 映射**：deliverable 列表 + 优先级

### 2. Sprint Backlog（冲刺待办列表）
- 开发团队承诺在本 Sprint 完成的 Product Backlog 条目
- 团队拥有，团队调整
- 包含实现计划（不只是列表）
- **DMS 映射**：milestone 下的 deliverable 集合

### 3. Increment（增量）
- Sprint 中完成的所有 Product Backlog 条目的总和
- 必须是"完成"的（Definition of Done）
- 必须可用，即使不发布
- **DMS 映射**：accepted 状态的 deliverable

## Definition of Done (DoD)
**完成的定义**：团队对"完成"的共识标准。

常见 DoD 条目：
- 代码通过 Code Review
- 单元测试覆盖率 ≥ 80%
- 通过集成测试
- 文档更新
- 通过 QA 验收

**DMS 映射**：deliverable.accepted 状态的前置条件

## 承诺 (Commitments)
- Product Backlog 的承诺：**Product Goal**
- Sprint Backlog 的承诺：**Sprint Goal**
- Increment 的承诺：**Definition of Done**

## 常见误区
1. **把 Scrum 当瀑布用**：Sprint 规划不是需求冻结
2. **SM 当项目经理用**：SM 是服务式领导，不是任务分配者
3. **每日站会当汇报用**：是团队内部同步，不是向领导汇报
4. **只做仪式不理解本质**：Scrum 是框架，不是 checklist
5. **忽略工程实践**：没有 TDD/CI/重构等实践，Scrum 只会更快产生垃圾

## 与 DMS 框架的映射
| Scrum 概念 | DMS 框架 |
|-----------|---------|
| Product Owner | product-manager 角色 |
| Scrum Master | scrum-master 角色 |
| Sprint | milestone (type=sprint) |
| Sprint Goal | milestone 目标 |
| Product Backlog | deliverable 列表 |
| Sprint Backlog | milestone 下的 deliverable |
| Increment | deliverable.accepted |
| Sprint Review | deliverable 评审 |
| Sprint Retrospective | 经验教训模板 |

## 参考
- Schwaber & Sutherland, *The Scrum Guide*, 2020
- Ken Rubin, *Essential Scrum*
