---
last_reviewed: "2026-08-25"
title: "合同管理维度"
description: "L3 通用业务层 — 合同全生命周期管理（CLM）"
source: "Agiloft / Harvey AI / Sirion CLM"
version: "CLM 2026"
category: "business"
dimension: "contract-management"
type: "dimension-index"
tags: ["contract-management", "clm", "lifecycle"]
---

# 合同管理维度

> L3 通用业务层 — 合同全生命周期管理（CLM）

## 维度定位

合同管理是软件行业交付管理的核心维度之一。合同定义了买卖双方的权利义务、
交付范围、付款条件、违约责任，是项目管理、售后管理、实施管理的法律基础。

## 知识体系

| 知识领域 | 来源 | 核心内容 |
|----------|------|----------|
| **CLM 7 阶段** | Agiloft / Sirion / Icertis | 合同全生命周期方法论 |
| **合同法** | 中国《民法典》合同编 / 美国 UCC | 合同成立、效力、履行、违约 |
| **合规** | GDPR / 等保 2.0 / 行业法规 | 数据保护、行业准入、审计要求 |
| **风险管理** | ISO 31000 | 合同风险评估、应对策略 |

## 目录结构

```
contract-management/
├── README.md                        # 本文件
├── knowledge/
│   ├── clm-lifecycle/               # CLM 全生命周期
│   │   ├── 01-intake-request.md     # 需求受理与分类
│   │   ├── 02-authoring-drafting.md # 起草与模板
│   │   ├── 03-negotiation.md        # 谈判与修订
│   │   ├── 04-approval.md           # 审批与签署
│   │   ├── 05-execution.md          # 履行与跟踪
│   │   ├── 06-renewal-amendment.md  # 续签与变更
│   │   └── 07-termination-archive.md # 终止与归档
│   ├── legal-framework/             # 法律框架
│   │   ├── contract-law-cn.md       # 中国合同法要点
│   │   ├── contract-law-us.md       # 美国 UCC 要点
│   │   ├── data-privacy.md          # 数据隐私（GDPR/个保法）
│   │   └── ip-rights.md             # 知识产权
│   └── compliance/                  # 合规
│       ├── sla-management.md        # SLA 管理
│       ├── audit-requirements.md    # 审计要求
│       └── risk-assessment.md       # 风险评估
├── roles/
│   ├── contract-manager/            # 合同经理
│   │   ├── SOUL.md
│   │   ├── AGENTS.md
│   │   └── IDENTITY.md
│   └── legal-reviewer/              # 法务审查员
│       ├── SOUL.md
│       ├── AGENTS.md
│       └── IDENTITY.md
└── templates/                       # 合同模板
    ├── nda-template.md              # 保密协议
    ├── service-agreement.md         # 服务协议
    ├── sow-template.md              # 工作说明书
    └── amendment-template.md        # 变更协议
```

## 与其他维度的协作

| 协作维度 | 协作方式 |
|----------|----------|
| 项目管理 | 合同定义项目范围和交付物，项目状态触发合同里程碑 |
| 售后管理 | 合同 SLA 驱动售后响应和升级 |
| 实施管理 | 合同约束交付范围和验收标准 |
| 产品设计 | 合同中的功能需求驱动产品规划 |

## 变更历史

- 2026-08-25: 初始化，目录结构 + 索引
