---
title: 后端测试
description: 单元测试、集成测试、E2E 测试与契约测试
source: Martin Fowler "Test Pyramid"; "Testing Microservices"
version: 1.0
category: business
dimension: software-development
sub_area: testing
type: knowledge
tags: [testing, unit-test, integration-test, e2e, contract-test]
xref: [software-development/knowledge/backend-dev/backend-security.md]
last_reviewed: 2026-08-27
---

# 后端测试

## 测试金字塔

```
        /  E2E  \        ← 少量（关键业务流程）
       / Integration \    ← 适量（模块间协作）
      /  Unit 测试     \  ← 大量（函数、类、逻辑）
```

| 层级 | 范围 | 速度 | 成本 | 覆盖率目标 |
|------|------|------|------|-----------|
| 单元测试 | 单个函数/类 | 极快 | 低 | 70-80% |
| 集成测试 | 模块间协作 | 快 | 中 | 15-20% |
| E2E 测试 | 完整业务流程 | 慢 | 高 | 5-10% |

## 单元测试

### 原则（FIRST）

| 原则 | 说明 |
|------|------|
| Fast | 快速执行（毫秒级） |
| Isolated | 独立运行，不依赖外部 |
| Repeatable | 任何环境结果一致 |
| Self-Validating | 自动断言，无需人工检查 |
| Timely | 与业务代码同步编写 |

### Mock 策略

| 类型 | 工具 | 用途 |
|------|------|------|
| Stub | 返回固定值 | 模拟外部服务响应 |
| Mock | 验证调用行为 | 验证方法是否被调用 |
| Spy | 部分真实 + 部分模拟 | 保留核心逻辑，模拟边界 |
| Fake | 内存实现 | 内存数据库替代真实 DB |

## 集成测试

| 类型 | 测试内容 | 工具 |
|------|----------|------|
| 数据库集成 | Repository 层 + 真实/内存 DB | Testcontainers、H2 |
| API 集成 | Controller 层 + HTTP 请求 | Supertest、REST Assured |
| 消息队列集成 | 生产者 + 消费者 | Testcontainers Kafka |

### 测试数据库策略

| 策略 | 优点 | 缺点 |
|------|------|------|
| Testcontainers（真实 DB） | 最接近生产 | 慢，需 Docker |
| 内存 DB（H2/SQLite） | 极快 | 与生产 DB 有差异 |
| 迁移回滚 | 每次测试后回滚 | 需要迁移脚本 |

## E2E 测试

| 工具 | 语言 | 特点 |
|------|------|------|
| Playwright | JS/Python/Java | 多浏览器、自动等待、Trace |
| Cypress | JS | 实时重载、时间旅行 |
| Postman/Newman | 无代码 | API 流程测试 |

### E2E 最佳实践

1. 只覆盖**关键业务流程**（登录→下单→支付）
2. 使用**测试数据工厂**，不依赖固定数据
3. 测试间**数据隔离**，避免互相影响
4. 设置合理的**超时和重试**

## 契约测试

### 消费者驱动契约（CDC）

```
消费者（前端）定义期望 → 生成契约 → 提供者（后端）验证
```

| 工具 | 说明 |
|------|------|
| Pact | 消费者驱动契约测试框架 |
| Spring Cloud Contract | Spring 生态契约测试 |

### 契约测试价值

- 前后端并行开发，不互相阻塞
- 接口变更自动检测
- 替代部分 E2E 测试（更快、更稳定）

## 测试覆盖率

| 指标 | 目标 | 说明 |
|------|------|------|
| 行覆盖率 | > 80% | 基础门槛 |
| 分支覆盖率 | > 70% | 条件覆盖 |
| 关键路径覆盖率 | 100% | 核心业务逻辑 |

**注意**：覆盖率是必要条件，不是充分条件。关注测试质量而非数字。
