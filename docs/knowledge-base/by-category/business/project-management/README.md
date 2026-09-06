---
id: PM-000
title: "项目管理维度索引"
description: "L3 项目管理维度总索引：PMBOK 8th / 敏捷 / 风险管理 / 干系人管理知识库，四大角色与五类交付物模板"
source: "PMBOK 8th (2026) / Scrum Guide 2020 / ISO 31000:2018"
version: "1.0"
category: "business"
dimension: "project-management"
stage: "manage"
sub_area: "index"
type: "index"
tags: ["project-management", "index", "pmbok", "agile", "risk", "stakeholder"]
last_reviewed: "2026-09-06"
---

# 项目管理维度索引

> L3 项目管理维度（P0）—— 覆盖项目全生命周期的知识、角色与模板。
> 建设遵循 [L3 建设方法论](../methodology/README.md)（维度设计 → 角色定义 → 知识文档）。

## 维度定位

项目管理维度为软件交付项目的全生命周期提供知识支撑：从项目启动、规划、执行、监控到收尾，覆盖预测型、敏捷与混合方法。

## 知识结构

### PMBOK 第 8 版（2026）

| 文档 | 说明 |
|------|------|
| [6 条项目管理原则](knowledge/pmbok-8th/principles.md) | 价值观基础 |
| [7 个绩效域](knowledge/pmbok-8th/performance-domains.md) | 核心关注领域 |
| [40 个过程概览](knowledge/pmbok-8th/processes.md) | 按绩效域分组 |
| [方法裁剪指南](knowledge/pmbok-8th/tailoring.md) | 裁剪五步法 |

### 敏捷方法论

| 文档 | 说明 |
|------|------|
| [Scrum 指南要点](knowledge/agile/scrum-guide.md) | Scrum 框架核心 |
| [看板方法](knowledge/agile/kanban.md) | 流动管理 |
| [混合方法](knowledge/agile/hybrid.md) | 预测+敏捷组合 |
| [用户故事编写](knowledge/agile/user-stories.md) | INVEST 标准 |

### 风险管理

| 文档 | 说明 |
|------|------|
| [风险登记册](knowledge/risk-management/risk-register.md) | 风险管理流程 |
| [定性分析](knowledge/risk-management/qualitative-analysis.md) | 风险优先级 |
| [应对策略](knowledge/risk-management/response-strategies.md) | 威胁与机会应对 |

### 干系人管理

| 文档 | 说明 |
|------|------|
| [干系人识别与参与](knowledge/stakeholder-management/identification.md) | 识别与分析 |
| [干系人参与计划](knowledge/stakeholder-management/engagement-plan.md) | 参与策略 |
| [沟通管理计划](knowledge/stakeholder-management/communication-plan.md) | 沟通矩阵 |

## 角色定义（4 个）

| 角色 | 定位 | 文件 |
|------|------|------|
| [项目经理](roles/project-manager/) | 项目全生命周期管理者 | SOUL + AGENTS + IDENTITY + references |
| [Scrum Master](roles/scrum-master/) | 敏捷团队教练与促进者 | SOUL + AGENTS + IDENTITY + references |
| [产品负责人](roles/product-owner/) | 产品价值唯一责任人 | SOUL + AGENTS + IDENTITY + references |
| [项目发起人](roles/project-sponsor/) | 项目最高支持者与最终责任人 | SOUL + AGENTS + IDENTITY + references |

## 交付物模板（5 个）

| 模板 | 用途 |
|------|------|
| [WBS 模板](templates/wbs-template.md) | 工作分解结构 |
| [风险登记册](templates/risk-register.md) | 风险记录与跟踪 |
| [状态报告](templates/status-report.md) | 周报/月报 |
| [会议纪要](templates/meeting-minutes.md) | 会议记录 |
| [变更请求](templates/change-request.md) | 变更控制 |

## 质量状态

| 检查项 | 状态 |
|--------|------|
| 知识文档 | 14 篇（PMBOK 4 + 敏捷 4 + 风险 3 + 干系人 3） |
| 角色定义 | 4 个（每角色 4 文件标准） |
| 交付物模板 | 5 个 |
| kb_index.py --validate | 见验证记录（零硬错误） |

## 与相关维度的协作

| 场景 | 协作维度 | 方式 |
|------|----------|------|
| 交付 SaaS 项目 | contract-management | 合同约束交付范围 |
| 项目变更 | contract-management | 合同变更联动 |
| 实施部署 | implementation | 项目驱动实施 |
| 产品迭代 | software-development | 敏捷迭代支撑 |

## 参考资料

- L3 架构设计：`docs/architecture/02-generic-business-layer.md` §6.2
- 方法论知识库：`../methodology/README.md`
- PMBOK 第 8 版：Project Management Institute (2026)
- Scrum Guide: https://scrumguides.org/
- ISO 31000:2018

## 变更历史

- 2026-09-06: 项目管理维度 P0 建设完成 — 知识 14 篇 + 角色 4 个 + 模板 5 个
