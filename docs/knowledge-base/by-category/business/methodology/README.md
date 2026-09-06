---
id: METHODOLOGY-000
title: "L3 建设方法论"
description: "L3 通用业务层的建设指南和标准规范：维度设计、角色定义、知识编写、质量标准、经验沉淀五篇核心文档"
source: "L3 架构设计 v1.5"
version: "1.5"
dimension: "methodology"
sub_area: "index"
stage: "manage"
tags: ["l3", "methodology", "guide", "index"]
last_reviewed: "2026-09-06"
---

# L3 建设方法论

> L3 通用业务层的建设指南和标准规范。
> 既是建设流程的"操作手册"，也是经验沉淀的"知识容器"。

## 方法论索引

| 文档 | 内容 | 状态 |
|------|------|------|
| [dimension-design.md](./dimension-design.md) | 业务维度设计方法（六步法） | ✅ 已就绪 |
| [role-definition.md](./role-definition.md) | 角色定义规范（SOUL/AGENTS/IDENTITY） | ✅ 已就绪 |
| [knowledge-authoring.md](./knowledge-authoring.md) | 知识文档编写指南 | ✅ 已就绪 |
| [quality-standard.md](./quality-standard.md) | 质量标准与验证（六维模型） | ✅ 已就绪 |
| [lessons-learned.md](./lessons-learned.md) | 建设经验沉淀（持续更新） | ✅ 已就绪 |

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

1. **建设前**：阅读 [dimension-design.md](./dimension-design.md)，理解维度如何设计
2. **定义角色**：遵循 [role-definition.md](./role-definition.md) 四文件标准
3. **写知识**：遵循 [knowledge-authoring.md](./knowledge-authoring.md) 编写规范
4. **验证质量**：用 [quality-standard.md](./quality-standard.md) 六维模型 + `kb_index.py --validate`
5. **沉淀经验**：建设完成后更新 [lessons-learned.md](./lessons-learned.md)

## 配套资源

- 架构文档：`docs/architecture/02-generic-business-layer.md`（L3 设计总纲）
- 校验工具：`python3 scripts/kb_index.py --validate`
- 业务知识库总索引：`../README.md`

## 变更历史

- 2026-08-25: 初始化，目录结构 + 索引
- 2026-09-06: 补齐 5 篇文档 + id/stage 元数据，对齐 L3 架构 v1.5
