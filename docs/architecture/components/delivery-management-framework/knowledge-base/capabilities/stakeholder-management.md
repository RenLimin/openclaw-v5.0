---
title: "干系人管理知识"
description: "项目干系人识别、分析、参与策略与关系维护的方法论"
source: "PMBOK Guide 7th Edition; Salience Model; Mendelow's Matrix"
version: "1.0.0"
category: "business"
dimension: "delivery-management"
sub_area: "capabilities"
type: "industry"
tags: ["stakeholder_management", "engagement", "power_interest", "communication", "expectation_management"]
capability: "stakeholder_management"
xref:
  - path: "roles/project-manager/capability-map.md"
    relation: "referenced_by"
  - path: "capabilities/communication-management.md"
    relation: "related_to"
last_reviewed: "2026-09-03"
---

# 干系人管理知识 Stakeholder Management

## 概述 Overview

干系人管理是交付管理框架中识别受项目影响或能影响项目的个人/组织、分析其期望和影响力、制定合适参与策略的能力。交付项目失败的原因中，**干系人期望管理不当** 常年位居前三。

在 DMS 框架中，干系人管理是所有沟通、决策、变更和验收活动的基础——不知道谁说了算、谁关心什么、谁可能反对，交付就寸步难行。

## 核心概念 Key Concepts

### 1. 干系人 Stakeholder
能影响项目决策、活动或结果的个人、群体或组织，以及会受或自认为会受项目决策、活动或结果影响的个人、群体或组织。包括内部（团队、管理层）和外部（客户、供应商、监管方、用户）。

### 2. 权力-利益方格 Power-Interest Grid
Mendelow 矩阵：按 **权力（Power）** 和 **利益（Interest）** 两个维度将干系人分为四类，对应不同的管理策略：
- 高权高利：重点管理（manage closely）
- 高权低利：令其满意（keep satisfied）
- 低权高利：随时告知（keep informed）
- 低权低利：监督（monitor）

### 3. 干系人参与度评估矩阵 Stakeholder Engagement Assessment Matrix
评估干系人当前参与度（C=Current）与期望参与度（D=Desired）的差距：
- **Unaware 不知晓**：不知道项目和影响
- **Resistant 抵制**：知道但不支持
- **Neutral 中立**：知道但不支持也不反对
- **Supportive 支持**：支持项目成功
- **Leading 领导**：积极推动项目成功

### 4. 显性/隐性期望 Explicit vs Implicit Expectations
- **显性期望**：明确表述的需求和要求
- **隐性期望**：未说出口但真实存在的期望（如政治诉求、个人绩效、部门利益）
- 干系人管理的关键在于挖掘隐性期望，而非只回应显性需求

## 方法/流程 Methodology

DMS 框架下干系人管理采用 **四步循环法**：

1. **识别干系人 Identify Stakeholders**：
   - 在项目启动阶段首次识别，贯穿全生命周期持续更新
   - 方法：干系人登记问卷、组织图分析、专家判断、头脑风暴
   - 输出：干系人登记册（stakeholder register），含姓名、角色、部门、联系方式、关注点

2. **规划干系人参与 Plan Stakeholder Engagement**：
   - 使用权力-利益方格、凸显模型（Salience Model: power/legitimacy/urgency）进行分类
   - 制定每位关键干系人的参与策略和沟通计划
   - 输出：干系人参与计划

3. **管理干系人参与 Manage Stakeholder Engagement**：
   - 按计划与干系人沟通和协作
   - 处理期望、解决问题、管理冲突
   - 关键动作：定期一对一、干系人评审会、变更影响沟通

4. **监督干系人参与 Monitor Stakeholder Engagement**：
   - 跟踪参与度变化，更新参与策略
   - 识别新干系人、评估干系人关系健康度
   - 输出：工作绩效信息、变更请求

## 度量指标 Metrics

| 指标名称 | 计算公式/定义 | 健康阈值 |
|---------|-------------|---------|
| 干系人参与度指数 Engagement Index | 加权平均干系人参与水平 | ≥ Supportive 级 |
| 关键干系人满意度 Key Stakeholder Satisfaction | 定期调研评分（1-5 分） | ≥ 4.0 |
| 干系人变更频率 Stakeholder Churn Rate | 当期新增/退出关键干系人数 / 总数 | ≤ 10%/季度 |
| 冲突解决时效 Conflict Resolution Time | 从冲突上报到解决的平均时长 | ≤ 5 工作日 |
| 期望差距指数 Expectation Gap Index | 未满足的关键期望数 / 总关键期望数 | ≤ 15% |

## 常见陷阱 Common Pitfalls

1. **只盯高层忽略执行层**：关注决策者但忽视实际使用者，导致交付物在用户侧推不动。用户干系人同样重要。
2. **干系人清单一成不变**：项目初期识别一次就不再更新。组织变动、人员调整会改变干系人格局。
3. **回避抵制型干系人**：对反对者避而不见，任其负面发酵。主动沟通、理解顾虑、争取中立是更优策略。
4. **承诺过度**：为讨好干系人答应做不到的事情，后期失信反而更伤关系。管理期望比满足期望更重要。

## 与 DMS 框架的映射 DMS Framework Mapping

| DMS 模块 | 映射关系 |
|---------|---------|
| `stakeholder-registry` 模块 | 干系人登记册数据模型，含 stakeholder_id, role, power_level, interest_level 字段 |
| `communication-management` 能力 | 干系人沟通计划驱动沟通管理执行 |
| `delivery-acceptance` 状态机 | 验收阶段需指定干系人作为验收人（acceptor_id） |
| `change-request` 模块 | CR 审批链基于干系人权力层级自动生成 |
| `reporting` 模块 | 不同干系人接收不同颗粒度的报表（高管摘要 vs 详细周报） |

## 参考 References

- PMI, *PMBOK® Guide*, 7th Edition, 2021
- Mendelow, A., *Environmental scanning - The impact of the stakeholder concept*, 1991
- Mitchell, Agle & Wood, *Toward a Theory of Stakeholder Identification and Salience*, 1997
