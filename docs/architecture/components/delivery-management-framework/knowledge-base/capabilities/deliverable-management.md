---
title: "交付物管理知识"
description: "交付物定义、版本控制、评审流转与验收归档的全生命周期管理方法"
source: "ISO 10007:2017; Configuration Management; IEEE 828-2012"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["deliverable_management", "configuration_management", "version_control", "acceptance", "baseline"]
capability: "deliverable_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/quality-management.md"
    relation: "depends_on"
last_reviewed: "2026-09-03"
---

# 交付物管理知识 Deliverable Management

## 概述 Overview

交付物管理是交付管理框架中对所有向客户或内部干系人提交的产出物进行定义、创建、评审、版本控制、验收和归档的能力。交付物（deliverable）是项目价值的最终载体，交付物管理的水平直接决定客户感知质量。

在 DMS 框架中，交付物管理是连接 **范围管理（定义做什么）** 和 **验收管理（确认做完了）** 的桥梁，每个交付物都有明确的生命周期状态。

## 核心概念 Key Concepts

### 1. 交付物分类 Deliverable Classification
- **可交付成果 Deliverable**：为完成项目而必须产出的任何独特并可核实的产品、成果或服务能力
- 按类型分：文档类（需求规格书、设计文档、用户手册）、代码类（源代码、安装包）、服务类（培训、运维支持）、硬件类（设备、物料）
- 按去向分：内部交付物（中间产物，供下一阶段使用）、外部交付物（提交给客户）

### 2. 配置管理 Configuration Management
建立和维护产品/交付物在其整个生命周期内的完整性和可追溯性的学科。核心活动：配置识别、配置控制、配置状态报告、配置审计。

### 3. 交付物基线 Deliverable Baseline
经正式批准的交付物版本，作为后续变更和比较的基准。基线变更必须通过正式的变更控制流程。常见基线：功能基线、分配基线、产品基线。

### 4. 交付物状态模型 Deliverable Status Model
交付物从创建到归档的标准生命周期：
`Draft → Review → Revised → Approved → Baseline → Delivered → Accepted → Archived`

### 5. 配置项 Configuration Item (CI)
配置管理中被单独标识和控制的交付物单元，每个 CI 有唯一标识符、版本号、状态记录和变更历史。

## 方法/流程 Methodology

DMS 框架下交付物管理采用 **六步生命周期法**：

1. **定义交付物 Define Deliverables**：
   - 在范围规划阶段创建交付物清单（Deliverables List）
   - 明确每个交付物的名称、编号、类型、格式要求、质量标准、验收标准、提交时间、接收人
   - 建立 WBS 与交付物的映射关系

2. **创建与版本控制 Create & Version Control**：
   - 按模板创建交付物，使用语义化版本号（主版本.次版本.修订号）
   - 主版本：重大变更或基线变更
   - 次版本：内容增加但不影响基线
   - 修订号：错误修正、格式调整

3. **评审与批准 Review & Approve**：
   - 内部评审（peer review）→ 项目经理审核 → 客户/干系人审批
   - 评审意见必须逐条响应，未关闭的意见不得进入下一状态
   - 批准后进入 Baseline 状态，形成正式基线

4. **提交与交付 Submit & Deliver**：
   - 通过 DMS 交付通道提交，生成交付凭证（delivery receipt）
   - 记录交付时间、交付版本、接收人、交付方式
   - 关联到对应里程碑

5. **验收与关闭 Accept & Close**：
   - 客户在验收窗口期内反馈意见
   - 通过验收：状态转为 Accepted，签署验收确认书
   - 未通过：返回 Revised 状态，启动缺陷修复或变更流程

6. **归档与回溯 Archive & Trace**：
   - 项目关闭后所有交付物归档入库
   - 保留完整版本历史和变更记录
   - 支持按版本、时间、干系人多维度检索

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 交付物按时交付率 On-time Delivery Rate | 按期交付的交付物数 / 计划交付物总数 | ≥ 90% |
| 一次通过率 First-time Acceptance Rate | 首次提交即通过验收的交付物数 / 总交付物数 | ≥ 80% |
| 版本合规率 Version Compliance Rate | 符合版本命名规范的交付物版本数 / 总版本数 | 100% |
| 评审周期 Review Cycle Time | 从提交评审到评审完成的平均时长 | ≤ 3 工作日 |
| 交付物完整度 Deliverable Completeness | 已交付且验收通过的交付物数 / 合同约定交付物总数 | 验收时 100% |

## 常见陷阱 Common Pitfalls

1. **交付物定义模糊**：合同和 SOW 中对交付物描述笼统，后期对"交什么、交到什么程度"产生争议。必须在项目初期细化交付物清单并签字确认。
2. **版本管理混乱**：文件名用"最终版""最终版_final""真的最终版"，分不清哪个是最新版本。必须使用统一的版本控制系统和命名规范。
3. **评审走过场**：评审人只签字不细看，问题到客户侧才暴露。必须建立评审责任制，评审意见可追溯，评审质量纳入考核。
4. **交付物与变更不同步**：范围变更了但交付物清单没更新，导致该交的没交、不该交的做了。变更请求必须自动触发交付物清单更新。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `deliverable-registry` 模块 | 交付物登记册数据模型，含 deliverable_id, type, version, status, owner 字段 |
| `delivery-workflow` 引擎 | 驱动交付物状态流转，支持多级审批配置 |
| `document-repository` 存储 | 交付物文件存储，关联版本历史（version_history 表） |
| `delivery-acceptance` 状态机 | `deliverables_accepted` 状态由交付物验收结果触发 |
| `change-request` 模块 | CR 批准后自动更新受影响的交付物条目 |

## 参考 References

- ISO 10007:2017, *Quality management — Guidelines for configuration management*
- IEEE 828-2012, *Standard for Software Configuration Management Plans*
- PMI, *PMBOK® Guide*, 7th Edition, 2021
- ITIL 4, *Service Transition*, 2019
