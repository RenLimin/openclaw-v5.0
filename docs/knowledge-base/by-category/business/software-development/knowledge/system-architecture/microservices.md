---
title: 微服务设计
description: 服务拆分、通信模式、数据管理与容错机制
source: Sam Newman "Building Microservices"; Chris Richardson "Microservices Patterns"; Fowler "Microservices"
version: 1.0
category: business
dimension: software-development
sub_area: system-architecture
type: knowledge
tags: [microservices, service-decomposition, saga, circuit-breaker, service-mesh]
xref: [software-development/knowledge/system-architecture/architectural-patterns.md]
last_reviewed: 2026-08-26
---

# 微服务设计

## 服务拆分原则

### 按业务能力拆分

```
❌ 按技术层拆分（前端服务/后端服务/数据库服务）
✅ 按业务域拆分（订单服务/支付服务/库存服务/物流服务）
```

### DDD 限界上下文

| 概念 | 含义 |
|------|------|
| 限界上下文（Bounded Context） | 模型适用的明确边界 |
| 聚合根（Aggregate Root） | 数据一致性的最小单元 |
| 领域事件（Domain Event） | 跨上下文通信的载体 |
| 防腐层（Anti-Corruption Layer） | 隔离外部模型转换 |

### 拆分粒度判断

| 信号 | 说明 |
|------|------|
| 独立部署需求 | 不同发布节奏 → 应拆分 |
| 独立扩展需求 | 负载特征不同 → 应拆分 |
| 团队自治 | 不同团队负责 → 应拆分 |
| 技术异构 | 需要不同技术栈 → 可拆分 |
| 频繁联动修改 | 改 A 必改 B → 不应拆分 |

## 通信模式

### 同步通信

| 方式 | 协议 | 适用 |
|------|------|------|
| REST | HTTP/JSON | 通用 CRUD |
| gRPC | HTTP/2 + Protobuf | 高性能内部调用 |
| GraphQL | HTTP/JSON | 灵活查询 |

### 异步通信

| 方式 | 适用 | 说明 |
|------|------|------|
| 消息队列 | 事件通知、削峰 | Kafka, RabbitMQ, RocketMQ |
| 事件溯源 | 审计、回放 | Event Store |
| CQRS | 读写分离 | 命令/查询分离 |

### 通信选择决策

```
需要即时响应？
├── 是 → 同步（REST/gRPC）
└── 否 → 异步（消息队列）
     ├── 需要保证顺序？→ Kafka Partition
     └── 需要广播？→ Pub/Sub
```

## 数据管理

### 数据库 per 服务

```
✅ 每个服务拥有自己的数据库
✅ 服务间不直接访问对方数据库
❌ 共享数据库（分布式单体反模式）
```

### 数据一致性

| 策略 | 一致性 | 复杂度 | 适用 |
|------|--------|--------|------|
| 2PC/XA | 强一致 | 高 | 金融核心（少用） |
| Saga | 最终一致 | 中 | 跨服务事务 |
| 事件驱动 | 最终一致 | 中 | 大多数场景 |
| TCC | 最终一致 | 高 | 高一致性要求 |

### Saga 模式

| 类型 | 机制 | 优点 | 缺点 |
|------|------|------|------|
| 编排式（Choreography） | 服务间事件驱动 | 简单、松耦合 | 流程难追踪 |
| 编排式（Orchestration） | 中央协调器控制 | 流程清晰 | 单点风险 |

**Saga 示例（订单创建）**：
```
1. 订单服务：创建订单（PENDING）
2. 库存服务：扣减库存
3. 支付服务：扣款
4. 物流服务：创建运单
5. 订单服务：更新状态（CONFIRMED）

失败补偿：
- 支付失败 → 库存服务：回滚库存 → 订单服务：取消订单
```

## 容错机制

### 熔断器（Circuit Breaker）

| 状态 | 行为 |
|------|------|
| Closed | 正常转发请求 |
| Open | 快速失败，不调用下游 |
| Half-Open | 放行少量请求测试恢复 |

**触发条件**：连续 N 次失败（如 5 次/10s）→ Open
**恢复条件**：Half-Open 请求成功率 > 阈值 → Closed

### 舱壁隔离（Bulkhead）

- 线程池隔离：不同下游使用独立线程池
- 连接池隔离：限制对单一服务的连接数
- 防止一个下游故障耗尽全部资源

### 重试策略

| 策略 | 参数 | 说明 |
|------|------|------|
| 固定间隔 | 重试 3 次，间隔 1s | 简单 |
| 指数退避 | 间隔 1s → 2s → 4s | 避免雪崩 |
| 退避 + 抖动 | 随机化间隔 | 避免重试风暴 |

**幂等性要求**：重试必须保证幂等（使用唯一请求 ID）

## 服务网格（Service Mesh）

### 功能

| 功能 | 说明 |
|------|------|
| 流量管理 | 路由、负载均衡、灰度发布 |
| 安全 | mTLS、认证授权 |
| 可观测性 | 分布式追踪、指标、日志 |
| 弹性 | 熔断、重试、超时 |

### 主流实现

| 实现 | 特点 |
|------|------|
| Istio | 功能最全、社区最大 |
| Linkerd | 轻量级、Rust 实现 |
| Consul Connect | 与 HashiCorp 生态集成 |

## 可观测性三大支柱

| 支柱 | 内容 | 工具 |
|------|------|------|
| 日志（Logs） | 事件记录 | ELK, Loki |
| 指标（Metrics） | 数值度量 | Prometheus, Grafana |
| 追踪（Traces） | 请求链路 | Jaeger, Zipkin |

### 健康检查

| 类型 | 说明 |
|------|------|
| Liveness | 进程是否存活（重启判断） |
| Readiness | 是否可接收流量（注册判断） |
| Startup | 启动是否完成（慢启动保护） |

## 部署模式

| 模式 | 说明 | 适用 |
|------|------|------|
| 单实例单服务 | 每个服务独立部署 | 标准模式 |
| 蓝绿部署 | 两套环境切换 | 零停机 |
| 金丝雀发布 | 小比例流量验证 | 风险控制 |
| 特性开关 | 代码已部署，功能按需开启 | 快速回滚 |

## 常见误区

1. **微服务是目标**：微服务是手段，不是目的。单体能解决就别拆
2. **忽视分布式复杂性**：网络不可靠、时钟不同步、部分失败
3. **服务拆得太细**：运维成本 > 收益
4. **缺乏自动化**：没有 CI/CD 和监控，微服务是灾难
5. **数据一致性忽视**：最终一致性不等于不处理一致性

## 参考框架

- Newman, S. "Building Microservices" (2nd Ed)
- Richardson, C. "Microservices Patterns"
- Fowler, M. "Microservices" (martinfowler.com)
- CNCF Cloud Native Landscape
