---
title: 数据仓库与数据建模
description: 维度建模、Data Vault 与数据仓库设计
source: Kimball "Data Warehouse Toolkit"; Kleppmann DDI
version: 1.0
category: business
dimension: software-development
sub_area: data-warehousing
type: knowledge
tags: [data-warehouse, dimensional-modeling, data-vault, star-schema]
last_reviewed: 2026-08-27
---

# 数据仓库与数据建模

## 维度建模（Kimball）

### 核心概念

| 概念 | 说明 |
|------|------|
| 事实表 | 业务度量（金额、数量、次数） |
| 维度表 | 描述属性（时间、地点、产品、用户） |
| 星型模型 | 事实表 + 直接关联的维度表 |
| 雪花模型 | 维度表进一步规范化 |

### 设计步骤

1. **选择业务过程**：订单、支付、登录...
2. **声明粒度**：一行代表什么？（一笔订单？一个订单项？）
3. **确定维度**：谁、什么、哪里、何时、为什么？
4. **确定事实**：可加、半可加、不可加

## Data Vault

| 组件 | 说明 |
|------|------|
| Hub | 业务主键（客户、产品、订单） |
| Link | 关系（客户-订单、订单-产品） |
| Satellite | 随时间变化的属性 |

**优势**：可审计、可扩展、适应变化。

## 数据分层设计

| 层级 | 粒度 | 用途 |
|------|------|------|
| ODS | 源系统粒度 | 数据备份、延迟敏感场景 |
| DWD | 清洗后明细 | 统一数据口径 |
| DWS | 轻度汇总 | 主题宽表 |
| ADS | 应用聚合 | 直接服务报表 |

## 缓慢变化维（SCD）

| 类型 | 策略 | 适用 |
|------|------|------|
| SCD1 | 覆盖旧值 | 不需要历史 |
| SCD2 | 新增行 + 时间戳 | 需要完整历史 |
| SCD3 | 新增列（当前值+旧值） | 只需上一个值 |
