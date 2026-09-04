---
title: "RACI 在敏捷环境中的适配"
description: "敏捷团队中 RACI 的使用方式、调整点和常见模式"
source: "PMI Agile Practice Guide + 行业实践"
version: "2026"
category: "business"
dimension: "delivery-management"
sub_area: "methodologies"
type: "industry"
tags: ["raci", "agile", "敏捷", "scrum", "职责分配"]
last_reviewed: "2026-09-03"
---

# RACI 在敏捷环境中的适配

## 概述
传统 RACI 是为结构化/瀑布项目设计的，但敏捷团队同样需要清晰的职责划分——只是形式和重点不同。

**核心区别**：
| 维度 | 传统 RACI | 敏捷 RACI |
|------|----------|----------|
| 侧重点 | 层级分明、职责固化 | 团队自治、职责流动 |
| R 的数量 | 1-3 人 | 整个团队都是 R |
| 决策方式 | 自上而下 | 团队共识 + PO 拍板 |
| 更新频率 | 项目初期定，很少变 | 每个 Sprint 都可能调整 |
| 文档化程度 | 详细矩阵 | 轻量、简明 |

## 敏捷团队的角色与 RACI

### Scrum 三角色的 RACI 映射

| 任务/领域 | PO | SM | Dev 团队 |
|----------|----|----|---------|
| **产品待办列表** | A | C/I | C |
| **优先级排序** | A | I | C |
| **Sprint Goal** | R | C | A |
| **技术方案** | I | C | A/R |
| **每日站会** | I | A/Facilitator | R |
| **质量** | I | C | A/R |
| **过程改进** | C | R | A |
| **干系人沟通** | A | C | R |

### 关键洞察
1. **Dev 团队在技术上是 A**：怎么实现团队说了算
2. **PO 在"做什么"上是 A**：做什么、不做什么 PO 定
3. **SM 在过程上是 R**：流程改进 SM 负责推动
4. **Sprint Goal 是共同承诺**：团队整体 A

## 敏捷环境的 RACI 调整

### 1. R 从"个人"扩展到"团队"
敏捷中很多任务的 R 是**整个开发团队**，不是单个人。
- 传统：张三 R、李四 R
- 敏捷：Dev 团队 R（团队自组织分配具体工作）

### 2. A 的层级更清晰
不是所有决策都一个人 A，而是分领域：
- **产品决策**：PO 是 A
- **技术决策**：团队是 A（或技术负责人）
- **过程决策**：SM 是 A（引导团队）

### 3. C 和 I 的节奏不同
- 传统：里程碑式沟通
- 敏捷：持续沟通（站会、评审会、回顾会）

### 4. RACI 更轻量
不需要对每个任务做 RACI，而是对**领域/能力域**做 RACI：
- 需求管理 → PO A
- 技术实现 → 团队 A
- 质量保证 → 团队 A
- 部署运维 → DevOps 角色 A

## 敏捷 RACI 的常见模式

### 模式 1：领域责任制
每个领域有明确的 A：
```
产品领域 → PO 是 A
技术领域 → Tech Lead 是 A（或团队集体 A）
质量领域 → QA 是 A
过程领域 → SM 是 A
```

### 模式 2：特性团队 + 组件团队
- **特性团队**：端到端交付功能（R 特性交付）
- **组件团队**：提供公共组件/服务（C/R 组件支持）
- 接口处明确 RACI，避免推诿

### 模式 3：内建质量
质量不是 QA 的事，是整个团队的事：
- **质量 A**：开发团队（质量内建）
- **质量 R**：每个开发者（写测试、做 Code Review）
- **质量 C**：QA（提供测试策略和工具）

## 敏捷 RACI 模板

| 能力域 | PO | SM | Dev | QA | UX | 架构师 | 干系人 |
|--------|----|----|-----|----|----|-------|--------|
| 产品愿景 | A | I | I | I | C | C | C |
| 需求优先级 | A | I | C | I | C | C | C |
| 用户故事拆分 | R | C | C | C | R | C | I |
| 技术方案 | I | C | A/R | C | I | R | I |
| Sprint 规划 | R | C | A/R | R | R | C | I |
| 每日站会 | I | A/Facilitator | R | R | R | C | I |
| Code Review | I | I | A/R | I | I | R | I |
| 测试策略 | C | I | C | A | I | C | I |
| 自动化测试 | C | I | R | A/R | I | C | I |
| Sprint Review | R | C | R | R | R | C | A/I |
| Sprint Retrospective | C | A/Facilitator | R | R | R | C | I |
| 部署上线 | I | C | A/R | C | I | R | I |
| 过程改进 | C | R | A | C | C | C | I |

## 敏捷团队的 RACI 误区

### 1. "我们是敏捷的，不需要职责划分"
错。敏捷不是没有职责，而是职责更灵活、更流动。没有清晰的 A，决策会瘫痪。

### 2. PO 管一切
PO 只管"做什么"，不管"怎么做"。技术决策团队说了算。

### 3. SM 当项目经理用
SM 是服务式领导，不是任务分配者，也不是最终负责人。团队对 Sprint Goal 共同负责。

### 4. RACI 写得太细
敏捷响应变化，RACI 到领域级别就够了，不用到每个故事。

### 5. 忽略涌现的角色
团队中会自然涌现出 Tech Lead、UX 负责人等角色。RACI 要承认这些角色，而不是假装大家完全平等。

## 规模化敏捷中的 RACI

多团队协作时，RACI 更加重要：

| 决策层级 | A | R | C | I |
|---------|---|---|---|---|
| 产品愿景 | Product Manager | PO 团队 | SM 团队 | 所有团队 |
| 架构决策 | Chief Architect | 各团队 Tech Lead | PO 团队 | 所有团队 |
| 发布计划 | Release Train Engineer | PO 团队 | 各 SM | 所有团队 |
| 团队内技术 | 团队 Tech Lead | 团队成员 | 架构师 | PO/SM |

## 与 DMS 框架的映射
| 敏捷 RACI 概念 | DMS 框架 |
|---------------|---------|
| 领域级 RACI | raci 模块的 capability 维度 |
| 团队级 R | `member_id` 支持团队 ID（可扩展） |
| 多角色协作 | 6 个角色模板 + 12 个能力域 |
| Scrum 三角色 | product-manager / scrum-master / delivery-manager |

## 参考
- PMI, *Agile Practice Guide*, 2017
- *The Roles and Responsibilities of Agile Teams*, Scrum Alliance
- Craig Larman, *Large-Scale Scrum (LeSS)*
