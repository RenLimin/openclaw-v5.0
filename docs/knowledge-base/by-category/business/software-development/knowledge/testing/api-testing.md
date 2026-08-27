---
title: API 测试
description: API 功能测试、契约测试与 Mock 实践
source: Postman Docs; Pact Docs; "API Testing Foundations"
version: 1.0
category: business
dimension: software-development
sub_area: api-testing
type: knowledge
tags: [api-testing, postman, pact, contract-test, mock]
last_reviewed: 2026-08-27
---

# API 测试

## 功能测试

| 工具 | 用途 |
|------|------|
| Postman/Newman | 手动探索 + CI 自动化 |
| Supertest | Node.js HTTP 断言 |
| REST Assured | Java API 测试 |
| HTTPie + jq | 快速命令行验证 |

## 测试覆盖

| 维度 | 内容 |
|------|------|
| 状态码 | 200/201/400/401/403/404/422/429/500 |
| 响应体 | 结构、类型、字段完整性 |
| 边界值 | 空数组、超大输入、特殊字符 |
| 认证 | Token 过期、无权限、伪造 Token |
| 性能 | 响应时间、并发安全 |

## 契约测试（CDC）

消费者驱动契约：前端定义期望 → 生成契约 → 后端验证。

| 工具 | 说明 |
|------|------|
| Pact | 消费者驱动契约测试框架 |
| Spring Cloud Contract | Spring 生态 |

## Mock 策略

| 工具 | 用途 |
|------|------|
| MSW（Mock Service Worker） | 浏览器 + Node Mock |
| WireMock | Java HTTP Mock |
| json-server | 快速 REST API Mock |
