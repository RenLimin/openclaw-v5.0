---
title: "质量管理知识"
description: "交付物质量规划、保证、控制与持续改进的体系化方法"
source: "ISO 9001:2015; PMBOK Guide 7th Edition; CMMI V2.0"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["quality_management", "QA", "QC", "defect_management", "continuous_improvement"]
capability: "quality_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/deliverable-management.md"
    relation: "related_to"
last_reviewed: "2026-09-03"
---

# 质量管理知识 Quality Management

## 概述 Overview

质量管理是交付管理框架中确保交付物满足既定质量要求的系统性能力。它涵盖质量规划、质量保证和质量控制三大领域，目标是"第一次就把事情做对"（Do it right the first time），以最低的质量成本达成客户满意。

在 DMS 框架中，质量管理不是项目末期的检查环节，而是贯穿 **需求→设计→开发→测试→验收→运维** 全生命周期的持续活动。

## 核心概念 Key Concepts

### 1. 质量保证 vs 质量控制 QA vs QC
- **质量保证 Quality Assurance (QA)**：过程导向，关注"是否按正确的方法做"，通过审计、评审、过程改进预防缺陷
- **质量控制 Quality Control (QC)**：结果导向，关注"产出物是否符合要求"，通过测试、检验、检查发现并修复缺陷
- QA 是 QC 的上游，QA 做得好可以大幅降低 QC 的工作量

### 2. 质量成本 Cost of Quality (COQ)
- **一致性成本 Cost of Conformance**：预防成本（培训、流程、工具）+ 评估成本（测试、评审、检验）
- **非一致性成本 Cost of Non-conformance**：内部失败成本（返工、报废）+ 外部失败成本（投诉、保修、声誉损失）
- 质量管理的黄金法则：1 元预防 ≈ 10 元检测 ≈ 100 元补救

### 3. 缺陷密度 Defect Density
单位规模的缺陷数量，常用单位：缺陷数/千行代码（defects/KLOC）、缺陷数/功能点、缺陷数/页面等。是衡量交付物质量水平的核心指标。

### 4. PDCA 循环 PDCA Cycle
戴明环：Plan（计划）→ Do（执行）→ Check（检查）→ Act（处理）。每轮循环解决一批问题，推动质量持续提升。

### 5. 全面质量管理 Total Quality Management (TQM)
全员参与、全过程、全要素的质量管理理念，强调客户满意、持续改进、数据驱动和团队协作。

## 方法/流程 Methodology

DMS 框架下质量管理采用 **三大过程组 + PDCA 循环**：

### 过程一：规划质量管理 Plan Quality Management
1. 识别质量标准和要求（行业标准、客户规范、内部基线）
2. 制定质量管理计划（质量目标、QA/QC 流程、角色职责、工具方法）
3. 定义质量度量指标和验收标准
4. 输出：质量管理计划、质量测量指标、质量核对单

### 过程二：管理质量 Manage Quality (QA)
1. 过程审计：定期检查交付过程是否符合规范
2. 质量评审：需求评审、设计评审、代码评审（CR）
3. 根本原因分析（RCA）：对重大质量问题用 5-Why、鱼骨图分析根因
4. 质量改进：基于 RCA 结果更新流程、模板、检查点
5. 输出：质量报告、改进建议、经验教训

### 过程三：控制质量 Control Quality (QC)
1. 测试执行：单元测试、集成测试、系统测试、UAT
2. 缺陷管理：缺陷登记→分类→指派→修复→验证→关闭
3. 质量数据采集：缺陷数、严重度分布、修复时效
4. 质量趋势分析：控制图（Control Chart）判断过程是否稳定
5. 输出：质量控制测量结果、已批准/拒绝的变更、经验教训

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 缺陷密度 Defect Density | 严重缺陷数 / 交付规模（KLOC/功能点） | ≤ 2/KLOC（软件） |
| 缺陷修复率 Defect Fix Rate | 已关闭缺陷数 / 已发现缺陷数 | ≥ 95%（发布前） |
| 一次通过率 First Pass Yield | 首次评审/测试通过的项 / 总项数 | ≥ 80% |
| 严重缺陷占比 Critical Defect Ratio | 严重/致命缺陷数 / 总缺陷数 | ≤ 10% |
| 质量成本比 COQ Ratio | 质量活动总成本 / 项目总成本 | 15%-25%（视行业） |

## 常见陷阱 Common Pitfalls

1. **重测试轻预防**：把质量等同于测试，大量投入 QC 而忽视 QA。结果是缺陷反复出现，测试陷入"发现-修复-回归"的死循环。
2. **质量目标拍脑袋**："零缺陷"口号好听但不现实，没有可量化的质量基线就无法衡量改进效果。必须设定可度量的质量目标。
3. **质量与进度对立**：进度紧张时第一个被砍掉的是质量活动。短期看似加速，长期因返工和缺陷修复反而更慢。
4. **缺陷管理有头无尾**：缺陷提了很多但不跟踪闭环，大量缺陷遗留到客户现场。必须确保每条缺陷都有最终状态。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `quality-plan` 子模块 | 质量管理计划存储，关联 delivery_id 外键 |
| `defect-tracking` 模块 | 缺陷生命周期管理，含 defect_id, severity, priority, status, root_cause 字段 |
| `review-management` 模块 | 各阶段评审（需求/设计/代码）流程与质量门禁（quality gate） |
| `delivery-acceptance` 状态机 | 验收质量门禁：`quality_passed` 状态为 UAT 通过的前置条件 |
| `dashboard` 仪表盘 | 质量趋势图、缺陷分布饼图、质量门禁状态看板 |

## 参考 References

- ISO 9001:2015, *Quality management systems — Requirements*
- PMI, *PMBOK® Guide*, 7th Edition, 2021
- CMMI Institute, *CMMI for Development, V2.0*, 2018
- Juran, J.M., *Juran's Quality Handbook*, 7th Edition, 2016
