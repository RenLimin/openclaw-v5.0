---
title: "问题管理知识"
description: "项目问题的识别、记录、分诊、调查、解决和关闭的完整生命周期方法论"
source: "ITIL 4 Problem Management; PMBOK Guide 7th Edition; Jira Issue Management Best Practices"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["issue_management", "problem_tracking", "triage", "root_cause", "incident"]
capability: "issue_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "roles/qa-engineer/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/risk-management.md"
    relation: "related_to"
last_reviewed: "2026-09-04"
---

# 问题管理知识 Issue Management

## 概述 Overview

问题管理是交付管理框架中对项目中出现的偏差、缺陷、障碍进行系统化跟踪和解决的能力。问题（Issue）是任何可能影响项目目标达成的事项，包括技术缺陷、资源冲突、需求变更、外部依赖阻塞等。

在 DMS 框架中，问题管理与风险管理、质量管理紧密互补：**风险是潜在的问题，问题是已发生的事件**。问题管理提供从发现到关闭的完整闭环，确保每个问题都有人跟、有方案、有结果。

## 核心概念 Key Concepts

### 1. 问题分类 Issue Categories
- **技术问题 Technical**：代码缺陷、架构缺陷、性能瓶颈、安全漏洞
- **流程问题 Process**：流程不合理、沟通不畅、审批阻塞
- **资源问题 Resource**：人员不足、设备缺失、预算超支
- **外部问题 External**：第三方依赖、供应商延迟、政策变化

### 2. 严重程度 Severity
- **Critical**：系统不可用或核心功能完全失效，需立即响应
- **High**：严重影响用户体验或项目进度，需当天处理
- **Medium**：有影响但有 workaround，需本周内处理
- **Low**：轻微影响，可排入后续迭代

### 3. 分诊 Triage
对问题进行初步评估和分类的过程，确定优先级、归属和下一步行动。分诊是问题管理的关键入口，避免重要问题淹没在噪音中。

### 4. 根因分析 Root Cause Analysis
找到问题的根本原因而非表象。常用方法：5 Whys、鱼骨图（Ishikawa）、故障树分析（FTA）。

### 5. 重开 Reopen
已解决的问题再次出现时，通过 reopen 流程回到活跃状态，而非创建新问题。重开率是问题管理质量的关键指标。

## 方法/流程 Methodology

DMS 框架下问题管理采用 **六阶段生命周期**：

### 1. 记录 Record
- 任何人发现问题均可创建，记录问题描述、严重程度、分类
- 初始状态：`open`

### 2. 分诊 Triage
- 对 open 问题进行分类和优先级排序
- 确定严重程度（severity）、分类（category）、归属人（assignee）
- `triage()` 方法按优先级+状态分组返回

### 3. 调查 Investigate
- `open → investigating`：开始调查根因
- 记录调查过程、影响范围、临时解决方案

### 4. 解决 Resolve
- `investigating → resolving`：确定修复方案并实施
- 记录修复措施、验证结果

### 5. 验证 Verify
- `resolving → resolved`：确认修复有效
- 如验证失败，可 reopen 回到 open 状态

### 6. 关闭 Close
- `resolved → closed`：最终关闭（终态）
- 也可从 open 直接 close（无需修复的问题）
- 重开：`resolved → reopened → resolving → resolved` 回路

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 问题解决周期 Time to Resolve | 从 open 到 resolved 的平均天数 | ≤ 5 天 |
| 重开率 Reopen Rate | 被 reopen 的问题数 / 已关闭问题总数 | ≤ 10% |
| 分诊覆盖率 Triage Coverage | 已分诊问题数 / 总 open 问题数 | ≥ 90% |
| 严重问题占比 Critical Ratio | Critical 问题数 / 总问题数 | ≤ 5% |
| 平均同时活跃问题数 WIP Issues | 非终态问题的平均数量 | 与团队规模匹配 |

## 常见陷阱 Common Pitfalls

1. **问题黑洞**：问题创建了没人跟，石沉大海。每个 open 问题必须有 assignee。
2. **跳过根因**：反复"修好了又出现"，因为没有做根因分析，只治标不治本。
3. **分诊疲劳**：问题太多导致分诊本身成为瓶颈。需要自动化分类和优先级建议。
4. **重开不追踪**：重开的问题和新建的问题混在一起，无法识别系统性问题。重开应保留完整历史。
5. **严重程度膨胀**：所有问题都是 High/Critical，导致真正紧急的问题被淹没。需要严重程度校准机制。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `issue` 模块 | 问题生命周期状态机 + 分诊视图 + 事件联动 |
| `issue.triage()` | 按优先级+状态分组的分诊视图，支持批量处理 |
| `issue.transition_issue()` | 状态迁移：investigate/resolve/verify/reopen/close |
| `risk` 模块 | 风险转化为问题时，issue 模块承接跟踪 |
| `quality` 模块 | 质量缺陷自动创建 issue 记录 |
| `project.cancelled` | 项目取消时，非终态 issue 自动 close |

## 参考 References

- AXELOS, *ITIL 4 Foundation*, 2019
- PMI, *PMBOK® Guide*, 7th Edition, 2021
- Atlassian, *Jira Service Management Best Practices*, 2023
- Anderson, D.J., *Kanban: Successful Evolutionary Change for Your Technology Business*, 2010
