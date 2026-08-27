---
title: 实时流处理
description: Flink、Kafka Streams 与实时数据处理架构
source: Flink Docs; Kafka Streams Docs; "Streaming Systems" Tyler Akidau
version: 1.0
category: business
dimension: software-development
sub_area: stream-processing
type: knowledge
tags: [stream-processing, flink, kafka, real-time, event-driven]
last_reviewed: 2026-08-27
---

# 实时流处理

## 批处理 vs 流处理

| 维度 | 批处理 | 流处理 |
|------|--------|--------|
| 数据边界 | 有界数据集 | 无界数据流 |
| 延迟 | 分钟~小时 | 毫秒~秒 |
| 工具 | Spark、Hive | Flink、Kafka Streams |
| 适用 | 离线报表、历史分析 | 实时监控、实时推荐 |

## 核心概念

### 时间语义

| 类型 | 说明 |
|------|------|
| Event Time | 事件发生时间 |
| Ingestion Time | 进入系统时间 |
| Processing Time | 处理时间 |

### 窗口类型

| 窗口 | 说明 |
|------|------|
| Tumbling | 固定大小、不重叠 |
| Sliding | 固定大小、可重叠 |
| Session | 基于活动间隔的动态窗口 |
| Global | 单一窗口，需自定义触发器 |

## 工具对比

| 工具 | 特点 |
|------|------|
| Apache Flink | 真正的流处理、精确一次语义、低延迟 |
| Kafka Streams | 轻量、与 Kafka 深度集成 |
| Spark Streaming | 微批处理、生态成熟 |
| Apache Beam | 统一批流 API、多运行时 |

## 常见模式

| 模式 | 说明 |
|------|------|
| 实时聚合 | 滑动窗口内的指标计算 |
| 事件关联 | 多流 JOIN、CEP（复杂事件处理） |
| 实时 ETL | 流式清洗、转换、加载 |
| 异常检测 | 基于规则或模型的实时告警 |

## 架构示例

```
数据源 → Kafka → Flink 处理 → 实时数仓/告警/推荐
                   ↓
              状态存储（RocksDB）
```
