# 知识库

> 系统建设的知识沉淀中枢。本知识库按 **3 维矩阵** 组织：层级 × 阶段 × 类别。

## 1. 三维模型

```
              设计 (Design)        开发 (Develop)        管理 (Manage)
         ┌──────────────────┬──────────────────┬──────────────────┐
系统层   │   system-design   │  system-develop  │  system-manage  │
(L1)     │                  │                  │                  │
         ├──────────────────┼──────────────────┼──────────────────┤
基础     │ infra-design     │ infra-develop    │ infra-manage    │
设施层   │                  │                  │                  │
(L2)     │                  │                  │                  │
         ├──────────────────┼──────────────────┼──────────────────┤
通用     │ generic-design   │ generic-develop  │ generic-manage  │
业务层   │                  │                  │                  │
(L3)     │                  │                  │                  │
         ├──────────────────┼──────────────────┼──────────────────┤
专有     │ proprietary-     │ proprietary-     │ proprietary-     │
业务层   │ design           │ develop          │ manage          │
(L4)     │                  │                  │                  │
         └──────────────────┴──────────────────┴──────────────────┘

每一格包含 3 类知识:
  · 业界实践 (industry-practices)
  · 理论知识 (theoretical-knowledge)
  · 项目经验 (project-experience) — 正确 & 错误
```

## 2. 目录结构

```
knowledge-base/
├── README.md                    (本文件)
├── INDEX.md                     (按主题/标签的快速索引)
│
├── by-layer/                    (按层级 — 纵深视角)
│   ├── L1-system/
│   ├── L2-infrastructure/
│   ├── L3-generic-business/
│   └── L4-proprietary-business/
│
├── by-stage/                    (按阶段 — 流程视角)
│   ├── design/
│   ├── develop/
│   └── manage/
│
├── by-category/                 (按类别 — 知识类型视角)
│   ├── industry-practices/      (业界最佳实践)
│   ├── theoretical-knowledge/   (理论知识)
│   └── project-experience/      (项目经验)
│       ├── correct/             (正确的经验 — 验证可行的方案)
│       ├── incorrect/           (错误的经验 — 踩过的坑)
│       └── README.md            (经验沉淀模型说明)
│
├── cross-cutting/               (横切关注点)
│   ├── security/
│   ├── observability/
│   ├── compliance/
│   ├── cost/
│   ├── collaboration/
│   └── knowledge-management/
│
└── templates/                   (模板)
    ├── KB-ARTICLE.md
    ├── EXPERIENCE-CARD.md
    ├── ADR.md
    └── LIBRARY-ITEM.md
```

## 3. 使用规范

### 3.1 添加知识时

每条知识必须明确：
1. **层级** (L1~L4) — 适用于哪些层
2. **阶段** (design/develop/manage) — 在哪个阶段使用
3. **类别** (industry/theory/experience) — 知识类型
4. **元数据** — 标题、标签、日期、来源、置信度

### 3.2 命名规范

- 知识文章：`KB-<序号>-<短描述>.md` (如 `KB-001-openclaw-skill-system.md`)
- 经验卡片：`EXP-<YYYYMMDD>-<短描述>.md`
- ADR：`ADR-<YYYYMM>-<短描述>.md`
- 横切专题：`CC-<主题>.md`

### 3.3 元数据规范 (frontmatter)

每篇文档必须以 YAML frontmatter 开头：

```yaml
---
title: 知识标题
layer: [L1, L2]                # 适用层级
stage: design                  # 主要阶段
category: industry-practice    # 类别
tags: [tag1, tag2]
created: 2026-08-21
updated: 2026-08-21
confidence: high               # high | medium | low
sources:                       # 来源（业界实践/理论必须有，经验可选）
  - title: 来源标题
    url: https://...
    accessed: 2026-08-21
---
```

### 3.4 检索策略

- **已知层级** → `by-layer/<L>/<stage>/`
- **已知阶段** → `by-stage/<stage>/<category>/`
- **已知类别** → `by-category/<category>/<layer>/`
- **主题/标签检索** → `INDEX.md`（按需生成）

## 4. 经验沉淀模型

详见 `by-category/project-experience/README.md`，核心规则：

- **日常/零散工作** → 经验卡片 (EXPERIENCE-CARD.md)
- **定期/架构设计** → ADR (ADR.md)
- **触发升级**：影响 ≥2 层、涉及 L1/L2 契约、需多模块对齐 → 必须升级为 ADR

## 5. 自建知识库系统 (演进目标)

详见 `../architecture/00-system-architecture.md` §5.3。
- 当前：Markdown 文件 + 元数据
- 目标：自建系统，支持人机协作阅读、跨系统移植
- 迁移策略：文件形式保留为**导出格式**

## 6. 相关文档

- 系统架构：`../architecture/00-system-architecture.md`
- 经验模型：`by-category/project-experience/README.md`
- 模板：`templates/`
