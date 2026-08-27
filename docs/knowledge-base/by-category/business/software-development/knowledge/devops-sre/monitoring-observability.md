---
title: 监控与可观测性
description: Prometheus/Grafana、ELK、SLO/SLI 与事故响应
source: Google SRE Book; Prometheus Docs; Grafana Docs
version: 1.0
category: business
dimension: software-development
sub_area: monitoring
type: knowledge
tags: [monitoring, observability, prometheus, grafana, slo, incident]
last_reviewed: 2026-08-27
---

# 监控与可观测性

## 三大支柱

| 维度 | 工具 | 说明 |
|------|------|------|
| Metrics | Prometheus + Grafana | 系统指标、业务指标 |
| Logging | ELK / Loki | 集中化日志 |
| Tracing | Jaeger / Zipkin | 分布式链路追踪 |

## SRE 核心

### SLO/SLI

| 概念 | 说明 | 示例 |
|------|------|------|
| SLI | 服务级别指标 | 可用性 99.9%、P99 延迟 < 500ms |
| SLO | 服务级别目标 | 月度可用性 ≥ 99.9% |
| 错误预算 | 1 - SLO = 允许的错误量 | 99.9% → 43min/月停机 |

### 告警原则

| 原则 | 说明 |
|------|------|
| 基于 SLO | 只告警影响 SLO 的问题 |
| 每个告警有 owner | 无人认领的告警 = 删除 |
| 分级响应 | Sev1 立即、Sev2 工作时间内 |

## 事故响应

| 阶段 | 活动 |
|------|------|
| 检测 | 告警触发 |
| 响应 | On-Call 介入、止损 |
| 恢复 | 服务恢复 |
| Post-Mortem | 24h 内产出，追因不追责 |
| 改进 | Action Item 跟踪 |

## On-Call 最佳实践

1. **Runbook**：每个告警配对应操作手册
2. **升级机制**：10min 未响应自动升级
3. **轮班合理**：单人 On-Call 不超过 1 周
