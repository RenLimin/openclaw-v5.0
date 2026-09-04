---
title: "知识库索引"
description: "DMS 框架知识库快速索引：9 篇文档按能力域、角色、文档类型分类一览"
source: "DMS Framework Knowledge Base Index"
category: "business"
dimension: "delivery-management"
sub_area: "knowledge-base"
type: "overview"
tags: ["index", "knowledge-base", "navigation"]
last_reviewed: "2026-09-04"
---

# 知识库索引

> DMS 框架知识库所有文档的快速索引。按能力域、角色、文档类型三种维度分类。

## 文档总览

| # | 文档 | 类型 | 所在目录 | 简介 |
|---|------|------|----------|------|
| 1 | [entity-relationship.md](data-model/entity-relationship.md) | 数据模型 | `data-model/` | ER 图、表字段、索引、表间关系 |
| 2 | [state-machines.md](data-model/state-machines.md) | 数据模型 | `data-model/` | 4 大状态机定义、迁移、事件联动 |
| 3 | [schema.sql](data-model/schema.sql) | 数据模型 | `data-model/` | 完整 DDL + 表用途注释 |
| 4 | [task-management.md](capabilities/task-management.md) | 能力文档 | `capabilities/` | 看板与 WBS 分解 |
| 5 | [issue-management.md](capabilities/issue-management.md) | 能力文档 | `capabilities/` | 问题分诊与根因分析 |
| 6 | [decision-management.md](capabilities/decision-management.md) | 能力文档 | `capabilities/` | 决策日志与审计追踪 |
| 7 | [openproject-lessons.md](references/openproject-lessons.md) | 行业参考 | `references/` | OpenProject 架构分析与借鉴 |
| 8 | [plane-lessons.md](references/plane-lessons.md) | 行业参考 | `references/` | Plane.so 架构分析与借鉴 |
| 9 | [github-projects-lessons.md](references/github-projects-lessons.md) | 行业参考 | `references/` | GitHub Projects 架构分析与借鉴 |

---

## 按能力域分类

### 项目管理域
- [entity-relationship.md](data-model/entity-relationship.md) — 项目表结构与关联
- [state-machines.md](data-model/state-machines.md) — 项目状态机
- [openproject-lessons.md](references/openproject-lessons.md) — 项目管理系统标杆

### 交付管理域
- [entity-relationship.md](data-model/entity-relationship.md) — 里程碑、交付物表结构
- [state-machines.md](data-model/state-machines.md) — 里程碑、交付物状态机
- [github-projects-lessons.md](references/github-projects-lessons.md) — 交付视图与迭代管理

### 任务管理域
- [task-management.md](capabilities/task-management.md) — 看板与 WBS 分解
- [entity-relationship.md](data-model/entity-relationship.md) — 任务数据模型
- [state-machines.md](data-model/state-machines.md) — 任务状态机

### 问题管理域
- [issue-management.md](capabilities/issue-management.md) — 问题分诊与根因分析
- [entity-relationship.md](data-model/entity-relationship.md) — 问题数据模型
- [state-machines.md](data-model/state-machines.md) — 问题状态机

### 决策管理域
- [decision-management.md](capabilities/decision-management.md) — 决策日志与审计追踪
- [entity-relationship.md](data-model/entity-relationship.md) — 决策数据模型
- [state-machines.md](data-model/state-machines.md) — 决策状态机

### 风险管理域
- [entity-relationship.md](data-model/entity-relationship.md) — 风险数据模型
- [state-machines.md](data-model/state-machines.md) — 风险状态机
- [plane-lessons.md](references/plane-lessons.md) — 现代工具风险追踪对比

### 团队与角色域
- [entity-relationship.md](data-model/entity-relationship.md) — 成员、干系人、RACI 表结构
- [openproject-lessons.md](references/openproject-lessons.md) — 角色权限与工作流参考

### 平台与架构域
- [schema.sql](data-model/schema.sql) — 完整数据库 Schema
- [entity-relationship.md](data-model/entity-relationship.md) — 整体数据架构
- [plane-lessons.md](references/plane-lessons.md) — 现代前后端分离架构参考

---

## 按角色分类

### 架构师
关注：系统设计、数据模型、可扩展性

| 优先级 | 文档 | 原因 |
|--------|------|------|
| ⭐⭐⭐ | [entity-relationship.md](data-model/entity-relationship.md) | 数据架构全景 |
| ⭐⭐⭐ | [schema.sql](data-model/schema.sql) | 精确 DDL 参考 |
| ⭐⭐ | [task-management.md](capabilities/task-management.md) | 任务域架构设计 |
| ⭐⭐ | [issue-management.md](capabilities/issue-management.md) | 问题域架构设计 |
| ⭐⭐ | [decision-management.md](capabilities/decision-management.md) | 决策域架构设计 |
| ⭐⭐ | [openproject-lessons.md](references/openproject-lessons.md) | 成熟系统架构借鉴 |
| ⭐⭐ | [plane-lessons.md](references/plane-lessons.md) | 现代架构参考 |
| ⭐⭐ | [github-projects-lessons.md](references/github-projects-lessons.md) | 数据模型演进思路 |

### 项目经理
关注：流程、方法论、模板、协作

| 优先级 | 文档 | 原因 |
|--------|------|------|
| ⭐⭐⭐ | [task-management.md](capabilities/task-management.md) | 看板与 WBS 核心方法 |
| ⭐⭐⭐ | [issue-management.md](capabilities/issue-management.md) | 问题分诊与根因分析 |
| ⭐⭐⭐ | [decision-management.md](capabilities/decision-management.md) | 决策日志与审计追踪 |
| ⭐⭐⭐ | [state-machines.md](data-model/state-machines.md) | 理解各实体生命周期 |
| ⭐⭐ | [openproject-lessons.md](references/openproject-lessons.md) | 行业最佳实践参考 |
| ⭐⭐ | [github-projects-lessons.md](references/github-projects-lessons.md) | 看板与迭代管理 |
| ⭐ | [entity-relationship.md](data-model/entity-relationship.md) | 数据结构理解（进阶） |

### 开发者
关注：API、数据结构、扩展方式

| 优先级 | 文档 | 原因 |
|--------|------|------|
| ⭐⭐⭐ | [schema.sql](data-model/schema.sql) | 直接可用的 DDL |
| ⭐⭐⭐ | [entity-relationship.md](data-model/entity-relationship.md) | 表关系与索引 |
| ⭐⭐⭐ | [state-machines.md](data-model/state-machines.md) | 状态流转规则 |
| ⭐⭐⭐ | [task-management.md](capabilities/task-management.md) | 任务域实现参考 |
| ⭐⭐⭐ | [issue-management.md](capabilities/issue-management.md) | 问题域实现参考 |
| ⭐⭐⭐ | [decision-management.md](capabilities/decision-management.md) | 决策域实现参考 |
| ⭐⭐ | [plane-lessons.md](references/plane-lessons.md) | API-First 设计参考 |

### 产品经理
关注：功能规划、用户体验、竞品分析

| 优先级 | 文档 | 原因 |
|--------|------|------|
| ⭐⭐⭐ | [task-management.md](capabilities/task-management.md) | 任务管理功能规划 |
| ⭐⭐⭐ | [issue-management.md](capabilities/issue-management.md) | 问题管理功能规划 |
| ⭐⭐⭐ | [decision-management.md](capabilities/decision-management.md) | 决策管理功能规划 |
| ⭐⭐⭐ | [plane-lessons.md](references/plane-lessons.md) | 现代 PM 工具对标 |
| ⭐⭐⭐ | [github-projects-lessons.md](references/github-projects-lessons.md) | 视图系统与灵活 |
| ⭐⭐ | [openproject-lessons.md](references/openproject-lessons.md) | 传统 PM 系统对比 |
| ⭐⭐ | [state-machines.md](data-model/state-machines.md) | 业务流程理解 |

---

## 按文档类型分类

### 技术文档（6 篇）
数据模型与系统设计类，开发者和架构师为主。

1. [entity-relationship.md](data-model/entity-relationship.md) — ER 图 + 表结构 + 索引
2. [state-machines.md](data-model/state-machines.md) — 状态机定义 + 迁移规则
3. [schema.sql](data-model/schema.sql) — 完整 DDL 脚本
4. [task-management.md](capabilities/task-management.md) — 看板与 WBS 分解
5. [issue-management.md](capabilities/issue-management.md) — 问题分诊与根因分析
6. [decision-management.md](capabilities/decision-management.md) — 决策日志与审计追踪

### 行业参考（3 篇）
开源项目分析，提供设计借鉴和行业上下文。

1. [openproject-lessons.md](references/openproject-lessons.md) — 传统开源 PM 标杆
2. [plane-lessons.md](references/plane-lessons.md) — 现代 SaaS 代表
3. [github-projects-lessons.md](references/github-projects-lessons.md) — Git 生态项目管理

### 总览文档（2 篇）
导航与入门类，所有角色均可查阅。

1. [README.md](README.md) — 知识库总览与使用指南
2. [INDEX.md](INDEX.md) — 本文件：快速索引

---

## 交叉索引表

| 文档 | 项目管理 | 交付管理 | 任务管理 | 问题管理 | 决策管理 | 风险管理 | 团队角色 | 平台架构 | 架构师 | PM | Dev | PM |
|------|:--------:|:--------:|:--------:|:--------:|:--------:|:--------:|:--------:|:--------:|:------:|:--:|:---:|:--:|
| entity-relationship.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ |
| state-machines.md | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |  |  | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| schema.sql |  |  |  |  |  |  |  | ✅ | ⭐⭐⭐ |  | ⭐⭐⭐ |  |
| task-management.md | ✅ | ✅ | ✅ |  |  |  | ✅ | ✅ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| issue-management.md |  | ✅ |  | ✅ |  | ✅ | ✅ | ✅ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| decision-management.md | ✅ | ✅ |  |  | ✅ |  | ✅ | ✅ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| openproject-lessons.md | ✅ |  |  |  |  |  | ✅ | ✅ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ |
| plane-lessons.md |  | ✅ |  |  |  | ✅ |  | ✅ | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ |
| github-projects-lessons.md |  | ✅ |  |  |  |  |  | ✅ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ |

> 图例：✅ 覆盖能力域 · ⭐ 推荐度（1-3 星）
