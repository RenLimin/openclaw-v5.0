---
title: 架构模式
description: 单体、微服务、事件驱动、CQRS、六边形架构等核心模式对比与选型
source: Martin Fowler "Patterns of Enterprise Application Architecture"; Clean Architecture (Robert C. Martin); Building Microservices (Sam Newman)
version: 1.0
category: business
dimension: software-development
sub_area: system-architecture
type: knowledge
tags: [architecture, microservices, event-driven, CQRS, hexagonal]
xref: [software-development/knowledge/system-architecture/microservices.md]
last_reviewed: 2026-08-26
---

# 架构模式

## 核心模式对比

### 单体架构（Monolithic）

| 维度 | 说明 |
|------|------|
| 结构 | 所有功能在一个进程/部署单元 |
| 优点 | 简单、易部署、易调试、事务简单 |
| 缺点 | 扩展困难、技术栈锁定、代码库膨胀 |
| 适用 | 小型应用、MVP、团队 < 10 人 |

### 微服务架构（Microservices）

| 维度 | 说明 |
|------|------|
| 结构 | 功能拆分为独立部署的服务 |
| 优点 | 独立扩展、技术异构、故障隔离 |
| 缺点 | 分布式复杂性、运维开销、数据一致性 |
| 适用 | 中大型系统、多团队、高可用要求 |

### 事件驱动架构（Event-Driven）

| 维度 | 说明 |
|------|------|
| 结构 | 组件通过事件异步通信 |
| 优点 | 松耦合、高扩展性、天然审计 |
| 缺点 | 调试困难、最终一致性、事件风暴 |
| 适用 | 实时处理、事件溯源、CQRS |

### CQRS（Command Query Responsibility Segregation）

| 维度 | 说明 |
|------|------|
| 结构 | 读写分离，不同模型处理命令和查询 |
| 优点 | 查询性能优化、模型简化、扩展灵活 |
| 缺点 | 复杂度增加、最终一致性 |
| 适用 | 读多写少、查询模型复杂 |

### 六边形架构（Hexagonal / Ports & Adapters）

| 维度 | 说明 |
|------|------|
| 结构 | 核心业务逻辑在中心，外部通过端口/适配器接入 |
| 优点 | 可测试性、技术无关、易替换 |
| 缺点 | 学习曲线、小项目过度设计 |
| 适用 | 领域复杂、需要长期演进的系统 |

## 选型决策树

```
团队规模 < 10 人？
├── 是 → 单体（模块化）
└── 否 → 业务域是否清晰可拆分？
         ├── 否 → 模块化单体（先治理）
         └── 是 → 需要独立扩展/部署？
                  ├── 否 → 模块化单体
                  └── 是 → 微服务
                           ├── 事件密集 → 事件驱动 + 微服务
                           └── 读写差异大 → CQRS + 微服务
```

## 关键质量属性（-ilities）

| 属性 | 含义 | 架构影响 |
|------|------|----------|
| 可扩展性 | 负载增长时保持性能 | 水平扩展、无状态设计 |
| 可用性 | 系统正常运行时间 | 冗余、故障转移、熔断 |
| 可维护性 | 修改和修复的难易 | 模块化、文档、测试 |
| 可测试性 | 验证正确性的难易 | 依赖注入、接口隔离 |
| 可部署性 | 发布新版本的速度 | CI/CD、容器化、特性开关 |
| 安全性 | 抵御威胁的能力 | 纵深防御、零信任 |
| 性能 | 响应速度和资源效率 | 缓存、异步、CDN |

## CAP 定理

| 组合 | 说明 | 示例 |
|------|------|------|
| CP（一致性+分区容忍） | 网络分区时拒绝写入 | ZooKeeper, etcd |
| AP（可用性+分区容忍） | 网络分区时接受写入，可能不一致 | Cassandra, DynamoDB |
| CA（一致性+可用性） | 无分区时两者兼顾（理论上不存在） | 单机数据库 |

## 架构决策记录（ADR）

### 何时使用 ADR

- 影响 ≥2 个子系统
- 涉及技术选型
- 不可逆或高成本回滚
- 团队对齐需要

### ADR 结构

```markdown
# ADR-XXX: [决策标题]

## 状态
Proposed / Accepted / Superseded

## 背景
为什么需要做这个决策？

## 决策
我们决定...

## 理由
为什么这样做？考虑了哪些替代方案？

## 后果
正面和负面影响
```

## 演进策略

### 单体 → 微服务迁移路径

```
1. 模块化单体（先拆分代码，不拆部署）
   ↓
2. 识别边界上下文（DDD）
   ↓
3. 提取第一个服务（通常是无状态、低耦合的）
   ↓
4. 逐步提取，每次一个
   ↓
5. 单体退役
```

### 反模式警示

| 反模式 | 表现 | 后果 |
|--------|------|------|
| 分布式单体 | 服务间紧耦合，必须同时部署 | 微服务的复杂性 + 单体的痛点 |
| 纳米服务 | 服务拆得过细 | 运维爆炸、网络开销 |
| 数据孤岛 | 每个服务有自己的数据库但互相直接查询 | 一致性灾难 |
| 事件地狱 | 事件链过长无法追踪 | 调试不可能 |

## 参考框架

- Fowler, M. "Patterns of Enterprise Application Architecture"
- Newman, S. "Building Microservices"
- R. C. Martin "Clean Architecture"
- Kleppmann, M. "Designing Data-Intensive Applications"
- Microsoft "Architecture Guide for .NET"
