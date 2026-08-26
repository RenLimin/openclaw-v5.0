---
title: API 设计
description: RESTful API、GraphQL、gRPC 设计原则与最佳实践
source: Richardson "RESTful Web APIs"; Google API Design Guide; OpenAPI Specification
version: 1.0
category: business
dimension: software-development
sub_area: system-architecture
type: knowledge
tags: [API, REST, GraphQL, gRPC, OpenAPI]
xref: [software-development/knowledge/system-architecture/microservices.md]
last_reviewed: 2026-08-26
---

# API 设计

## API 风格对比

### REST

| 维度 | 说明 |
|------|------|
| 协议 | HTTP/1.1 或 HTTP/2 |
| 数据格式 | JSON（主流）/ XML |
| 风格 | 资源导向，URL 表示资源，HTTP 动作为操作 |
| 优点 | 简单、通用、缓存友好 |
| 缺点 | 过度获取/获取不足、多次请求 |
| 适用 | 通用 CRUD、公开 API |

### GraphQL

| 维度 | 说明 |
|------|------|
| 协议 | HTTP（POST 为主） |
| 数据格式 | JSON |
| 风格 | 查询语言，客户端指定需要的数据 |
| 优点 | 精确获取、单一端点、强类型 schema |
| 缺点 | 缓存复杂、查询性能风险、学习曲线 |
| 适用 | 复杂数据关系、移动端、BFF 层 |

### gRPC

| 维度 | 说明 |
|------|------|
| 协议 | HTTP/2 |
| 数据格式 | Protocol Buffers（二进制） |
| 风格 | 服务定义（.proto），生成客户端/服务端代码 |
| 优点 | 高性能、强类型、双向流 |
| 缺点 | 浏览器支持有限、调试困难 |
| 适用 | 服务间通信、低延迟场景 |

## RESTful API 设计规范

### URL 设计

```
✅ GET    /api/v1/users          # 获取用户列表
✅ GET    /api/v1/users/123      # 获取单个用户
✅ POST   /api/v1/users          # 创建用户
✅ PUT    /api/v1/users/123      # 全量更新
✅ PATCH  /api/v1/users/123      # 部分更新
✅ DELETE /api/v1/users/123      # 删除用户

❌ GET    /api/v1/getUser        # 动词不应出现在 URL
❌ GET    /api/v1/users/list     # list 冗余
❌ POST   /api/v1/createUser     # 用 HTTP 动作表达操作
```

### 命名规则

| 规则 | 正确 | 错误 |
|------|------|------|
| 复数名词 | `/orders` | `/order` |
| 小写 + 连缀 | `/order-items` | `/orderItems` |
| 无尾斜杠 | `/users` | `/users/` |
| 版本前缀 | `/api/v1/users` | `/users`（无版本） |

### HTTP 状态码

| 类别 | 码 | 含义 |
|------|-----|------|
| 成功 | 200 | OK（查询/更新） |
| 成功 | 201 | Created（创建） |
| 成功 | 204 | No Content（删除） |
| 客户端错误 | 400 | Bad Request（参数错误） |
| 客户端错误 | 401 | Unauthorized（未认证） |
| 客户端错误 | 403 | Forbidden（无权限） |
| 客户端错误 | 404 | Not Found |
| 客户端错误 | 409 | Conflict（资源冲突） |
| 客户端错误 | 422 | Unprocessable Entity（业务校验失败） |
| 服务端错误 | 500 | Internal Server Error |
| 服务端错误 | 503 | Service Unavailable |

### 分页

```
GET /api/v1/users?page=1&page_size=20

Response:
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

### 过滤/排序/搜索

```
GET /api/v1/users?status=active&role=admin
GET /api/v1/users?sort=-created_at,+name
GET /api/v1/users?q=zhang
```

## 错误响应格式

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数校验失败",
    "details": [
      {
        "field": "email",
        "message": "邮箱格式不正确"
      },
      {
        "field": "age",
        "message": "年龄必须在 1-120 之间"
      }
    ],
    "request_id": "req_abc123",
    "documentation_url": "https://api.example.com/docs/errors/VALIDATION_ERROR"
  }
}
```

## 安全设计

### 认证

| 方式 | 适用 | 说明 |
|------|------|------|
| JWT | 无状态服务 | Bearer token，含过期时间 |
| Session | 传统 Web | 服务端存储 session |
| OAuth 2.0 | 第三方授权 | 授权码模式最安全 |
| API Key | 服务间通信 | 简单但需配合 TLS |

### 防护措施

| 措施 | 说明 |
|------|------|
| HTTPS 强制 | 所有 API 必须 TLS |
| 速率限制 | 防止滥用（如 100 req/min/IP） |
| CORS 配置 | 严格限制来源域 |
| 输入校验 | 白名单校验，防注入 |
| 敏感数据脱敏 | 日志中不记录密码/Token |

## 版本管理策略

| 策略 | 示例 | 优点 | 缺点 |
|------|------|------|------|
| URL 版本 | `/api/v1/users` | 直观、缓存友好 | URL 变化 |
| Header 版本 | `Accept: application/vnd.api.v2+json` | URL 不变 | 不直观 |
| 参数版本 | `/api/users?version=2` | 简单 | 不规范 |

**推荐**：URL 版本（v1/v2），最直观且工具支持最好。

## API 文档

### OpenAPI（Swagger）

```yaml
openapi: 3.0.0
info:
  title: User API
  version: 1.0.0
paths:
  /api/v1/users:
    get:
      summary: 获取用户列表
      parameters:
        - name: page
          in: query
          schema:
            type: integer
            default: 1
      responses:
        '200':
          description: 成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UserList'
```

### 文档工具

| 工具 | 用途 |
|------|------|
| Swagger UI | 交互式 API 文档 |
| Redoc | 美观的静态文档 |
| Postman | API 测试 + 文档 |
| Stoplight | 可视化 API 设计 |

## 常见误区

1. **忽视版本管理**：上线后无法兼容变更
2. **过度暴露**：返回全部字段，浪费带宽
3. **缺乏错误处理**：只返回 500，不区分错误类型
4. **无速率限制**：被刷爆才发现
5. **忽视幂等性**：POST 重复调用产生重复数据

## 参考框架

- Richardson, L. "RESTful Web APIs"
- Google API Design Guide (cloud.google.com/apis/design)
- OpenAPI Specification v3.1
- Zalando RESTful API Guidelines
