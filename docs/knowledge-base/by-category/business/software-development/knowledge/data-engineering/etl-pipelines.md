---
title: ETL/ELT 数据管线
description: 数据抽取、转换、加载流程设计与工具实践
source: Fundamentals of Data Engineering; Airflow Docs; dbt Docs
version: 1.0
category: business
dimension: software-development
sub_area: etl-pipelines
type: knowledge
tags: [etl, elt, airflow, dbt, data-pipeline]
last_reviewed: 2026-08-27
---

# ETL/ELT 数据管线

## ETL vs ELT

| 维度 | ETL | ELT |
|------|-----|-----|
| 顺序 | 抽取→转换→加载 | 抽取→加载→转换 |
| 转换位置 | 中间引擎（Spark） | 目标数仓内（SQL） |
| 灵活性 | 转换逻辑固定 | 转换灵活，可迭代 |
| 适用 | 传统数仓 | 现代云数仓 |

## 管线设计原则

| 原则 | 说明 |
|------|------|
| 幂等性 | 重复执行结果一致 |
| 可重跑 | 失败后可从任意步骤恢复 |
| 增量处理 | 只处理变更数据，避免全量 |
| 数据校验 | 每步输出有质量检查 |
| 监控告警 | 延迟、失败、数据量异常告警 |

## 工具生态

| 工具 | 用途 |
|------|------|
| Airflow | 工作流编排、调度 |
| dbt | 数据转换（SQL 优先） |
| Spark | 大数据批处理 |
| Flink | 实时流处理 |
| Kafka | 消息队列、数据管道 |
| Great Expectations | 数据质量校验 |

## 数据分层

| 层级 | 说明 | 示例 |
|------|------|------|
| ODS | 原始数据层 | 源系统镜像 |
| DWD | 明细数据层 | 清洗后的事实表 |
| DWS | 汇总数据层 | 聚合指标 |
| ADS | 应用数据层 | 面向报表的宽表 |
