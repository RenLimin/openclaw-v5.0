# L3 Office 业务维度设计文档

> L3 通用业务层组件，提供 Office 文档生产的通用业务能力（知识/模板/角色）。
>
> 依赖 L2 Office Engine (011 v2)，提供 create/read/update/parse/convert 技术能力。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L3 通用业务层 |
| 组件 ID | 012 |
| 组件名称 | Office 业务维度 |
| 状态 | 🚧 建设中 |
| ADR | ADR-202609-029 |

## 2. 设计原则

| 原则 | 说明 |
|---|---|
| **通用优先** | 只放真正跨场景通用的资产，专有内容放 L4 |
| **继承扩展** | L4 通过继承扩展 L3，不复制粘贴 |
| **格式统一** | 模板用 Markdown + frontmatter，和知识库一致 |
| **角色标准化** | 角色定义遵循 L3 角色四文件模型 |
| **变量统一** | 统一命名规范和类型体系 |

## 3. 目录结构

```
L3-business/components/office-business/
├── knowledge/              # 业务知识（规范/结构/变量体系）
│   ├── README.md           # 知识索引
│   ├── document-spec.md    # 通用文档规范
│   ├── variable-system.md  # 变量命名/类型体系
│   └── structure-guide.md # 常见文档结构指南
├── templates/             # 通用模板资产（Markdown 格式，供渲染）
│   ├── index.json         # 模板索引
│   ├── contract/           # 合同通用模板
│   │   ├── sales-contract.md
│   │   └── service-contract.md
│   ├── report/            # 通用报告模板
│   │   ├── weekly-report.md
│   │   ├── monthly-report.md
│   │   ├── quarterly-report.md
│   │   └── annual-report.md
│   ├── proposal/          # 方案通用模板
│   │   ├── project-proposal.md
│   │   └── technical-proposal.md
│   └── presentation/      # 汇报演示通用模板
│       ├── project-status.md
│       └── meeting-minutes.md
└── roles/                 # 角色定义
    ├── document-engineer/ # 文档工程师
    │   ├── SOUL.md
    │   ├── AGENTS.md
    │   └── IDENTITY.md
    └── business-analyst/  # 业务分析师
        ├── SOUL.md
        ├── AGENTS.md
        └── IDENTITY.md
```

## 4. 核心能力

### 4.1 业务知识

| 知识文档 | 内容 |
|---|---|
| **document-spec.md** | 通用文档规范：页边距/字体/标题层级/列表/表格样式等 |
| **variable-system.md** | 变量体系：命名规范/类型定义/作用域/占位格式 |
| **structure-guide.md** | 常见文档结构指南：合同/报告/方案/汇报的典型结构 |

### 4.2 通用模板

**分类：**
- `contract/`：合同通用模板（销售/服务）
- `report/`：报告通用模板（周报/月报/季报/年报）
- `proposal/`：方案通用模板（项目方案/技术方案）
- `presentation/`：汇报演示模板（项目状态/会议纪要）

**格式：** Markdown + frontmatter

**frontmatter 元数据：**
```yaml
---
title: 模板标题
description: 模板用途描述
author: 作者
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [标签1, 标签2]
variables:
  - name: variable_name
    type: string | number | date | list | table | markdown
    description: 变量说明
    required: true/false
---
```

**索引**：`index.json` 包含所有模板元数据，支持检索和筛选。

### 4.3 标准角色

#### 文档工程师 (document-engineer)
- **职责**：文档生成、格式检查、模板渲染、格式转换
- **能力边界**：只负责格式和规范，不负责内容正确性和业务逻辑
- **输出**：符合规范的最终 Office 文件

#### 业务分析师 (business-analyst)
- **职责**：数据整理、内容分析、变量填充、报告生成
- **能力边界**：基于输入数据生成内容，不做业务决策
- **输出**：填充完变量的文档内容，交付文档工程师渲染

## 5. 与其他层的关系

### 5.1 L3 → L2 依赖
```
L3 Office 业务维度
  │
  ▼
L2 Office Engine (统一 SDK)
  │
  ▼
L1 运行时抽象（文件系统 + exec）
```
- L3 只依赖 L2 统一 SDK，不直接调用底层库
- L2 提供 create/read/update/parse/convert，L3 提供业务知识/模板/角色

### 5.2 L4 → L3 继承
- L4 专有业务继承 L3 通用能力
- L4 只添加专有模板、专有变量、专有角色扩展
- L4 不复制 L3 内容，保持继承关系

## 6. 验证标准

| 验证项 | 标准 |
|---|---|
| 目录结构 | 所有目录创建完成，结构符合设计 |
| 业务知识 | 三篇核心知识文档齐全 |
| 模板 | 四个分类共 11 个模板，index.json 索引完整 |
| 角色 | 两个角色各三个文件齐全 |
| ADR + DESIGN | 文档齐全，对齐设计 |
| 通用/专有分离 | 没有专有内容混入 L3 |

## 7. 变更历史

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-09-08 | 1.0 | 初始设计 |
