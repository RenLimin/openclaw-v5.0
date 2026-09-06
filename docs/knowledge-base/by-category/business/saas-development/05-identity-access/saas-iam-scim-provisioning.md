---
id: saas-iam-scim-provisioning
title: SCIM 用户自动配置 SOP
category: business/saas-development/05-identity-access
dimension: saas-development
sub_area: identity-access
type: knowledge
tags: [identity, SCIM, provisioning, user-management]
version: 1.0.0
status: active
created: 2026-09-06
updated: 2026-09-06
revision: 1
author: Jerry
confidentiality: internal
source: "SCIM 2.0 RFC 7642/7643/7644; Okta SCIM Implementation; Azure AD Provisioning"
last_reviewed: 2026-09-06
---

# SCIM 用户自动配置 SOP

## 适用场景

- SaaS 产品 SCIM 2.0 接口实现
- 企业客户用户生命周期自动化管理（入职 / 调岗 / 离职）
- 与 Okta / Azure AD / OneLogin 等 IdP 的 SCIM 对接
- 大批量用户的自动化同步

---

## 核心原则

1. **IdP 是权威源** — 用户信息以 IdP 为准，我们这边是副本，单向同步
2. **幂等操作** — 同样的请求执行多次结果一样，不会重复创建
3. **增量优先** — 优先支持增量同步，全量同步只在初始化时用
4. **可观测** — 每次同步操作有日志、有状态、可追溯
5. **容错设计** — IdP 发来的奇怪数据不要崩，优雅处理

---

## 什么是 SCIM

SCIM（System for Cross-domain Identity Management）是一个开放标准，用于在不同系统之间自动化用户生命周期管理。

简单说：SSO 解决"怎么登录"，SCIM 解决"账号怎么建、怎么改、怎么删"。

### SCIM 解决的问题

**没有 SCIM 时：**
- 客户 IT 手动给每个员工创建账号
- 员工离职了，忘了禁用账号 → 安全风险
- 部门调岗，权限还要手动改 → 效率低
- 大客户有几千人，手动创建根本不现实

**有了 SCIM 后：**
- 员工入职 → IdP 加人 → 自动在我们系统建号
- 员工调岗 → IdP 改部门/组 → 自动更新权限
- 员工离职 → IdP 删人 → 自动禁用账号
- 全程自动化，零人工操作

---

## SCIM 2.0 协议概览

### 核心资源

| 资源 | 端点 | 说明 |
|---|---|---|
| **User** | `/scim/v2/Users` | 用户 |
| **Group** | `/scim/v2/Groups` | 用户组 |
| **ServiceProviderConfig** | `/scim/v2/ServiceProviderConfig` | 服务提供者配置 |
| **ResourceTypes** | `/scim/v2/ResourceTypes` | 支持的资源类型 |
| **Schemas** | `/scim/v2/Schemas` | Schema 定义 |

### 标准操作（CRUD）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| **Create** | POST | `/Users` | 创建用户 |
| **Read** | GET | `/Users/{id}` | 获取用户详情 |
| **List** | GET | `/Users` + 过滤 | 查询用户列表 |
| **Update** | PUT | `/Users/{id}` | 全量更新 |
| **Patch** | PATCH | `/Users/{id}` | 部分更新 |
| **Delete** | DELETE | `/Users/{id}` | 删除用户 |

### 用户字段映射

| SCIM 字段 | 我们的字段 | 说明 |
|---|---|---|
| userName | username / email | 用户名（通常是邮箱） |
| name.givenName | first_name | 名 |
| name.familyName | last_name | 姓 |
| displayName | display_name | 显示名称 |
| emails[primary] | email | 主邮箱 |
| active | status | 是否激活 |
| externalId | external_id | IdP 侧的用户 ID |
| locale | locale | 语言 |
| timezone | timezone | 时区 |
| groups | groups / roles | 用户组 / 角色 |
| phoneNumbers | phone | 电话 |

---

## SCIM 实现要点

### 必须支持的功能（最小可用集）

1. ✅ 用户创建（POST /Users）
2. ✅ 用户查询（GET /Users + 过滤）
3. ✅ 用户更新（PUT / PATCH）
4. ✅ 用户删除 / 停用（DELETE / active=false）
5. ✅ 组查询（GET /Groups）
6. ✅ ServiceProviderConfig 和 Schemas 元数据

### 推荐支持的功能

1. ✅ 用户组成员管理（PATCH Group）
2. ✅ 分页（startIndex + count）
3. ✅ 过滤（filter 参数）
4. ✅ 批量操作（Bulk）
5. ✅ 企业用户 Schema 扩展（urn:ietf:params:scim:schemas:extension:enterprise:2.0:User）

### 认证方式

SCIM 接口必须认证，推荐方式：

| 方式 | 安全性 | 实现难度 | 说明 |
|---|---|---|---|
| **OAuth 2.0 Bearer Token** | 高 | 中 | 最标准，推荐 |
| **API Key（Header）** | 中 | 低 | 简单，但不如 OAuth 安全 |
| **HTTP Basic Auth** | 低 | 低 | 不推荐，除非客户要求 |

**推荐：** 生成一个长期有效的 Bearer Token，客户在 IdP 里配置。每个租户一个独立的 token。

---

## 客户配置流程

### 前提条件

- 客户已配置 SSO（SCIM 通常和 SSO 一起用）
- 客户企业版套餐（SCIM 是企业版功能）
- 客户 IT 管理员有 IdP 配置权限

### 配置步骤

```
1. 管理员进入「设置 - 身份验证 - SCIM 配置」
2. 启用 SCIM
3. 生成 SCIM Base URL 和 Token
4. 将这些信息填入客户 IdP 的 SCIM 配置中
5. 配置属性映射（如果有自定义字段）
6. 测试连接
7. 配置同步规则（哪些用户/组需要同步）
8. 启动同步
9. 检查首次同步结果
```

### 属性映射配置

客户可以自定义 SCIM 字段到我们系统字段的映射：
- 默认映射（标准字段自动匹配）
- 自定义字段映射（客户扩展字段）
- 表达式映射（简单的转换逻辑）

---

## 用户生命周期同步

### 事件触发矩阵

| IdP 操作 | 我们系统动作 | 说明 |
|---|---|---|
| **创建用户** | 创建账号 + 发送欢迎邮件 | 初始密码？不需要，因为有 SSO |
| **更新用户信息** | 更新用户资料 | 姓名、邮箱、部门等 |
| **禁用用户（active=false）** | 禁用账号，踢掉现有登录会话 | 用户离职 / 休假 |
| **启用用户（active=true）** | 重新启用账号 | 休假回来 / 误操作恢复 |
| **删除用户** | 禁用 / 删除账号 | 取决于策略，推荐禁用而非删除 |
| **加入组** | 增加角色 / 权限 | 组和角色映射 |
| **离开组** | 移除角色 / 权限 | - |

### 组与角色映射

**映射方式：**

| 方式 | 说明 | 适用场景 |
|---|---|---|
| **一对一映射** | 一个 IdP 组对应我们的一个角色 | 简单场景 |
| **多对多映射** | 多个组组合成一套权限 | 复杂权限体系 |
| **继承映射** | 父组成员自动拥有子组权限 | 层级组织架构 |

**配置方法：** 管理员在后台设置「IdP 组名 → 系统角色」的映射关系

---

## 同步监控与日志

### 同步状态看板

客户管理员可以看到：
- 上次同步时间
- 同步用户数 / 组数
- 成功数 / 失败数
- 最近的同步错误
- 同步历史记录

### 日志内容

每次 SCIM 操作记录：
- 操作类型（create / update / delete）
- 操作用户（SCIM 中的 userName）
- 操作时间
- 操作结果（成功 / 失败）
- 失败原因（如果失败）
- 请求 / 响应体（调试用，脱敏）

### 告警

- 连续失败超过阈值（如 10 次）→ 通知管理员
- 同步异常中断 → 通知管理员
- 长时间不同步（如 24 小时没同步了）→ 提醒检查

---

## 常见问题处理

### Q1：用户创建了但登录不了？

**排查：**
1. 确认 SSO 的 NameID 和 SCIM 的 userName 是否一致
2. 确认用户的 active 状态是否为 true
3. 检查用户是否在正确的组里

### Q2：删除操作是真删还是禁用？

**建议：默认禁用，不硬删除。**

原因：
- 删了数据就没了，可能误删
- 用户可能过几天又回来（调岗回来）
- 审计需要保留用户记录
- IdP 的 delete 有时候是误操作

可以设置：禁用 30 天后自动删除（或归档）。

### Q3：SCIM 和手动创建的用户冲突吗？

**处理策略：**
- 通过 externalId 匹配，有就更新，没有就创建
- 邮箱唯一，邮箱已存在的话关联起来
- SCIM 管理的用户标记来源 = SCIM，不允许手动改密码等

### Q4：大批量同步（几千用户）性能问题？

**优化：**
- 支持 Bulk 操作（批量创建/更新）
- 异步处理，不阻塞请求
- 限流保护，防止打挂系统
- 增量同步优先，全量同步少用

---

## 合规与安全

### 数据保护

- SCIM 传输的数据包含员工个人信息（姓名、邮箱、电话等）
- 必须 HTTPS 传输
- Token 加密存储
- 操作日志完整审计

### 合规要求

- SCIM 是 SOC 2 / ISO 27001 审计中的常见项
- 客户数据保护法规（GDPR 等）要求用户数据可删除
- SCIM 的删除 / 禁用能力是合规必需的

---

## 常见陷阱

| 陷阱 | 表现 | 规避方法 |
|---|---|---|
| 删用户直接硬删 | 误删了数据找不回来 | 默认禁用，保留一段时间再删 |
| 过滤支持不全 | Okta 发的 filter 查询不支持，同步失败 | 至少支持常用的 filter（userName eq, email eq, active eq） |
| 幂等性没做好 | 网络重试导致创建重复用户 | 用 externalId 做幂等键，已存在就更新 |
| 没有测试账号 | 客户配置完不知道对不对 | 提供测试连接功能，模拟一次同步 |
| 日志不友好 | 同步失败了客户不知道为啥 | 清晰的错误信息 + 同步日志面板 |
| 只支持用户不支持组 | 客户需要基于组的权限，做不了 | SCIM Groups + 角色映射一起做 |
| 安全没做好 | SCIM token 泄露了能操作所有用户 | token 权限最小化 + 可随时吊销 + IP 白名单可选 |

---

## 关联 SOP

- SSO 集成 → `saas-iam-sso-saml-oidc.md`
- RBAC / ABAC 权限模型 → `saas-iam-rbac-abac.md`
- 审计日志 → `saas-iam-audit-logging.md`
- 安全合规 → `../09-security-compliance/`
