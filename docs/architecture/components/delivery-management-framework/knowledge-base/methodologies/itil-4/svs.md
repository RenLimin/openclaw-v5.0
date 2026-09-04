---
title: "ITIL 4 服务价值体系 (SVS)"
description: "ITIL 4 服务价值体系的 6 个组成部分及在交付管理中的映射"
source: "AXELOS ITIL 4 Foundation"
version: "4"
category: "business"
dimension: "delivery-management"
sub_area: "methodologies"
type: "industry"
tags: ["itil", "svs", "服务管理", "价值体系"]
last_reviewed: "2026-09-03"
---

# ITIL 4 — 服务价值体系 (SVS)

## 概述
ITIL 4 是 IT 服务管理的最佳实践框架，第 4 版从"流程导向"转向"价值导向"，核心是**服务价值体系 (Service Value System, SVS)**。

**核心理念**：一切为了价值。服务提供者的所有活动，最终都应该为客户创造价值。

## SVS 架构

```
                            ┌─────────────────────────┐
                            │  指导原则 Guiding      │
                            │  Principles            │
                            └───────────┬─────────────┘
                                        │
┌─────────────────┐          ┌──────────▼────────────┐         ┌─────────────────┐
│  机会 / 需求    │ ───────→ │  服务价值链          │ ──────→ │   价值          │
│  Opportunity   │          │  Service Value Chain │         │   Value         │
└─────────────────┘          └──────────┬────────────┘         └─────────────────┘
                                        │
                            ┌───────────▼─────────────┐
                            │  治理 Governance        │
                            │  实践 Practices          │
                            │  持续改进 Continual     │
                            │  Improvement Model (CIM) │
                            └─────────────────────────┘
```

## SVS 的 6 个组成部分

### 1. 指导原则 (Guiding Principles) — 7 条
贯穿所有决策和行动的通用指导思想。

| # | 指导原则 | 含义 |
|---|---------|------|
| 1 | **聚焦价值 (Focus on Value)** | 一切从价值出发，而不是从技术/流程出发 |
| 2 | **从你所在的地方开始 (Start where you are)** | 不要从零开始，先评估现状 |
| 3 | **迭代式推进，使用反馈 (Progress iteratively with feedback)** | 小步快跑，用反馈纠偏 |
| 4 | **协作并提高可见性 (Collaborate and promote visibility)** | 跨职能协作，工作透明化 |
| 5 | **整体思考和工作 (Think and work holistically)** | 系统思维，不优化局部牺牲整体 |
| 6 | **保持简单实用 (Keep it simple and practical)** | 如果流程不增加价值，就删掉 |
| 7 | **优化和自动化 (Optimize and automate)** | 先优化流程，再考虑自动化 |

### 2. 治理 (Governance)
组织如何被指导和控制。治理框架包括：
- 评估：评估战略、合规、绩效
- 指导：设定方向、分配资源
- 监督：监控进展、风险、合规

### 3. 服务价值链 (Service Value Chain)
SVS 的核心，6 个关键活动形成价值创造的运营模式。

```
计划 ─→ 改进 ─→ 参与 ─→ 设计转换 ─→ 获取构建 ─→ 交付支持
 ↑                                                          │
 └──────────────────────────────────────────────────────────┘
```

**6 个价值链活动**：
1. **计划 (Plan)**：理解愿景、定义策略、制定计划
2. **改进 (Improve)**：持续改进服务和实践
3. **参与 (Engage)**：与干系人互动、理解需求、处理投诉
4. **设计转换 (Design & Transition)**：将需求转化为服务解决方案
5. **获取构建 (Obtain/Build)**：获取或构建服务组件
6. **交付支持 (Deliver & Support)**：交付和支持服务，确保满足约定

### 4. 实践 (Practices)
为实现特定目的而设计的一组组织资源。ITIL 4 定义了 34 个管理实践（详见 practices.md）。

分为 3 类：
- **通用管理实践**（14 个）：战略、投资、架构、风险、财务...
- **服务管理实践**（17 个）：服务台、事件、问题、变更、SLA...
- **技术管理实践**（3 个）：部署、基础设施、软件开发

### 5. 持续改进模型 (Continual Improvement Model, CIM)
7 步改进循环：
```
1. 我们愿景是什么？
2. 我们在哪里？
3. 我们想去哪里？
4. 我们怎么到达那里？
5. 我们采取行动了吗？
6. 我们到达了吗？
7. 我们怎么保持动能？
```

### 6. 机会与需求 (Opportunity & Demand)
价值创造的输入：
- **机会**：为干系人增加价值的可能性
- **需求**：干系人的产品/服务需求

价值不是单方面创造的，是**共同创造 (Co-creation)**——提供者和消费者共同创造价值。

## 服务价值链 vs 产品生命周期

| 价值链活动 | 产品阶段 | 交付管理对应 |
|-----------|---------|------------|
| 计划 | 战略/规划 | scope_management, schedule_management |
| 改进 | 运营/优化 | quality_management, 经验教训 |
| 参与 | 需求/干系人 | stakeholder_management, communication |
| 设计转换 | 设计/开发 | deliverable_management, milestone_tracking |
| 获取构建 | 实施/采购 | resource_management, contract_interface |
| 交付支持 | 运营/支持 | sla_tracking, deliverable 验收 |

## 与 PMBOK 的对比

| 维度 | ITIL 4 | PMBOK 8th |
|------|--------|-----------|
| 核心 | 服务价值体系 | 原则 + 绩效域 |
| 适用 | 服务运营、运维 | 项目交付 |
| 时间范围 | 持续（无终点） | 临时（有始有终） |
| 价值创造 | 共同创造 | 交付价值 |
| 改进 | 持续改进模型 | 经验教训 |

## 在交付管理中的应用

ITIL 4 对 DMS 框架的启发：
1. **价值导向**：每个交付物都要明确"交付什么价值"，而不只是"交付什么功能"
2. **价值链思维**：把交付过程看成一条价值链，每个环节都应该增加价值
3. **服务视角**：项目交付是"一次性服务"，SLA 同样适用
4. **持续改进**：每个项目结束都要复盘，反哺方法论
5. **实践而非流程**：提供最佳实践工具箱，让团队按需裁剪

## 与 DMS 框架的映射

| ITIL 4 概念 | DMS 框架 |
|-------------|---------|
| 服务价值链 | project 状态机 + workflow_scheme |
| 34 个实践 | 12 个能力原子 + 5 个模块 |
| 指导原则 | 各角色 SOUL + 经验知识库 |
| 持续改进模型 | 经验教训模板 + 知识库更新机制 |
| 服务价值 | deliverable 验收标准 + 价值定义 |
| SLA 管理 | sla_tracking 能力域 |

## 参考
- AXELOS, *ITIL 4 Foundation: ITIL 4 Edition*, 2019
- *ITIL 4 Service Value System Explained*, AXELOS Whitepaper
