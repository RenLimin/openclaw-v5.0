---
title: "任务管理知识"
description: "项目任务的分解、看板跟踪、阻塞管理和完成度量的完整生命周期方法论"
source: "Kanban Method (Anderson); Scrum Guide 2020; WBS Practice Standard (PMI)"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["task_management", "kanban", "wbs", "cycle_time", "wip_limit"]
capability: "task_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "roles/scrum-master/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/schedule-management.md"
    relation: "depends_on"
last_reviewed: "2026-09-04"
---

# 任务管理知识 Task Management

## 概述 Overview

任务管理是交付管理框架中对工作项（Task）进行分解、分配、跟踪和完成的能力。任务（Task）是 WBS（工作分解结构）的最底层可执行单元，是项目进度的最小粒度体现。

在 DMS 框架中，任务管理以**看板（Kanban）**为核心视图，提供从 backlog 到 done 的完整生命周期管理。任务管理与里程碑管理、交付物管理紧密联动：里程碑由多个任务完成，交付物关联到具体任务。

## 核心概念 Key Concepts

### 1. 任务分解 WBS
任务是 WBS 的最底层，一个任务应满足：
- **单一责任人**（assignee），不存在"两个人共同负责"
- **可验证完成标准**（DoD, Definition of Done），完成与否没有歧义
- **1-5 人天**的颗粒度，太大拆小，太小合并

### 2. 看板列与状态映射
| 看板列 | 状态 | 含义 |
|-------|------|------|
| Backlog | `backlog` | 待办池，已规划但尚未开始 |
| To Do | `todo` | 已从 backlog 拉出，准备开始 |
| In Progress | `in_progress` | 正在进行中 |
| Blocked | `blocked` | 被外部因素阻塞 |
| Done | `done` | 已完成（终态） |
| Cancelled | `cancelled` | 已取消（终态） |

### 3. WIP 限制
在制品（Work in Progress）限制是看板方法的核心约束，强制团队在开始新工作前先完成已有工作。典型 WIP = 团队人数 × 1.5。

### 4. 阻塞管理 Blocked
任务被外部依赖、资源不足等因素阻塞时，状态变为 `blocked`。阻塞任务不计入 WIP，但应是管理重点——阻塞时间越长，项目延迟风险越大。

### 5. 周期时间 Cycle Time
从任务进入 in_progress 到 done 的时间，是衡量交付效率的核心指标。周期时间越短，交付能力越强。

## 方法/流程 Methodology

DMS 框架下任务管理采用 **Kanban 拉动式流程**：

### 1. 需求收集
- 任务进入 backlog 队列
- 按优先级排序
- 初始状态：`backlog`

### 2. 拉动 Pull
- 团队成员从 backlog 中按优先级取出任务
- `backlog → todo`（通过 `pull` 迁移）
- WIP 限制约束：达到上限时不能再拉新任务

### 3. 执行 Execute
- `todo → in_progress`（通过 `start` 迁移）
- 任务负责人开始工作
- 遇到阻塞：`in_progress → blocked`（通过 `block` 迁移）
- 解除阻塞：`blocked → in_progress`（通过 `unblock` 迁移）

### 4. 完成 Complete
- `in_progress → done`（通过 `complete` 迁移）
- 满足 DoD 后标记完成
- done 是终态，不可再迁移

### 5. 取消 Cancel
- `todo → cancelled` 或 `blocked → cancelled`
- 不再需要的任务取消而非删除，保留历史记录
- cancelled 是终态

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 周期时间 Cycle Time | 任务从 in_progress 到 done 的平均时间 | 随任务类型设定 |
| 通过率 Throughput | 单位时间内完成的任务数 | 持续稳定或上升 |
| WIP 在制品数 | 非终态任务总数 | ≤ 团队人数 × 1.5 |
| 阻塞率 Blocked Rate | blocked 任务数 / 总活跃任务数 | ≤ 10% |
| 任务完成率 Completion Rate | done 任务数 / (done + cancelled) | ≥ 80% |
| 平均阻塞时长 Avg Block Duration | 任务处于 blocked 状态的平均天数 | ≤ 2 天 |

## 常见陷阱 Common Pitfalls

1. **任务粒度过大**：一个任务好几周，进度无法衡量。任务应拆到 1-5 人天粒度。
2. **没有 DoD**："完成"的定义模糊，导致"我以为做完了"和"这也叫做完了"的反复拉扯。每个任务必须有明确完成标准。
3. **阻塞不暴露**：任务被阻塞了但状态还是 in_progress，看板上看不到。阻塞必须立即改状态，可视化是看板的价值所在。
4. **WIP 没有限制**：大家同时干很多事，每个都干一点，结果什么都完不成。WIP 限制是看板的灵魂。
5. **任务积压失控**：backlog 越攒越多，从不清理。定期 groom backlog，删除不再重要的任务。
6. **取消就删除**：取消的任务直接删除，丢失历史。取消是终态，保留记录用于复盘。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `task` 模块 | 任务生命周期状态机 + 看板视图 + 事件联动 |
| `task.board()` | 按状态分组的看板视图，支持拖拽式流程 |
| `task.transition_task()` | 状态迁移：pull/start/block/unblock/complete/cancel |
| `milestone` 模块 | 里程碑包含多个任务，完成度自动计算 |
| `deliverable` 模块 | 交付物关联具体任务，任务完成触发交付物评审 |
| `project.cancelled` | 项目取消时，非终态 task 自动 cancelled |

## 参考 References

- Anderson, D.J., *Kanban: Successful Evolutionary Change for Your Technology Business*, 2010
- Scrum.org, *The Scrum Guide*, 2020 Revision
- PMI, *Practice Standard for Work Breakdown Structures*, 3rd Edition, 2019
- Reinertsen, D., *The Principles of Product Development Flow*, 2009
