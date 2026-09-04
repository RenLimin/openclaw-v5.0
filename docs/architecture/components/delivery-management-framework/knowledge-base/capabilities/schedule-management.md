---
title: "进度管理知识"
description: "项目进度规划、排程、监控与偏差纠正的方法论"
source: "PMBOK Guide 6th/7th Edition; Critical Chain Project Management"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["schedule_management", "critical_path", "gantt", "earned_value", "baseline"]
capability: "schedule_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/scope-management.md"
    relation: "depends_on"
last_reviewed: "2026-09-03"
---

# 进度管理知识 Schedule Management

## 概述 Overview

进度管理是交付管理框架中对项目时间维度进行规划、执行、监控和调整的核心能力。它确保交付物在承诺的时间内完成，是衡量交付绩效的三大基线（范围、进度、成本）之一。

在 DMS 框架中，进度管理与范围管理、资源管理紧密耦合，形成 **范围→资源→进度** 的铁三角联动机制。

## 核心概念 Key Concepts

### 1. 关键路径法 Critical Path Method (CPM)
通过分析活动依赖关系，找出项目中最长的活动序列（关键路径）。关键路径上任何活动的延迟都会直接导致项目延期。关键路径上的活动时差（float/slack）为零。

### 2. 关键链项目管理 Critical Chain Project Management (CCPM)
考虑资源约束的排程方法，将缓冲区（buffer）放置在关键链末端和汇入点，而非每个活动末尾，以应对墨菲定律和帕金森定律。

### 3. 进度基线 Schedule Baseline
经批准的进度计划版本，用于对比实际执行情况以衡量绩效。变更需走正式 CR 流程。

### 4. 挣值管理 Earned Value Management (EVM)
将范围、进度、成本整合到一个综合指标体系中，核心三值：PV（计划值）、EV（挣值）、AC（实际成本），衍生出 SV、CV、SPI、CPI 等绩效指标。

### 5. 滚动式规划 Rolling Wave Planning
对近期工作详细规划，远期工作粗粒度规划，随项目推进逐步细化。适用于需求不确定的敏捷或混合型交付。

## 方法/流程 Methodology

DMS 框架下进度管理采用 **六步闭环**：

1. **规划进度管理 Plan Schedule Management**：在 `delivery-planning` 阶段确定排程方法、工具、准确度要求和绩效测量规则
2. **定义活动 Define Activities**：基于 WBS 工作包进一步分解为具体活动，输出活动清单（activity list）和里程碑清单
3. **排列活动顺序 Sequence Activities**：建立活动间的 FS/FF/SF/SS 依赖关系，绘制前导图（PDM）或箭线图（ADM）
4. **估算活动持续时间 Estimate Activity Durations**：采用类比估算、参数估算、三点估算（PERT = (O+4M+P)/6）等方法
5. **制定进度计划 Develop Schedule**：综合资源、约束、关键路径分析，生成甘特图（Gantt Chart）和进度基线
6. **控制进度 Control Schedule**：每周/每迭代通过 EVM、燃尽图、偏差分析监控进度，必要时发起进度变更

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 进度绩效指数 SPI | EV / PV | ≥ 0.95 |
| 进度偏差 SV | EV - PV | ≥ 0 |
| 关键路径偏差 Critical Path Variance | 关键路径实际工时 - 关键路径基线工时 | ≤ 5% |
| 里程碑达成率 Milestone Achievement Rate | 按期完成里程碑数 / 总里程碑数 | ≥ 90% |
| 活动完成率 Activity Completion Rate | 已完成活动数 / 总活动数 | 按阶段设定 |

## 常见陷阱 Common Pitfalls

1. **"拍脑袋"排期**：未基于 WBS 和活动估算直接排期，偏差可达 50% 以上。必须以分解后的活动为基础。
2. **忽略资源约束**：关键路径法不考虑资源可用性，同一人被分配到多个关键活动上导致排期失效。需做资源平衡（resource leveling）。
3. **缓冲区埋在活动内**：每个活动都加安全时间，结果帕金森定律生效——工作膨胀到填满可用时间。CCPM 将缓冲区集中管理。
4. **基线频繁变更**：每次延期就重设基线，导致基线失去参照意义。基线变更必须有正式 CR 和审批记录。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `delivery-planning` 状态机 | `schedule_baselined` 状态标记进度基线冻结 |
| `gantt-chart` 组件 | 甘特图渲染，数据源为 `activities` 表 |
| `milestone-tracking` 能力 | 关键里程碑节点与进度计划联动 |
| `earned-value` 仪表盘 | SPI/SV 等 EVM 指标计算引擎 |
| `change-request` 模块 | 进度变更通过 CR 关联 `impact_schedule` 字段 |

## 参考 References

- PMI, *PMBOK® Guide*, 7th Edition, 2021
- Goldratt, E.M., *Critical Chain*, 1997
- PMI, *Practice Standard for Earned Value Management*, 3rd Edition, 2019
