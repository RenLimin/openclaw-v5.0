---
id: saas-iam-sso-saml-oidc
title: 企业 SSO 集成 SOP（SAML / OIDC）
category: business/saas-development/05-identity-access
dimension: saas-development
sub_area: identity-access
type: knowledge
tags: [identity, SSO, SAML, OIDC, authentication]
version: 1.0.0
status: active
created: 2026-09-06
updated: 2026-09-06
revision: 1
author: Jerry
confidentiality: internal
source: "SAML 2.0 Specification; OIDC Core 1.0; OAuth 2.0 RFC 6749; Okta IAM Architecture"
last_reviewed: 2026-09-06
---

# 企业 SSO 集成 SOP（SAML / OIDC）

## 适用场景

- SaaS 产品的企业级单点登录集成
- SAML 2.0 / OIDC 协议对接企业身份提供商（IdP）
- 客户 IT 团队自助配置 SSO 的流程
- SSO 上线后的运维与故障排查

---

## 核心原则

1. **协议标准化** — 用标准协议（SAML/OIDC），不搞自定义登录
2. **客户自助优先** — 配置流程让客户 IT 自己能搞定，减少实施成本
3. **安全默认** — 开启 SSO 后默认禁用密码登录，防止绕过
4. **优雅降级** — IdP 挂了的时候，有应急登录方案
5. **完整审计** — 所有登录行为（成功/失败）都有日志

---

## SSO 基础知识

### 什么是 SSO

单点登录（Single Sign-On）：用户在企业身份系统登录一次，就能访问所有接入的应用，不需要每个应用都输密码。

### 核心角色

| 角色 | 简称 | 说明 |
|---|---|---|
| **服务提供商** | SP（Service Provider） | 我们的 SaaS 产品 |
| **身份提供商** | IdP（Identity Provider） | 企业的身份系统，如 Okta、Azure AD |
| **用户** | User | 企业员工 / 最终用户 |

### 主流协议对比

| 维度 | SAML 2.0 | OIDC |
|---|---|---|
| **类型** | XML 基于 | JSON / OAuth 2.0 基于 |
| **年代** | 2005 年（老而弥坚） | 2014 年（现代协议） |
| **主要场景** | 企业内部应用 Web SSO | 移动 / Web / API，更现代 |
| **复杂度** | 高（XML 签名繁琐） | 中（JSON Web Token） |
| **企业支持度** | 高（几乎所有企业 IdP 都支持） | 越来越高 |
| **Logout** | 支持 SLO（单点登出） | 支持（RP-Initiated） |
| **适用规模** | 中大型企业 | 所有规模 |

**选型建议：**
- 企业版功能，SAML 是标配（客户 expect 有）
- OIDC 适合更现代的场景和移动端
- 两个都支持是最佳实践

---

## SAML 2.0 集成

### SAML 登录流程

```
1. 用户访问我们的产品
2. 跳转到企业 IdP 登录页
3. 用户在 IdP 完成认证
4. IdP 生成 SAML Response（XML，带签名）
5. 浏览器 POST 到我们的 ACS URL
6. 我们验证签名和声明
7. 建立登录会话，用户登录成功
```

### SP 端需要提供的信息

客户配置 IdP 时需要从我们这里拿到：

| 信息 | 说明 | 示例 |
|---|---|---|
| **ACS URL** | 断言消费服务 URL | `https://app.example.com/sso/saml/acs` |
| **SP Entity ID** | SP 的唯一标识 | `https://app.example.com/sso/saml/metadata` |
| **Single Logout URL** | 单点登出 URL | `https://app.example.com/sso/saml/slo` |
| **SP 元数据 XML** | 包含以上所有信息的 XML | 可下载的 XML 文件 |

### IdP 端需要提供的信息

客户配置完成后，需要提供给我们：

| 信息 | 说明 |
|---|---|
| **IdP Entity ID** | IdP 的唯一标识 |
| **IdP SSO URL** | 登录跳转地址 |
| **IdP SLO URL** | 登出地址（可选） |
| **IdP 证书** | 用于验证 SAML 签名的公钥证书 |
| **IdP 元数据 XML** | 包含以上信息的 XML（推荐） |

### 声明映射（Attribute Mapping）

SAML Assertion 中携带的用户信息，需要和我们系统的字段映射：

| SAML 声明 | 我们的字段 | 必填 | 说明 |
|---|---|---|---|
| NameID | email / username | 是 | 用户唯一标识，建议用邮箱 |
| email | email | 是 | 邮箱地址 |
| firstName / givenName | first_name | 否 | 名 |
| lastName / surname | last_name | 否 | 姓 |
| displayName | name | 否 | 显示名称 |
| department | department | 否 | 部门 |
| groups | roles / groups | 否 | 用户组，用于权限映射 |

---

## OIDC 集成

### OIDC 登录流程（Authorization Code Flow）

```
1. 用户访问我们的产品
2. 重定向到 IdP 的 /authorize 端点
3. 用户在 IdP 登录并授权
4. IdP 重定向回我们的 redirect_uri，带 code
5. 我们用 code 向 IdP /token 端点换 token
6. 验证 id_token，获取用户信息
7. 建立登录会话
```

### 需要的配置信息

| 信息 | 说明 |
|---|---|
| **Client ID** | 客户端标识 |
| **Client Secret** | 客户端密钥 |
| **Issuer URL** | IdP 发行者 URL（如 `https://accounts.google.com`） |
| **Authorization Endpoint** | 授权端点 |
| **Token Endpoint** | Token 端点 |
| **UserInfo Endpoint** | 用户信息端点 |
| **JWKS URL** | 公钥 URL（用于验证 JWT 签名） |

> 大多数 OIDC IdP 支持 Discovery Endpoint（`/.well-known/openid-configuration`），可以自动发现以上所有端点。

### Scope 与 Claims

| Scope | 返回的 Claims | 说明 |
|---|---|---|
| openid | sub | 必填，用户唯一标识 |
| email | email, email_verified | 邮箱 |
| profile | name, given_name, family_name, picture | 基本资料 |
| groups | groups | 用户组（部分 IdP 支持） |

---

## 客户配置流程

### 自助配置流程（企业版标配）

```
1. 管理员进入「设置 - 身份验证 - SSO」
2. 选择协议（SAML / OIDC）
3. 下载 SP 元数据 / 复制 SP 配置信息
4. 到企业 IdP 中配置应用，获取 IdP 配置
5. 回到我们的产品，填入 IdP 配置
6. 配置属性映射
7. 测试连接（用测试账号登录）
8. 测试通过，启用 SSO
```

### 配置检查清单

- [ ] SP Entity ID / ACS URL 正确配置
- [ ] IdP 证书 / Client Secret 正确上传
- [ ] NameID / sub 映射正确（建议用邮箱）
- [ ] 必要的用户属性（邮箱、姓名）已映射
- [ ] 角色 / 部门映射（如果需要）已配置
- [ ] 测试账号 SSO 登录成功
- [ ] 登出功能正常
- [ ] 应急登录方案已确认

---

## 安全要点

### 必须启用的安全措施

1. **签名验证** — SAML Response 必须验证签名，防止篡改
2. **HTTPS** — 所有 SSO 相关 URL 必须是 HTTPS
3. **防止重放攻击** — SAML Assertion 有过期时间 + one-time use
4. **状态参数** — OIDC 用 state 参数防 CSRF
5. **PKCE** — 移动端 OIDC 用 PKCE（Proof Key for Code Exchange）
6. **加密可选** — 敏感场景下 SAML Assertion 可以加密

### 开启 SSO 后的登录策略

| 策略 | 说明 | 适用场景 |
|---|---|---|
| **混合登录** | SSO 和密码登录都可以 | 过渡期，部分用户还没迁到 SSO |
| **强制 SSO** | 只能通过 SSO 登录，禁用密码 | 安全要求高的企业，推荐 |
| **白名单** | 特定账号（如超级管理员）可以密码登录，其他必须 SSO | 兼顾安全和应急 |

**推荐：** 强制 SSO + 超级管理员白名单应急

### SCIM 自动用户管理

SSO 只管登录，SCIM（System for Cross-domain Identity Management）管用户生命周期：
- 用户入职 → 自动创建账号
- 用户调岗 → 自动更新角色
- 用户离职 → 自动停用账号

配合使用体验最好。

---

## 故障排查

### 常见问题与定位

| 问题 | 可能原因 | 排查方法 |
|---|---|---|
| **登录后跳回来还是未登录** | SAML 验证失败 / 用户不存在 | 查看 SAML 响应，检查签名和属性 |
| **提示找不到用户** | NameID 映射不对，或者用户没创建 | 检查 NameID 格式和值 |
| **无限重定向循环** | 会话没建成功，又跳去 IdP | 检查 Cookie 设置、域名、HTTPS |
| **签名验证失败** | 证书不对 / Response 被篡改 | 确认 IdP 证书是否正确、是否过期 |
| **登出后又自动登录了** | IdP 会话还在，免登又回来了 | 实现 SLO 单点登出 |

### 调试工具

- SAML：SAML Tracer（浏览器插件），抓 SAML Request/Response
- OIDC：浏览器开发者工具，看 Network 请求
- JWT 调试：jwt.io 解码 token
- 日志：详细的 SSO 日志，记录每个步骤和错误

---

## 主流 IdP 对接要点

| IdP | 市场份额 | SAML | OIDC | SCIM | 对接难度 |
|---|---|---|---|---|---|
| **Okta** | 高 | ✅ | ✅ | ✅ | 低 |
| **Azure AD** | 高 | ✅ | ✅ | ✅ | 低 |
| **Ping Identity** | 中 | ✅ | ✅ | ✅ | 中 |
| **OneLogin** | 中 | ✅ | ✅ | ✅ | 低 |
| **Google Workspace** | 中 | ✅ | ✅ | ✅ | 低 |
| **AD FS** | 中（传统企业） | ✅ | ❌ | ❌ | 高 |
| **钉钉 / 企业微信** | 国内高 | 部分 | ✅ | 部分 | 中 |

---

## 常见陷阱

| 陷阱 | 表现 | 规避方法 |
|---|---|---|
| 每个客户都要定制 | 每个客户 SSO 对接都要研发改代码 | 做通用配置化 SSO，客户自助配置 |
| 只支持 SAML | 现代客户要 OIDC 就傻眼了 | 两个协议都支持，OIDC 优先 |
| 没有应急方案 | 客户 IdP 挂了，全公司登不上我们系统 | 预留超级管理员密码登录 / 应急登录码 |
| 映射太复杂 | 属性映射搞成可视化拖拽，客户不会用 | 提供默认映射，高级配置藏起来 |
| 日志不够 | 出了问题不知道哪错了 | 详细的 SSO 日志，客户管理员能看 |
| 安全没做到位 | SAML 不验签名 / 没防重放 | 严格按照安全规范实现，第三方安全审计 |
| 不支持 SCIM | 用户入职离职还要手动建号删号 | SSO + SCIM 一起做，完整的用户生命周期管理 |

---

## 关联 SOP

- SCIM 用户同步 → `saas-iam-scim-provisioning.md`
- RBAC / ABAC 权限模型 → `saas-iam-rbac-abac.md`
- 审计日志 → `saas-iam-audit-logging.md`
- 安全合规 → `../09-security-compliance/`
