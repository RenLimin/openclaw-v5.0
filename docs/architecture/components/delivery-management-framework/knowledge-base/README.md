---
title: "DMS 框架知识库"
description: "交付管理框架知识库总览：目录结构、使用指南、与 DMS 框架的关系"
source: "DMS Framework Knowledge Base"
category: "business"
dimension: "delivery-management"
sub_area: "knowledge-base"
type: "overview"
tags: ["knowledge-base", "dms-framework", "overview", "index"]
last_reviewed: "2026-09-03"
---

# DMS 框架知识库

> 交付管理框架（Delivery Management Framework）知识库：数据模型、参考架构、能力域、方法论、角色、模板的完整文档体系。

## 知识库定位

本知识库是 DMS 框架的**权威文档中心**，服务于三类读者：

- **架构师**：了解数据模型、系统设计、技术选型
- **项目经理**：掌握方法论、流程模板、角色职责
- **开发者**：参考 API、扩展模块、集成方式

所有文档均基于**实际代码**（数据模型部分）和**公开行业知识**（参考文档部分）编写，标注来源与版本。

## 目录结构

```
knowledge-base/
├── README.md                          ← 本文件：总览与使用指南
├── INDEX.md                           ← 快速索引：按能力域/角色/类型分类
├── data-model/                        ← 数据模型（基于实际代码）
│   ├── entity-relationship.md         ← ER 图 + 表字段 + 索引 + 关系
│   ├── state-machines.md              ← 4 大状态机定义 + 迁移 + 事件联动
│   └── schema.sql                     ← 完整 DDL + 表用途注释
├── references/                        ← 行业参考（开源项目分析）
│   ├── openproject-lessons.md         ← OpenProject 架构借鉴
│   ├── plane-lessons.md               ← Plane.so 架构借鉴
│   └── github-projects-lessons.md     ← GitHub Projects 架构借鉴
├── capabilities/                      ← 能力域文档
│   └── (各能力域说明文档)
├── methodologies/                     ← 方法论
│   └── (项目管理方法论与最佳实践)
├── roles/                             ← 角色与职责
│   └── (各角色的 RACI 与职责描述)
└── templates/                         ← 模板
    └── (项目/里程碑/交付物等模板)
```

## 与 DMS 框架的关系

```
┌─────────────────────────────────────────────────────────┐
│                    DMS 框架 (代码)                        │
│  dms-framework/                                          │
│  ├── core/         (数据库、状态机、事件总线、模块系统)      │
│  ├── modules/      (project/milestone/deliverable/risk)  │
│  └── cli/          (命令行接口)                           │
└──────────────────────────┬──────────────────────────────┘
                           │ 对应
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  知识库 (文档)                            │
│  knowledge-base/                                         │
│  ├── data-model/    ← 与 core/modules 一一对应           │
│  ├── references/    ← 行业对标与设计借鉴                  │
│  ├── capabilities/  ← 业务能力域抽象                      │
│  ├── methodologies/ ← 方法论与最佳实践                    │
│  ├── roles/         ← 角色体系                            │
│  └── templates/     ← 可复用模板                          │
└─────────────────────────────────────────────────────────┘
```

- **data-model/**：严格对应代码实现，代码变更时同步更新
- **references/**：独立于代码，提供设计决策的行业上下文
- **capabilities/** `methodologies/` `roles/` `templates/`：业务层抽象，指导框架使用和扩展

## 使用指南

### 如何检索

1. **按类型找**：
   - 想看数据库设计 → `data-model/entity-relationship.md`
   - 想看状态流转 → `data-model/state-machines.md`
   - 想看行业对标 → `references/` 目录
   - 想看快速索引 → `INDEX.md`

2. **按角色找**：见 `INDEX.md` 中的"按角色分类"

3. **按能力域找**：见 `INDEX.md` 中的"按能力域分类"

### 如何扩展

新增文档遵循以下规范：

1. **Frontmatter**：所有 Markdown 文件必须包含 YAML frontmatter：
   ```yaml
   ---
   title: "文档标题"
   description: "一句话描述"
   source: "来源（代码路径/公开资料链接）"
   category: "business"      # business / technical / operational
   dimension: "delivery-management"
   sub_area: "capabilities"  # data-model / references / capabilities / ...
   type: "reference"         # technical / industry / template / overview
   tags: ["tag1", "tag2"]
   last_reviewed: "2026-09-03"
   ---
   ```

2. **数据模型类文档**：必须基于实际代码，标注代码来源路径，禁止凭空编造

3. **参考类文档**：标注公开来源，对比分析需客观

4. **更新 INDEX.md**：新增文档后，同步在 `INDEX.md` 中注册

## 版本与维护

- **当前版本**：对应 DMS Framework v1.1.0
- **维护原则**：代码变更 → 数据模型文档同步更新
- **评审周期**：参考文档每季度评审一次，数据模型文档随代码版本发布更新
