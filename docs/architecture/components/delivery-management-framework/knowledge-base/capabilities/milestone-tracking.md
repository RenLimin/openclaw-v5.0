---
title: "里程碑跟踪知识"
description: "项目里程碑定义、监控、预警与验收的系统化管理方法"
source: "PMBOK Guide 7th Edition; PRINCE2 2017; Stage-Gate Model"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["milestone_tracking", "stage_gate", "go_no_go", "checkpoint", "progress_control"]
capability: "milestone_tracking"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/schedule-management.md"
    relation: "depends_on"
last_reviewed: "2026-09-03"
---

# 里程碑跟踪知识 Milestone Tracking

## 概述 Overview

里程碑跟踪是交付管理框架中对项目关键节点（里程碑）进行定义、监控、预警和决策评审的能力。里程碑（Milestone）是项目进度中零持续时间的标记点，代表某个阶段或重要交付物的完成，是管理层掌握项目态势、进行阶段性决策的核心抓手。

在 DMS 框架中，里程碑是进度计划的"骨架"，也是 **阶段门禁（Stage-Gate）** 的载体——每个里程碑都是一次 Go/No-Go 决策点，未通过评审的项目不得进入下一阶段。

## 核心概念 Key Concepts

### 1. 里程碑 Milestone
项目中的重要事件或检查点，持续时间为零（zero-duration），标志着某个阶段、交付物或目标的完成。里程碑不是活动，而是活动完成的"结果标记"。

### 2. 阶段门控 Stage-Gate
将项目划分为若干阶段，每个阶段结束时设一个门（Gate），由决策层评审阶段成果并决定是否进入下一阶段。常见决策：Go（通过）、No-Go（终止）、Recycle（返工重做）、Conditional Go（有条件通过）。

### 3. 里程碑清单 Milestone List
项目中所有里程碑的结构化列表，含里程碑 ID、名称、计划日期、基线日期、实际日期、状态、负责人、验收标准、关联交付物等字段。

### 4. 关键里程碑 vs 检查点 Key Milestone vs Checkpoint
- **关键里程碑 Key Milestone**：影响项目整体目标的重大节点（如上线、验收、合同节点），通常需要高层审批
- **检查点 Checkpoint**：内部进度跟踪节点，频率更高（如周/双周），用于过程监控

### 5. 里程碑趋势分析 Milestone Trend Analysis (MTA)
将每个里程碑的预测完成日期随时间的变化绘制成趋势图，直观展示项目进度是在改善还是恶化。趋势线向下倾斜=延期，向上=提前，水平=稳定。

## 方法/流程 Methodology

DMS 框架下里程碑管理采用 **定义-监控-评审-决策四阶循环**：

### 1. 定义里程碑 Define Milestones
- 在规划阶段，基于 WBS 和进度计划识别关键里程碑
- 典型交付项目里程碑序列：
  - M1: 项目启动会（Kick-off）完成
  - M2: 需求规格确认
  - M3: 设计评审通过
  - M4: 开发完成/集成测试通过
  - M5: 用户验收测试（UAT）通过
  - M6: 系统上线
  - M7: 终验通过/项目关闭
- 每个里程碑必须定义：完成标准、验收交付物、评审角色、预警阈值

### 2. 监控里程碑 Monitor Milestones
- 每周/迭代更新里程碑状态（Not Started / At Risk / On Track / Delayed / Completed）
- 设置预警机制：距里程碑 ≤ 7 天且完成度 < 70% 自动标红预警
- 使用燃尽图、里程碑趋势图监控整体进度态势

### 3. 里程碑评审 Milestone Review
- 到达里程碑日期后组织评审会议
- 评审内容：阶段交付物完整性、质量达标情况、风险与问题状态、下一阶段准备度
- 输出：评审纪要、Go/No-Go 决策、待办事项列表

### 4. 决策与纠偏 Decision & Corrective Action
- Go：批准进入下一阶段，更新基线（如需）
- Conditional Go：限定条件和截止日期，满足后自动放行
- Recycle：返回上一阶段补充完善
- No-Go：项目暂停或终止，进入关闭流程

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 里程碑按时达成率 On-time Milestone Rate | 按期完成的关键里程碑数 / 关键里程碑总数 | ≥ 85% |
| 里程碑偏差天数 Milestone Variance Days | 实际完成日期 - 基线日期（天） | 平均 ≤ 3 天 |
| 里程碑预警数 Milestone Alert Count | 当期处于 At Risk/Delayed 状态的里程碑数 | ≤ 总数的 15% |
| 阶段评审一次通过率 Stage First-pass Rate | 首次评审即 Go 的里程碑数 / 评审总数 | ≥ 75% |
| 里程碑趋势指数 Milestone Trend Index | 最新预测日期变化的平均值（正=恶化，负=改善） | 趋于 0 或负值 |

## 常见陷阱 Common Pitfalls

1. **里程碑太多等于没有**：把每个活动完成都设为里程碑，导致管理层注意力分散。关键里程碑应控制在 5-10 个，覆盖整个项目周期。
2. **里程碑标准模糊**："差不多完成了""基本通过"等模糊表述导致里程碑状态主观性强。必须用可验证的交付物和量化标准定义完成条件。
3. **只报喜不报忧**：里程碑状态长期"绿色"，到了日期突然变红。鼓励暴露风险，At Risk 状态是正常的管理信号而非问责依据。
4. **阶段门控流于形式**：评审会变成"走过场"，所有项目都无条件通过。Stage-Gate 的价值在于"挡"——确实有项目被拦住才说明机制有效。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `milestone-registry` 模块 | 里程碑数据模型，含 milestone_id, planned_date, baseline_date, actual_date, status 字段 |
| `delivery-state-machine` 状态机 | 每个里程碑对应状态机的一个关键状态（如 `requirements_baselined`, `design_approved`） |
| `alert-engine` 告警引擎 | 里程碑延期/风险自动触发通知，关联 escalation_path |
| `stage-gate-review` 工作流 | 阶段门控评审流程，支持 Go/No-Go/Recycle/Conditional Go 决策 |
| `dashboard` 仪表盘 | 里程碑甘特图、状态红绿灯、趋势分析图 |

## 参考 References

- PMI, *PMBOK® Guide*, 7th Edition, 2021
- AXELOS, *PRINCE2® Guide*, 2017 Edition
- Cooper, R.G., *Winning at New Products: Creating Value Through Innovation*, 5th Edition, 2011
