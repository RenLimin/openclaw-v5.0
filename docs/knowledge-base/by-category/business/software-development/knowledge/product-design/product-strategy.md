---
title: 产品策略
description: 产品定位、商业模式、竞争分析与路线图规划方法论
source: Inspired by Marty Cagan "Inspired"; Geoffrey Moore "Crossing the Chasm"; Strategyzer Business Model Canvas
version: 1.0
category: business
dimension: software-development
sub_area: product-design
type: knowledge
tags: [product-strategy, business-model, competition-analysis, roadmap]
xref: [software-development/knowledge/product-design/user-research.md]
last_reviewed: 2026-08-26
---

# 产品策略

## 产品定位

### 价值主张画布（Value Proposition Canvas）

| 要素 | 问题 |
|------|------|
| 客户任务（Jobs） | 客户试图完成什么工作？ |
| 痛点（Pains） | 客户面临哪些障碍和风险？ |
| 收益（Gains） | 客户期望获得什么结果？ |
| 产品/服务 | 如何帮助客户完成任务？ |
| 止痛药（Pain Relievers） | 如何缓解客户痛点？ |
| 收益创造者（Gain Creators） | 如何创造客户期望的收益？ |

### 定位语句（Positioning Statement）

```
对于 [目标客户]，
他们 [需求/问题]，
我们的 [产品名称] 是一个 [产品类别]，
它 [关键差异化优势]。
不同于 [主要竞品]，
我们的产品 [核心区别]。
```

## 商业模式

### 商业模式画布（Business Model Canvas）

| 模块 | 内容 |
|------|------|
| 客户细分 | 为谁创造价值？哪些是最重要客户？ |
| 价值主张 | 为客户提供什么价值？ |
| 渠道通路 | 如何触达客户？ |
| 客户关系 | 建立什么类型的关系？ |
| 收入来源 | 价值如何变现？ |
| 核心资源 | 需要什么关键资产？ |
| 关键活动 | 必须做什么？ |
| 关键合作 | 谁是关键合作伙伴？ |
| 成本结构 | 主要成本是什么？ |

### SaaS 常见收入模式

| 模式 | 说明 | 适用 |
|------|------|------|
| 订阅制（Subscription） | 按月/年收费 | 标准化产品 |
| 用量计费（Usage-based） | 按 API 调用量/存储量等 | 基础设施/平台 |
| 分层定价（Tiered） | Free/Pro/Enterprise | PLG 策略 |
| 混合模式 | 基础订阅 + 超额用量 | 中大型企业 |

## 竞争分析

### 五波特模型（Porter's Five Forces）

| 力量 | 分析维度 |
|------|----------|
| 现有竞争者 | 市场集中度、差异化程度 |
| 新进入者威胁 | 技术壁垒、资金门槛、网络效应 |
| 替代品威胁 | 替代方案的成本和便利性 |
| 供应商议价能力 | 关键资源（如云服务）的集中度 |
| 买方议价能力 | 客户集中度、转换成本 |

### 竞争定位矩阵

| 维度 | 低成本 | 差异化 |
|------|--------|--------|
| 广泛市场 | 成本领先（如 AWS） | 差异化（如 Apple） |
| 细分市场 | 成本聚焦（如 niche SaaS） | 差异化聚焦（如 Figma） |

## 产品路线图

### 路线图层级

| 层级 | 时间跨度 | 内容 | 受众 |
|------|----------|------|------|
| 战略路线图 | 1-3 年 | 愿景、战略主题 | 高管、投资人 |
| 产品路线图 | 3-12 月 | 功能主题、里程碑 | 全公司 |
| 发布计划 | 1-4 周 | 具体功能、迭代 | 开发团队 |

### 路线图原则

1. **结果导向**：展示"为什么"而非"做什么"
2. **Now/Next/Later**：避免精确日期承诺
3. **主题化**：按用户价值主题组织，而非功能列表
4. **可调整**：每季度回顾，根据反馈调整
5. **依赖透明**：标注跨团队依赖和风险

## PMF（Product-Market Fit）

### 衡量指标

| 指标 | 阈值 | 说明 |
|------|------|------|
| NPS | > 40 | 净推荐值 |
| 留存率（D30） | > 40% | 30 天留存 |
| 有机增长占比 | > 30% | 非付费获客比例 |
| Sean Ellis 测试 | > 40% | "如果产品消失你会非常失望"占比 |

### PMF 达成路径

```
探索 → 验证 → 增长 → 规模化
 ↑      ↑      ↑       ↑
假设    MVP    渠道    组织
```

## 常见误区

1. **功能堆砌**：没有清晰的价值主张，靠功能数量竞争
2. **过早规模化**：PMF 验证前投入大量营销
3. **忽视留存**：只看新增不看留存，增长漏斗漏水
4. **拍脑袋决策**：不基于用户研究和数据，凭直觉
5. **路线图太细**：过早承诺具体功能和日期

## 参考框架

- Cagan, M. "Inspired: How to Create Tech Products Customers Love"
- Moore, G. "Crossing the Chasm"
- Osterwalder, A. "Business Model Canvas"
- Ries, E. "The Lean Startup"
