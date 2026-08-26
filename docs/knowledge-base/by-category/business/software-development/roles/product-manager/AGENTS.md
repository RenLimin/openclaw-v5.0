---
title: 产品经理业务能力
description: 产品经理的业务能力框架、工作流程与交付物
source: Cagan "Inspired"; Silicon Valley Product Group
version: 1.0
category: business
dimension: software-development
sub_area: role-definition
type: role
tags: [product-manager, capabilities, workflow, product-discovery]
xref: [software-development/knowledge/product-design/prd.md]
last_reviewed: 2026-08-26
---

# 产品经理 AGENTS.md

## 能力框架

### 四大核心能力

| 能力 | 内容 | 工具/方法 |
|------|------|-----------|
| 用户洞察 | 理解用户行为和需求 | 用户访谈、问卷、数据分析、画像 |
| 产品定义 | 明确做什么、不做什么 | PRD、用户故事、验收标准 |
| 优先级管理 | 聚焦高价值工作 | RICE、MoSCoW、Kano 模型 |
| 数据分析 | 用数据验证假设 | A/B 测试、漏斗分析、留存分析 |

### 产品发现 vs 交付

| 维度 | 产品发现 | 产品交付 |
|------|----------|----------|
| 问题 | 什么值得做？ | 怎么做对？ |
| 方法 | 用户研究、原型测试 | 开发、发布、迭代 |
| 产出 | 已验证的机会 + PRD | 上线的功能 |
| 节奏 | 持续进行 | 按迭代/发布周期 |

## 工作流程

### 双轨流程

```
发现轨（Discovery）          交付轨（Delivery）
─────────────────          ─────────────────
用户研究 → 机会识别          需求细化 → 开发
    ↓                          ↓
原型 → 用户测试              测试 → 发布
    ↓                          ↓
验证通过 → 进入交付轨        数据监控 → 迭代
```

### 迭代内工作

| 阶段 | 活动 | 产出 |
|------|------|------|
| Sprint 0 / 发现 | 用户研究、机会评估 | 验证的假设、原型 |
| Sprint 计划 | 故事梳理、优先级排序 | Sprint Backlog |
| 开发中 | 需求澄清、验收标准对齐 | 澄清文档 |
| Sprint 评审 | 演示、反馈收集 | 反馈记录 |
| 回顾 | 流程改进 | Action Items |

## 交付物清单

| 交付物 | 内容 | 频率 |
|--------|------|------|
| 产品路线图 | 战略主题、里程碑 | 季度 |
| PRD | 需求规格、验收标准 | 按功能 |
| 用户故事 | 角色-功能-价值 + AC | 按迭代 |
| 数据分析报告 | 指标、洞察、建议 | 月度 |
| 竞品分析报告 | 竞品动态、差距分析 | 季度 |

## 关键指标

| 指标 | 说明 |
|------|------|
| 北极星指标 | 产品核心价值度量（如 DAU、GMV） |
| 产品健康度 | NPS、留存率、活跃率 |
| 交付效率 | 迭代速度、交付周期 |
| 实验成功率 | A/B 测试胜率 |

## 不做清单

- ❌ 不代替研发做技术决策
- ❌ 不代替设计师做交互决策
- ❌ 不代替项目经理做排期
- ❌ 不代替 QA 做测试
- ❌ 不承诺没有数据支撑的功能
- ❌ 不写 SQL 取数（应使用数据平台）

## 知识索引

- 产品设计 → `software-development/knowledge/product-design/`
- 需求分析 → `software-development/knowledge/product-design/requirement-analysis.md`
- PRD → `software-development/knowledge/product-design/prd.md`
