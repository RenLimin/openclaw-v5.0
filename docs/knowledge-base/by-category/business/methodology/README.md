---
last_reviewed: "2026-08-25"
title: "L3 建设方法论"
description: "L3 通用业务层的建设指南和标准规范"
source: "L3 架构设计 v1.3"
version: "1.3"
dimension: "methodology"
tags: [l3, methodology, guide]
---
# L3 建设方法论

> L3 通用业务层的建设指南和标准规范。
> 既是建设流程的"操作手册"，也是经验沉淀的"知识容器"。

## 方法论索引

| 文档 | 内容 | 状态 |
|------|------|------|
| [dimension-design.md](./dimension-design.md) | 业务维度设计方法 | 📐 设计中 |
| [role-definition.md](./role-definition.md) | 角色定义规范 | 📐 设计中 |
| [knowledge-authoring.md](./knowledge-authoring.md) | 知识文档编写指南 | 📐 设计中 |
| [quality-standard.md](./quality-standard.md) | 质量标准与验证 | 📐 设计中 |
| [lessons-learned.md](./lessons-learned.md) | 建设经验沉淀 | 📋 待首次建设后更新 |

## 核心流程

```
需求识别 → 知识调研 → 维度定义 → 角色规划 → 依赖分析 → 优先级排序
    ↓
维度建设（每个维度）
    ├── 知识文档编写
    ├── 角色定义（SOUL + AGENTS + IDENTITY）
    ├── 交付物模板
    └── 质量验证
    ↓
经验沉淀 → 更新方法论
```

## 使用方式

1. **建设前**：阅读本方法论，理解标准和流程
2. **建设中**：按方法论执行，每个维度遵循标准步骤
3. **建设后**：更新 `lessons-learned.md`，沉淀经验

## 变更历史

- 2026-08-25: 初始化，目录结构 + 索引
