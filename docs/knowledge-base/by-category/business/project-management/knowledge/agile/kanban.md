---
title: "看板方法（Kanban）"
description: "看板方法的核心原则、实践和适用场景"
source: "Kanban Method (David J. Anderson)"
version: "Kanban 2024"
category: "industry-practice"
dimension: "project-management"
sub_area: "agile"
type: "industry-practice"
tags: ["project-management", "agile", "kanban", "flow"]
last_reviewed: "2026-08-25"
---

# 看板方法（Kanban）

> 看板是一种流程优化方法，通过可视化工作流、限制在制品来提升流动效率。

## 核心原则

1. **从现有流程开始**：不推翻重来，渐进式改进
2. **追求增量变革**：小步快跑，避免大爆炸式变革
3. **尊重现有角色**：不改变组织结构和职责
4. **鼓励领导力**：每个人都可以提出改进建议

## 六项核心实践

| 实践 | 说明 |
|------|------|
| **可视化工作流** | 看板列 = 工作阶段，卡片 = 工作项 |
| **限制在制品（WIP）** | 每列设置 WIP 上限，防止过载 |
| **管理流动** | 关注工作项的流动速度，识别瓶颈 |
| **明确流程规则** | 定义每列的进入/退出标准 |
| **建立反馈环** | 每日站会、回顾会等 |
| **协作改进** | 基于数据持续优化 |

## 看板设计

### 基础看板

```
待办 (Backlog) → 进行中 (In Progress) → 完成 (Done)
```

### 典型软件开发看板

```
待办 → 分析 → 开发 → 代码审查 → 测试 → 部署 → 完成
  ↑         ↑       ↑          ↑        ↑
 WIP:5    WIP:3   WIP:3     WIP:2    WIP:2
```

### WIP 限制计算
- 每列 WIP = 该列人数 × 1.5（初始值）
- 根据实际流动情况调整
- 瓶颈列 WIP 最低

## 关键指标

| 指标 | 说明 | 目标 |
|------|------|------|
| **前置时间（Lead Time）** | 从开始到完成的总时间 | 越短越好 |
| **周期时间（Cycle Time）** | 从开始处理到完成的时间 | 越短越好 |
| **吞吐量（Throughput）** | 单位时间完成的工作项数 | 越高越好 |
| **在制品（WIP）** | 当前进行中的工作项数 | 越低越好 |
| **流动效率** | 处理时间 / 前置时间 | 越高越好 |

## 看板 vs Scrum

| 维度 | 看板 | Scrum |
|------|------|-------|
| 迭代 | 无固定迭代 | 固定 Sprint（2-4 周） |
| 角色 | 无新增角色 | PO / SM / 团队 |
| 变更 | 随时可变更 | Sprint 内不变更 |
| WIP 限制 | 核心实践 | 隐含（Sprint Backlog） |
| 适用场景 | 运维/支持/持续交付 | 产品开发/项目交付 |

## 混合方法：Scrumban
- 保留 Scrum 的 Sprint 和角色
- 引入看板的 WIP 限制和流动管理
- 适合从 Scrum 向看板过渡的团队

## 参考资料

- David J. Anderson: "Kanban: Successful Evolutionary Change for Your Technology Business"
- Kanban University: https://kanban.university/
