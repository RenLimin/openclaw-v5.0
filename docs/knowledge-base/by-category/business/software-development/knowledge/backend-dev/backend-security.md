---
title: 后端安全
description: 认证授权、威胁防护与安全最佳实践
source: OWASP Top 10; NIST; JWT RFC 7519
version: 1.0
category: business
dimension: software-development
sub_area: security
type: knowledge
tags: [security, jwt, oauth2, rbac, owasp, authentication]
xref: [software-development/knowledge/backend-dev/backend-testing.md]
last_reviewed: 2026-08-27
---

# 后端安全

## OWASP Top 10（2021）

| 排名 | 威胁 | 防护措施 |
|------|------|----------|
| A01 | 访问控制失效 | RBAC/ABAC、最小权限、鉴权中间件 |
| A02 | 加密失败 | TLS 1.3、敏感数据加密存储、密钥轮换 |
| A03 | 注入（SQL/NoSQL/命令） | 参数化查询、ORM、输入校验 |
| A04 | 不安全设计 | 威胁建模、安全设计评审 |
| A05 | 安全配置错误 | 默认安全、最小暴露、定期扫描 |
| A06 | 脆弱组件 | 依赖扫描（Snyk/Dependabot）、及时升级 |
| A07 | 认证失败 | MFA、密码策略、账户锁定 |
| A08 | 数据完整性失败 | 签名验证、依赖锁定、CI 校验 |
| A09 | 日志不足 | 审计日志、异常告警、不可篡改 |
| A10 | SSRF | URL 白名单、网络隔离 |

## 认证与授权

### JWT（JSON Web Token）

| 部分 | 说明 |
|------|------|
| Header | 算法声明（HS256/RS256） |
| Payload | 声明（sub、exp、iat、roles） |
| Signature | 签名验证完整性 |

**最佳实践**：
- 使用 RS256（非对称）而非 HS256（对称）
- 设置合理过期时间（access token 15min，refresh token 7d）
- 不在 Payload 放敏感信息（仅 Base64 编码，非加密）
- Refresh Token 存 httpOnly Cookie

### OAuth 2.0 + OpenID Connect

| 角色 | 说明 |
|------|------|
| Resource Owner | 用户 |
| Client | 应用 |
| Authorization Server | 认证服务（颁发 Token） |
| Resource Server | API 服务（验证 Token） |

| Grant Type | 适用场景 |
|------------|----------|
| Authorization Code + PKCE | 第三方登录、SPA |
| Client Credentials | 服务间通信 |
| Device Code | 无浏览器设备 |

### RBAC vs ABAC

| 模型 | 说明 | 适用 |
|------|------|------|
| RBAC | 基于角色（Admin/Editor/Viewer） | 角色固定的系统 |
| ABAC | 基于属性（部门+级别+时间） | 复杂权限场景 |
| ReBAC | 基于关系（Owner/Member） | 社交/协作系统 |

## 常见攻击防护

| 攻击 | 防护 |
|------|------|
| SQL 注入 | 参数化查询、ORM、输入白名单 |
| XSS | 输出转义、CSP、httpOnly Cookie |
| CSRF | SameSite Cookie、CSRF Token、Origin 校验 |
| 暴力破解 | 速率限制、账户锁定、CAPTCHA |
| 重放攻击 | Nonce、时间戳、请求签名 |
| 中间人 | TLS 1.3、HSTS、证书固定 |

## 安全 Headers

| Header | 作用 |
|--------|------|
| `Content-Security-Policy` | 限制资源加载来源 |
| `Strict-Transport-Security` | 强制 HTTPS |
| `X-Content-Type-Options` | 禁止 MIME 嗅探 |
| `X-Frame-Options` | 防止点击劫持 |
| `Referrer-Policy` | 控制 Referer 泄露 |
