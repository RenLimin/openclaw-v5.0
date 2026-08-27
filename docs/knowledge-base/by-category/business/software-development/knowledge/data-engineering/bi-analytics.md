---
title: BI 分析与指标体系
description: 自助 BI、指标体系设计与数据可视化
source: Measures of Success Kate Vitasek; Google HEART Framework
version: 1.0
category: business
dimension: software-development
sub_area: bi-analytics
type: knowledge
tags: [bi, analytics, metrics, kpi, dashboard]
last_reviewed: 2026-08-27
---

# BI 分析与指标体系

## 北极星指标

| 概念 | 说明 |
|------|------|
| 北极星指标 | 单一核心指标，指引产品方向 |
| 一级指标 | 按业务域拆解（获客、留存、变现） |
| 二级指标 | 按策略动作拆解 |
| 三级指标 | 按执行细节拆解 |

## 指标体系设计

### AARRR 漏斗

| 阶段 | 指标示例 |
|------|----------|
| Acquisition（获客） | 新增用户数、获客成本 |
| Activation（激活） | 首次关键行为完成率 |
| Retention（留存） | 次日/7日/30日留存率 |
| Revenue（变现） | ARPU、LTV、付费转化率 |
| Referral（推荐） | NPS、邀请转化率 |

### HEART 框架（Google）

| 维度 | 说明 |
|------|------|
| Happiness | 用户满意度 |
| Engagement | 参与度 |
| Adoption | 采纳率 |
| Retention | 留存率 |
| Task Success | 任务完成率 |

## BI 工具

| 工具 | 特点 |
|------|------|
| Apache Superset | 开源、SQL 原生 |
| Metabase | 轻量、自助查询 |
| Tableau | 企业级、可视化强 |
| Power BI | 微软生态 |
| Looker | Git 版本化、建模层 |

## 报表设计原则

1. **一页一主题**：每张报表聚焦一个业务问题
2. **对比展示**：环比、同比、目标对比
3. **下钻能力**：从汇总到明细的逐层探索
4. **异常高亮**：超出阈值的指标自动标红
