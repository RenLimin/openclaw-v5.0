---
title: "风险管理知识"
description: "项目风险识别、分析、应对与监控的系统化方法"
source: "ISO 31000:2018; PMBOK Guide 7th Edition; COSO ERM"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["risk_management", "risk_assessment", "mitigation", "contingency", "issue_management"]
capability: "risk_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/issue-management.md"
    relation: "related_to"
last_reviewed: "2026-09-03"
---

# 风险管理知识 Risk Management

## 概述 Overview

风险管理是交付管理框架中识别、分析、应对和监控项目不确定性的能力。它通过主动管理潜在威胁与机会，最大化正向事件概率和影响，最小化负向事件的后果。

在 DMS 框架中，风险管理是 **前置防御层**，将隐性不确定性转化为可量化、可跟踪、可处置的登记项，避免风险演变为问题（issue）后被动救火。

## 核心概念 Key Concepts

### 1. 风险 vs 问题 Risk vs Issue
- **风险 Risk**：尚未发生的不确定事件，发生后会影响项目目标
- **问题 Issue**：已经发生的风险或已知的困难，需要立即处理
- 风险管理的目标是让风险永远停留在"潜在"状态，或在发生时已有预案

### 2. 风险概率 × 影响矩阵 Probability-Impact Matrix
将风险按发生概率（P）和影响程度（I）两个维度评级，P×I 得到风险分值（risk score），用于排序和资源分配。通常采用 5×5 矩阵。

### 3. 风险应对策略 Risk Response Strategies
- **威胁应对**：规避 Avoid、转移 Transfer、减轻 Mitigate、接受 Accept、上报 Escalate
- **机会应对**：开拓 Exploit、分享 Share、提高 Enhance、接受 Accept
- 每一条已识别风险必须指定应对策略和责任人

### 4. 风险储备 Risk Reserve
- **应急储备 Contingency Reserve**：应对已知风险（known-unknowns），项目经理可动用，纳入成本基线
- **管理储备 Management Reserve**：应对未知风险（unknown-unknowns），需高层审批，不纳入成本基线

### 5. 风险登记册 Risk Register
记录所有已识别风险的结构化文档，含风险 ID、描述、类别、概率、影响、分值、应对策略、责任人、状态、触发条件等字段。

## 方法/流程 Methodology

DMS 框架下风险管理采用 **PDCA 四阶段循环**：

1. **规划风险管理 Plan Risk Management**：在 `delivery-planning` 阶段确定风险管理方法、角色、频次、风险分类体系和评级标准
2. **识别风险 Identify Risks**：通过头脑风暴、德尔菲法、检查表、SWOT 分析、假设分析等持续识别风险，更新风险登记册
3. **实施风险分析 Perform Risk Analysis**：
   - 定性分析：概率-影响矩阵评级、风险紧迫性评估
   - 定量分析：蒙特卡洛模拟、决策树分析、敏感性分析（龙卷风图）
4. **规划风险应对 Plan Risk Responses**：针对 Top 10 高优先级风险制定具体应对措施，明确触发条件和应急方案
5. **实施风险应对 Implement Risk Responses**：按计划执行应对措施，记录效果
6. **监督风险 Monitor Risks**：每周/双周风险评审会，跟踪已识别风险、识别新风险、评估应对有效性、关闭已过时风险

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 风险数量趋势 Risk Count Trend | 当期新增风险数 - 当期关闭风险数 | 净增≤3/周 |
| 高风险占比 High Risk Ratio | 高分值风险数 / 总活跃风险数 | ≤ 15% |
| 风险应对有效率 Response Effectiveness | 成功避免/减轻的风险数 / 已触发风险数 | ≥ 70% |
| 风险燃尽率 Risk Burn-down Rate | 已关闭风险数 / 总识别风险数 | 随项目推进上升 |
| 问题转化率 Issue Conversion Rate | 演变为问题的风险数 / 总风险数 | ≤ 10% |

## 常见陷阱 Common Pitfalls

1. **风险识别走过场**：项目初期识别一次就再也不更新，风险登记册沦为摆设。必须持续迭代，每周评审。
2. **只有威胁没有机会**：风险管理只盯着负面风险，忽略正向机会（如提前交付的可能性、成本节约空间）。
3. **风险责任人模糊**："大家共同负责"等于没人负责。每条风险必须指定唯一的风险责任人（risk owner）。
4. **不设风险储备**：预算和进度中完全没有应急缓冲，一个风险触发就导致全线崩溃。一般建议预留 10%-15% 应急储备。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `risk-register` 模块 | 风险登记册数据模型，含 risk_id, probability, impact, score, owner, status 字段 |
| `delivery-planning` 状态机 | `risk_plan_approved` 状态标记风险管理计划获批 |
| `issue-tracking` 模块 | 风险触发为问题时自动创建 issue 并关联 source_risk_id |
| `change-request` 模块 | 重大风险应对可能触发范围/进度/成本变更 |
| `dashboard` 仪表盘 | 风险热力图（heatmap）、Top 10 风险列表、风险趋势图 |

## 参考 References

- ISO 31000:2018, *Risk management — Guidelines*
- PMI, *PMBOK® Guide*, 7th Edition, 2021
- COSO, *Enterprise Risk Management — Integrating with Strategy and Performance*, 2017
