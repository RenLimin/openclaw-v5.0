---
title: "合同接口知识"
description: "交付管理与合同管理的接口规范、变更联动、索赔处理与合同履约跟踪方法"
source: "FIDIC Contracts; PMBOK Guide 7th Edition; Contract Management Body of Knowledge"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["contract_interface", "contract_management", "claim_management", "contract_change", "compliance"]
capability: "contract_interface"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/scope-management.md"
    relation: "related_to"
last_reviewed: "2026-09-03"
---

# 合同接口知识 Contract Interface

## 概述 Overview

合同接口是交付管理框架中连接合同管理与交付执行的边界能力。它确保交付活动严格遵守合同条款，合同变更及时同步到交付计划，交付绩效有据可查、有合同可依。合同是交付的 **法律基线**，所有交付活动最终都要回到合同框架下衡量。

在 DMS 框架中，合同接口是法务/商务侧与交付侧的枢纽——合同条款转化为交付约束，交付证据支撑合同结算与索赔。

## 核心概念 Key Concepts

### 1. 合同类型 Contract Types
- **固定总价合同 Firm Fixed Price (FFP)**：固定总价，风险主要在卖方。适用范围明确、变更少的项目。
- **成本加酬金合同 Cost Plus Fixed Fee (CPFF)**：实报实销 + 固定酬金，风险主要在买方。适用范围不确定的研发项目。
- **工料合同 Time and Materials (T&M)**：按工时和单价结算，兼具固定和成本补偿特点。适用范围快速启动、规模不确定的项目。
- 合同类型直接决定了交付管理的侧重点：FFP 重范围控制，CPFF 重成本透明，T&M 重工时核算。

### 2. 合同工作说明书 Statement of Work (SOW)
合同中对交付范围、交付物、验收标准、服务水平的详细描述，是交付范围的法律依据。SOW 模糊是后期争议的最大来源。

### 3. 变更令 Change Order
经合同双方签字确认的正式合同变更文件，修改合同范围、价格、工期等条款。变更令是合同变更的唯一合法形式，口头承诺不具备法律效力。

### 4. 索赔 Claim
合同一方因对方原因遭受损失，向对方提出的赔偿要求。索赔的三要素：**合同依据、事实证据、损失计算**。索赔管理的关键是文档证据链。

### 5. 合同履约跟踪 Contract Compliance Tracking
持续监控交付活动是否符合合同条款要求，包括交付物质量、进度节点、文档要求、报告义务、安全合规等。

## 方法/流程 Methodology

DMS 框架下合同接口管理采用 **五位一体** 方法：

### 1. 合同交底与转化 Contract Handoff & Translation
- 中标/签约后，商务/法务向交付团队做合同交底
- 将合同条款转化为交付约束：
  - 范围约束：SOW → WBS 映射
  - 进度约束：合同里程碑 → 项目里程碑
  - 质量约束：验收标准 → 质量计划
  - 文档约束：交付物清单 → 交付物登记册
  - 商务约束：付款节点 → 里程碑收款计划
- 输出：合同要点摘要、交付约束清单

### 2. 变更联动管理 Change Linkage Management
- 交付侧变更（范围/进度/成本）→ 评估合同影响 → 如需修改合同 → 发起变更令
- 合同侧变更（客户提出变更令）→ 同步更新交付基线 → 调整进度/资源/预算
- 关键原则：**合同变更 = 交付变更**，两者必须同步、同版本、同审批

### 3. 索赔管理 Claim Management
- **预防**：减少合同漏洞，做好文档记录，降低索赔发生概率
- **识别**：监控可能触发索赔的事件（客户延误、范围变更、条件变化）
- **评估**：分析索赔依据、计算索赔金额/工期、评估胜诉概率
- **应对**：谈判、协商、调解、仲裁/诉讼
- 输出：索赔登记册、索赔报告、谈判纪要

### 4. 付款节点跟踪 Payment Milestone Tracking
- 建立合同付款节点与交付里程碑的映射
- 每个付款节点对应：交付物清单、验收证明、发票要求
- 提前准备付款申请材料，确保收款及时

### 5. 合同收尾 Contract Closeout
- 核实所有交付物已验收通过
- 确认所有合同义务已履行
- 处理未了索赔和争议
- 归档合同文档和交付证据
- 输出：合同收尾报告、经验教训

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 合同履约率 Contract Compliance Rate | 符合合同条款的交付项 / 总合同义务项 | ≥ 98% |
| 变更令处理时效 Change Order Cycle Time | 从变更申请到签署变更令的平均天数 | ≤ 15 工作日 |
| 索赔发生率 Claim Incidence Rate | 发生索赔的合同数 / 总合同数 | ≤ 10% |
| 收款及时率 Payment Collection Rate | 按期到账金额 / 当期应收金额 | ≥ 95% |
| 合同争议率 Contract Dispute Rate | 进入争议/诉讼的合同数 / 总合同数 | ≤ 2% |

## 常见陷阱 Common Pitfalls

1. **交付团队不读合同**：项目经理只看 SOW 不看合同通用条款，踩了合同中的违约陷阱才发现。合同交底必须做透，关键条款人手一份摘要。
2. **口头变更不落地**：客户现场负责人说"先做了再说"，做完后对方公司不认账。所有变更必须有书面变更令，没有变更令就是默认没变更。
3. **证据意识薄弱**：日常沟通不记录、会议纪要不签字、交付凭证不保留，出了索赔拿不出证据。好的交付管理 = 好的文档管理。
4. **变更走交付不走合同**：内部 CR 批了但忘记同步更新合同，结算时对不上账。变更必须双轨并行：交付基线和合同同步更新。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `contract-registry` 模块 | 合同登记数据模型，含 contract_id, type, SOW_ref, payment_terms, clauses 字段 |
| `change-request` 模块 | CR 自动关联合同影响评估，触发变更令流程 |
| `deliverable-management` 能力 | 交付物验收记录作为合同履约证据链 |
| `milestone-tracking` 能力 | 里程碑与合同付款节点映射，支持收款触发 |
| `claim-management` 子模块 | 索赔登记、证据管理、索赔跟踪全流程 |

## 参考 References

- FIDIC, *Conditions of Contract for Construction (Red Book)*, 2017
- PMI, *PMBOK® Guide*, 7th Edition, 2021
- NCMA, *Contract Management Body of Knowledge (CMBOK)*, 7th Edition, 2019
