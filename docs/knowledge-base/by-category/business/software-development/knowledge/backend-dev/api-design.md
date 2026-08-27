---
title: API 设计
description: RESTful、GraphQL、gRPC 等 API 设计规范与最佳实践
source: Richardson "RESTful Web APIs"; GraphQL.org; Google API Design Guide
version: 1.0
category: business
dimension: software-development
sub_area: api-design
type: knowledge
tags: [api-design, rest, graphql, grpc, openapi]
xref: [software-development/knowledge/backend-dev/database-design.md]
last_reviewed: 2026-08-27
---

# API 设计

## RESTful API

### 核心原则

| 原则 | 说明 |
|------|------|
| 资源导向 | URL 表示资源（名词），不表示动作 |
| HTTP 语义 | GET 查询、POST 创建、PUT 全量更新、PATCH 部分更新、DELETE 删除 |
| 无状态 | 请求携带完整上下文，服务端不保存会话状态 |
| 统一接口 | 一致的响应格式、错误码、分页规范 |

### URL 设计规范

```
GET    /api/v1/users          # 列表
GET    /api/v1/users/{id}     # 详情
POST   /api/v1/users          # 创建
PUT    /api/v1/users/{id}     # 全量更新
PATCH  /api/v1/users/{id}     # 部分更新
DELETE /api/v1/users/{id}     # 删除
GET    /api/v1/users/{id}/orders  # 嵌套资源
```

### HTTP 状态码

| 码 | 含义 | 使用场景 |
|----|------|----------|
| 200 | OK | 查询/更新成功 |
| 201 | Created | 创建成功 |
| 204 | No Content | 删除成功 |
| 400 | Bad Request | 参数错误 |
| 401 | Unauthorized | 未认证 |
| 403 | Forbidden | 无权限 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 资源冲突（如重复创建） |
| 422 | Unprocessable Entity | 业务校验失败 |
| 429 | Too Many Requests | 限流 |
| 500 | Internal Server Error | 服务端错误 |

### 响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... },
  "meta": {
    "page": 1,
    "pageSize": 20,
    "total": 100
  }
}
```

### 版本管理

| 策略 | 示例 | 适用场景 |
|------|------|----------|
| URL 版本 | `/api/v1/`、`/api/v2/` | 推荐，直观 |
| Header 版本 | `Accept: application/vnd.api.v2+json` | 追求 URL 稳定 |
| 参数版本 | `?version=2` | 简单场景 |

## GraphQL

### 核心概念

| 概念 | 说明 |
|------|------|
| Schema | 类型定义，前后端契约 |
| Query | 查询（只读） |
| Mutation | 变更（写操作） |
| Subscription | 实时订阅（WebSocket） |
| Resolver | 字段级数据获取函数 |

### 与 REST 对比

| 维度 | REST | GraphQL |
|------|------|---------|
| 数据获取 | 固定字段，可能过度/不足获取 | 精确查询，按需获取 |
| 端点 | 多个 URL | 单一端点 |
| 版本 | URL/Header 版本 | Schema 演进（无版本） |
| 缓存 | HTTP 缓存友好 | 需额外配置 |
| 文件上传 | 原生支持 | 需额外方案 |

## gRPC

### 特点

- Protocol Buffers 序列化（二进制，比 JSON 快 5-10x）
- HTTP/2 多路复用
- 强类型契约（.proto 文件）
- 支持流式通信（客户端流、服务端流、双向流）

### 适用场景

| 场景 | 推荐 |
|------|------|
| 微服务间通信 | ✅ gRPC |
| 浏览器 ↔ 服务端 | ✅ REST / GraphQL |
| 实时通信 | ✅ gRPC 双向流 |
| 公开 API | ✅ REST |

## API 文档

| 工具 | 格式 | 特点 |
|------|------|------|
| OpenAPI 3.0（Swagger） | YAML/JSON | REST 标准，生态成熟 |
| GraphQL Schema | SDL | 自文档化 |
| AsyncAPI | YAML/JSON | 事件驱动 API 文档 |
| Postman Collection | JSON | 可执行文档 |
