---
title: "看板方法 (Kanban)"
description: "看板方法的 6 项核心实践、3 个指标，及在交付管理中的应用"
source: "David J. Anderson - Kanban Method"
version: "2020"
category: "business"
dimension: "delivery-management"
sub_area: "methodologies"
type: "industry"
tags: ["kanban", "agile", "敏捷", "精益", "可视化"]
last_reviewed: "2026-09-03"
---

# 看板方法 (Kanban Method)

## 概述
看板方法是一种渐进式变革组织的方法，通过**可视化工作流、限制在制品、管理流动**来提升交付效率。它不预设固定的角色或节奏，而是从当前状态出发，持续改进。

**核心价值观**：
- 从当前状态开始
- 追求渐进式变革
- 尊重当前的角色、职责和头衔
- 鼓励各级领导力

## 6 项核心实践

### 1. 可视化 (Visualize)
把工作流、工作项、阻塞都可视化出来。

**常见看板列**：
```
待办 → 分析 → 开发 → 测试 → 验收 → 已发布
```

**DMS 映射**：milestone / deliverable 状态机的可视化呈现

### 2. 限制在制品 (Limit WIP)
每个阶段的工作项数量设上限，强制团队专注完成而非开始新工作。

**WIP 限制设定原则**：
- 不要太松（起不到作用）
- 不要太紧（频繁阻塞）
- 从当前实际水平开始，逐步降低
- 按角色/能力设定，不是按人数

**Little's Law**：
> 平均交付周期 = 在制品数量 / 平均吞吐率

WIP 越低 → 交付周期越短 → 反馈越快

### 3. 管理流动 (Manage Flow)
关注工作项如何流过系统，识别瓶颈和等待时间。

**关键指标**：
- **交付周期 (Lead Time)**：从需求提出到交付的总时间
- **周期时间 (Cycle Time)**：从开始工作到完成的时间
- **吞吐率 (Throughput)**：单位时间完成的工作项数

**流动管理原则**：
- 减少批量
- 减少等待
- 减少切换
- 优先处理老化的工作项

### 4. 明确过程策略 (Make Process Policies Explicit)
把工作规则明确写出来，让团队对"怎么做"有共识。

**策略类型**：
- 准入条件（什么可以进入某列）
- 准出条件（什么可以离开某列）
- 优先级规则
- 阻塞处理流程

**DMS 映射**：状态机的 guard 条件 + transition 规则

### 5. 实施反馈环 (Implement Feedback Loops)
定期检视和适应。

**反馈会议**：
- 每日站会（同步）
- 看板梳理会（需求澄清）
- 运营回顾（流程改进）
- 风险回顾

### 6. 协同改进，共同进化 (Improve Collaboratively, Evolve Experimentically)
用数据驱动改进，用科学方法做实验。

**改进循环**：
```
现状 → 识别问题 → 提出假设 → 设计实验 → 执行 → 测量 → 评估 → 标准化/放弃
```

## 3 个核心指标

### 1. 累积流图 (Cumulative Flow Diagram, CFD)
- 横轴：时间
- 纵轴：各状态工作项数量（累积）
- 带宽 = WIP 数量
- 看趋势：带宽变宽 → WIP 增加 → 周期变长

### 2. 周期时间分布图 (Cycle Time Histogram)
- 横轴：周期时间区间
- 纵轴：工作项数量
- 看分布：长尾 → 不稳定 → 需预测时要注意
- **百分位数**：85% 工作项在 X 天内完成

### 3. 吞吐率图 (Throughput Run Chart)
- 横轴：时间（周/迭代）
- 纵轴：每周期完成的工作项数
- 看稳定性：波动大 → 可预测性差

## 看板 vs Scrum

| 维度 | Scrum | 看板 |
|------|-------|------|
| **节奏** | 固定 Sprint（1-4周） | 持续流动，无固定节奏 |
| **角色** | PO / SM / Dev 团队 | 无强制角色 |
| **WIP 限制** | 间接（Sprint Backlog 大小） | 直接（每列 WIP 限制） |
| **变更** | Sprint 内不改变 Goal | 随时可以 pull 新工作 |
| **度量** | 速度 (Velocity) | 周期时间/吞吐率 |
| **适用场景** | 产品开发、需求有优先级 | 运维、支持、持续交付 |

## 常见误区
1. **有白板就是看板**：没有 WIP 限制，只是任务板
2. **WIP 限制形同虚设**：经常突破 WIP，等于没设
3. **只看板不用改进**：可视化只是起点，持续改进才是目的
4. **忽略阻塞项**：阻塞项是最大的流动杀手

## 与 DMS 框架的映射
| 看板概念 | DMS 框架 |
|---------|---------|
| 看板列 | 状态机状态 |
| WIP 限制 | 状态级别的并发控制（可扩展） |
| 工作项 | deliverable / work_items |
| 周期时间 | deliverable 从开始到完成的时间 |
| 流动管理 | milestone 进度跟踪 + 阻塞识别 |
| 累积流图 | 里程碑进展可视化（可扩展） |

## 参考
- David J. Anderson, *Kanban: Successful Evolutionary Change for Your Technology Business*, 2010
- Daniel Vacanti, *Actionable Agile Metrics for Predictability*, 2015
