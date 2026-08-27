---
title: 微服务架构
description: 服务拆分、事件驱动、Saga/CQRS 与微服务治理
source: Richardson "Microservices Patterns"; Newman "Building Microservices"
version: 1.0
category: business
dimension: software-development
sub_area: microservices
type: knowledge
tags: [microservices, event-driven, saga, cqrs, service-mesh]
xref: [software-development/knowledge/backend-dev/database-design.md]
last_reviewed: 2026-08-27
---

# 微服务架构

## 服务拆分原则

| 原则 | 说明 |
|------|------|
| 单一职责 | 每个服务只负责一个业务能力 |
| 松耦合 | 服务间通过 API/事件通信，不共享数据库 |
| 高内聚 | 相关逻辑放在同一服务 |
| 领域驱动 | 按 DDD 限界上下文拆分 |

### 拆分策略

| 策略 | 说明 |
|------|------|
| 按业务域 | 用户服务、订单服务、支付服务 |
| 按操作类型 | 命令服务（写）+ 查询服务（读，CQRS） |
| 按数据边界 | 每个服务独立数据库 |

## 服务间通信

| 模式 | 特点 | 适用 |
|------|------|------|
| 同步 REST | 简单、实时 | 查询、简单操作 |
| 同步 gRPC | 强类型、高性能 | 内部服务间调用 |
| 异步消息 | 解耦、削峰 | 事件通知、最终一致性 |

### 消息队列选型

| 队列 | 特点 | 适用 |
|------|------|------|
| Kafka | 高吞吐、持久化、分区 | 事件流、日志聚合 |
| RabbitMQ | 灵活路由、ACK 保证 | 任务队列、RPC |
| Redis Stream | 轻量、低延迟 | 实时通知、轻量事件 |

## 分布式事务

### Saga 模式

| 类型 | 说明 | 回滚方式 |
|------|------|----------|
| 编排式 Saga | 中央协调器指挥步骤 | 协调器发补偿命令 |
| 协同式 Saga | 每个服务触发下一步 | 事件驱动补偿 |

### CQRS（命令查询职责分离）

```
        写请求                读请求
          ↓                     ↓
    Command Side           Query Side
    (领域模型 + 写库)      (读模型 + 读库)
          ↓                     ↑
    Domain Events  →  事件同步更新读库
```

**适用场景**：读写比悬殊、查询复杂、需要不同数据模型。

## 服务治理

### 服务发现

| 方案 | 说明 |
|------|------|
| Client-Side | 客户端从注册中心获取地址（Consul、Eureka） |
| Server-Side | 通过负载均衡器路由（K8s Service、Nginx） |

### 熔断与降级

| 模式 | 说明 |
|------|------|
| 熔断器 | 连续失败 N 次后快速失败，避免雪崩 |
| 降级 | 返回缓存/默认值，保证核心可用 |
| 限流 | 令牌桶/漏桶，保护服务不被打垮 |
| 超时 | 每层调用设置超时，避免级联阻塞 |

### 可观测性

| 维度 | 工具 | 说明 |
|------|------|------|
| 日志 | ELK / Loki | 集中化日志收集与查询 |
| Metrics | Prometheus + Grafana | 系统指标监控 |
| Tracing | Jaeger / Zipkin | 分布式链路追踪 |
| 告警 | AlertManager | 异常通知（PagerDuty、Slack） |
