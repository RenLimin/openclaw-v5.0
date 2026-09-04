---
title: "GitHub Projects 架构借鉴分析"
description: "GitHub Projects (Classic + Next-gen) 架构与设计分析，以及对 DMS 框架的借鉴价值与对比"
source: "公开资料 · GitHub Docs (docs.github.com) · GitHub Engineering Blog"
category: "business"
dimension: "delivery-management"
sub_area: "references"
type: "industry"
tags: ["github", "projects", "reference", "architecture", "kanban", "lessons-learned"]
last_reviewed: "2026-09-03"
---

# GitHub Projects 架构借鉴分析

> 来源：docs.github.com · GitHub Engineering Blog · 基于公开文档的架构推断与分析

## 1. 两代 Projects 对比

GitHub 有两代 Projects 系统，代表了两种截然不同的设计哲学。

| 维度 | Projects Classic | Projects (Next-gen) |
|------|-----------------|---------------------|
| 发布时间 | 2016 | 2022 (Beta) / 2023 (GA) |
| 核心模型 | 看板 + Issue 卡片 | 数据库式项目表 + 自定义字段 |
| 视图 | 仅看板 | 表格/看板/路线图/甘特 |
| 字段 | 固定（note + label + assignee） | 完全自定义字段 |
| 分组 | 按列 (To Do/In Progress/Done) | 按任意字段分组 |
| 自动化 | 基础（列名匹配状态） | Workflows + 自定义规则 |
| 跨仓库 | 不支持 | 原生支持跨仓库/跨组织 |

## 2. 架构亮点与可借鉴设计

### 2.1 统一 Issue 模型

GitHub 的核心设计哲学：**Issue 是一切工作的原子单位**。
- Issue 同时承载 bug、feature、task、discussion
- Projects 只是 Issue 的"视图"，不复制数据
- 一个 Issue 可出现在多个 Project 中

**DMS 对照**：DMS 的 `work_items` 统一表思路与此一致，但 DMS 是"拥有"数据而不是"视图"。可考虑支持跨项目引用。

### 2.2 Next-gen Projects 的数据库式设计

Next-gen Projects 的最大创新：**项目本身就是一张可自定义的数据库表**。

- 每个 Project 有自己的 schema（自定义字段集合）
- 字段类型：text/number/date/single select/iteration/tracks/link
- 视图只是这张表的不同呈现方式
- 支持类似 Airtable 的字段公式

**DMS 可借鉴**：DMS 的 `custom_fields` + `metadata` 模式是轻量版实现。可进一步发展为"项目即数据库"模型。

### 2.3 迭代字段 (Iteration Field)

Next-gen Projects 的 Iteration 字段设计精巧：
- 不是独立实体，而是一种字段类型
- 有开始/结束日期，可自动递增
- Sprint 规划天然支持

**DMS 可借鉴**：Iteration 作为字段类型而非独立实体，大大简化了数据模型。

### 2.4 Workflows 自动化

GitHub Projects 的 Workflow 自动化基于规则引擎：
- 触发器：issue 创建、标签变更、PR 合并等
- 动作：移动到某列、设置字段值、添加评论
- 声明式配置，无需代码

**DMS 可借鉴**：当前 DMS 通过事件总线 + 硬编码订阅实现自动化。可引入声明式规则引擎降低使用门槛。

### 2.5 看板列与状态的松耦合

Classic Projects 中，看板列名与 Issue 状态没有强制绑定，用户可以自由命名列。
Next-gen 中，通过"按状态分组"实现列与状态的映射。

**DMS 对照**：DMS 状态机的 `category` 属性（todo/in_progress/done/blocked/cancelled）本质上就是看板分组，思路一致。

## 3. 与 DMS 框架的对比

| 维度 | GitHub Projects | DMS 框架 |
|------|----------------|----------|
| 定位 | Git 生态中的项目管理视图 | 独立的交付管理框架 |
| 数据模型 | Issue + Project 视图层 | work_items 统一实体表 |
| 自定义 | Next-gen 完全自定义字段 | custom_fields + metadata |
| 状态管理 | Issue 状态 + 看板列映射 | 状态机 + category 分组 |
| 视图 | 表格/看板/路线图 | 无（框架层） |
| 自动化 | Workflows 规则引擎 | 事件总线 + 硬编码订阅 |
| 跨项目 | Issue 可在多 Project 中 | 每个 work_item 只属于一个 project |
| 集成 | GitHub 生态深度集成 | 框架级，待扩展集成 |
| 迭代支持 | Iteration 字段类型 | 无（可扩展） |
| API | 完整 GraphQL API | CLI + 进程内调用 |

## 4. 关键借鉴点总结

1. **视图与实体分离**：Project 是 Issue 的视图而非容器，这种松耦合支持更灵活的组织方式。DMS 可增加"视图"概念
2. **项目即数据库**：Next-gen 的自定义字段模型极其灵活，DMS 的 custom_fields 方向正确，但需增强字段类型和公式支持
3. **Iteration 作为字段**：迭代不是独立实体而是字段类型，简化模型同时满足需求
4. **声明式自动化**：Workflow 规则引擎比硬编码事件订阅更易用，适合非技术用户
5. **状态与看板列解耦**：通过 category 分组而不是状态直接映射列，增加了灵活性

## 5. 风险与教训

- GitHub Projects Classic 因功能受限逐渐被 Next-gen 取代，说明可扩展性是长期竞争力
- Next-gen 的数据库式设计学习曲线较陡，新用户上手困难，需要在灵活性和简单性间找平衡
- 深度绑定 GitHub 生态既是优势也是限制，DMS 作为独立框架应保持生态中立
- 视图系统的开发维护成本很高，DMS 作为框架应定义标准接口而非内置所有视图
