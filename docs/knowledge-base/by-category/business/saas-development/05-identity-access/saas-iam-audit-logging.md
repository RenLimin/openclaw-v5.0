---
id: saas-iam-audit-logging
title: 身份与访问审计日志 SOP
category: business/saas-development/05-identity-access
dimension: saas-development
sub_area: identity-access
type: knowledge
tags: [identity, audit-log, compliance, security]
version: 1.0.0
status: active
created: 2026-09-06
updated: 2026-09-06
revision: 1
author: Jerry
confidentiality: internal
source: "SOC 2 CC7.2; ISO 27001 A.12.4; NIST SP 800-92 Log Management"
last_reviewed: 2026-09-06
---

# 身份与访问审计日志 SOP

## 适用场景

- SaaS 产品身份与访问相关的审计日志设计与实现
- 安全事件追溯与调查
- 合规审计（SOC 2、等保、ISO 27001）
- 客户管理员审计自己租户的操作

---

## 核心原则

1. **谁也不能删审计日志** — 审计日志是最后一道防线，只能追加，不能修改删除
2. **完整记录关键操作** — 所有认证、授权、权限变更都要有日志
3. **不可篡改** — 审计日志要有防篡改机制（至少是技术上的，最好是物理上的）
4. **可查询可导出** — 日志要能搜、能筛、能导出
5. **合规对齐** — 满足 SOC 2、等保、GDPR 等常见合规要求

---

## 审计事件分类

### 认证事件（Authentication）

| 事件 | 触发时机 | 重要级别 |
|---|---|---|
| login.success | 登录成功 | 中 |
| login.failure | 登录失败 | 高（多次失败可能是攻击） |
| login.mfa_challenge | MFA 验证 | 中 |
| login.mfa_success | MFA 验证通过 | 中 |
| login.sso | SSO 登录 | 中 |
| logout | 登出 | 低 |
| password_reset.request | 请求重置密码 | 中 |
| password_reset.success | 密码重置成功 | 中 |
| password_change | 修改密码 | 中 |
| account_lock | 账号锁定（多次失败） | 高 |

### 授权与权限事件（Authorization）

| 事件 | 触发时机 | 重要级别 |
|---|---|---|
| permission.denied | 权限不足（403） | 中（多次可能是探测） |
| role.grant | 授予角色 | 高 |
| role.revoke | 移除角色 | 高 |
| role.create | 创建角色 | 高 |
| role.update | 修改角色权限 | 高 |
| role.delete | 删除角色 | 高 |
| policy.change | 安全策略变更 | 高 |

### 用户管理事件

| 事件 | 触发时机 | 重要级别 |
|---|---|---|
| user.create | 创建用户 | 中 |
| user.invite | 邀请用户 | 中 |
| user.update | 更新用户信息 | 低 |
| user.deactivate | 禁用用户 | 高 |
| user.activate | 启用用户 | 中 |
| user.delete | 删除用户 | 高 |
| user.impersonate_start | 管理员模拟登录开始 | 高 |
| user.impersonate_end | 管理员模拟登录结束 | 高 |

### 配置变更事件

| 事件 | 触发时机 | 重要级别 |
|---|---|---|
| settings.change | 系统设置变更 | 中 |
| sso.enable | 启用 SSO | 高 |
| sso.disable | 禁用 SSO | 高 |
| sso.config_change | SSO 配置变更 | 高 |
| scim.enable | 启用 SCIM | 高 |
| api_key.create | 创建 API Key | 高 |
| api_key.revoke | 吊销 API Key | 高 |
| ip_whitelist.change | IP 白名单变更 | 高 |

### 数据访问事件（高敏感）

| 事件 | 触发时机 | 重要级别 |
|---|---|---|
| data.export | 导出数据 | 高 |
| data.bulk_delete | 批量删除数据 | 高 |
| data.view_sensitive | 查看敏感字段 | 中 |
| admin.data_access | 管理员访问租户数据 | 高 |

---

## 日志字段规范

### 通用字段（所有事件都有）

| 字段 | 类型 | 说明 | 必填 |
|---|---|---|---|
| id | string | 日志唯一 ID | ✅ |
| timestamp | datetime | 事件发生时间（UTC，毫秒级） | ✅ |
| tenant_id | string | 租户 ID | ✅ |
| user_id | string | 操作用户 ID（系统操作则为 system） | ✅ |
| user_email | string | 操作用户邮箱 | - |
| ip_address | string | 操作来源 IP | ✅ |
| user_agent | string | 浏览器 / 客户端 UA | - |
| event_type | string | 事件类型（如 login.success） | ✅ |
| event_category | string | 事件分类（auth / user / config 等） | ✅ |
| severity | string | 级别：low / medium / high / critical | ✅ |
| description | string | 人类可读的描述 | ✅ |
| request_id | string | 请求 ID，用于关联其他日志 | - |

### 事件特有字段

根据事件类型不同，携带不同的字段：

**登录成功示例：**
```json
{
  "event_type": "login.success",
  "method": "password",
  "login_location": "Beijing, CN",
  "device": "Chrome / Mac OS X"
}
```

**权限授予示例：**
```json
{
  "event_type": "role.grant",
  "target_user_id": "u_123",
  "target_user_email": "zhang@example.com",
  "role_id": "r_admin",
  "role_name": "管理员"
}
```

**导出数据示例：**
```json
{
  "event_type": "data.export",
  "data_type": "orders",
  "record_count": 1523,
  "file_size": 204800,
  "export_format": "xlsx"
}
```

---

## 日志存储与管理

### 存储要求

1. **只追加（Append-only）** — 只能写入新日志，不能修改和删除已有日志
2. **防篡改** — 日志有哈希校验，能检测是否被篡改
3. **独立存储** — 和业务数据库分开，不要放在同一个库
4. **冷热分层** — 近期日志热存储（可查询），历史日志冷存储（归档）

### 保留周期

| 日志类型 | 保留周期 | 存储层级 | 合规依据 |
|---|---|---|---|
| 认证日志 | 1 年 | 热 30 天 + 冷 1 年 | SOC 2 / 等保 |
| 权限变更日志 | 2 年 | 热 90 天 + 冷 2 年 | 等保三级 |
| 操作审计日志 | 1 年 | 热 30 天 + 冷 1 年 | SOC 2 |
| 安全事件日志 | 3 年 | 热 90 天 + 冷 3 年 | 事件追溯 |
| 管理员操作日志 | 2 年 | 热 90 天 + 冷 2 年 | 合规要求 |

**最低要求：** 6 个月在线查询 + 1 年归档（大多数合规的底线）

### 存储方案

| 方案 | 优点 | 缺点 |
|---|---|---|
| **Elasticsearch** | 查询强大，生态好 | 成本高，运维复杂 |
| **ClickHouse** | 查询快，成本低 | 日志分析场景适合 |
| **云日志服务** | 托管，省事 | 成本随量增长 |
| **数据库 + 归档** | 简单，成本低 | 查询能力弱 |

**推荐：** ClickHouse 或云日志服务，量大成本可控。

---

## 日志查询与告警

### 查询能力

客户管理员可以查自己租户的审计日志：
- 按事件类型筛选
- 按用户筛选
- 按时间范围筛选
- 按 IP 地址筛选
- 关键字搜索
- 导出查询结果

### 异常检测与告警

**自动告警规则：**

| 规则 | 触发条件 | 级别 | 通知 |
|---|---|---|---|
| **暴力破解** | 同一 IP 10 分钟内登录失败 > 20 次 | 高 | 安全团队 |
| **异常登录** | 用户从非常用地点 / 设备登录 | 中 | 用户本人 + 管理员 |
| **管理员登录** | 管理员账号登录 | 中 | 安全团队 |
| **权限升级** | 普通用户被授予管理员角色 | 高 | 安全团队 + 超级管理员 |
| **批量导出** | 单次导出 > 10000 条记录 | 中 | 管理员 |
| **模拟登录** | 管理员模拟用户登录 | 高 | 安全团队 |
| **设置变更** | 安全相关设置（SSO、IP 白名单）变更 | 高 | 管理员 |

---

## 合规要求对照

### SOC 2

- CC6.1 / CC6.2 / CC6.3 — 逻辑访问安全
- 要求：跟踪和监控用户活动，特别是特权活动
- 需要：审计日志、访问审查、异常检测

### 等保 2.0

- 三级要求：审计覆盖到每个用户，对重要操作有日志
- 审计记录保留 ≥ 6 个月
- 审计进程无法被中断
- 审计记录无法被删除、修改

### GDPR

- 数据访问需要可追溯
- 用户可以要求查看自己的数据被谁访问过
- 数据泄露 72 小时内通知监管机构（需要日志支持调查）

---

## 常见陷阱

| 陷阱 | 表现 | 规避方法 |
|---|---|---|
| 日志不全 | 出了安全事件找不到关键日志 | 梳理关键操作清单，确保全覆盖 |
| 日志能被删除 | 管理员自己删日志，毁尸灭迹 | 日志独立存储 + 只追加 + 权限隔离 |
| 没有日志查询界面 | 客户要审计日志只能找客服导出 | 提供自助审计日志页面 |
| 日志太多没用的 | 什么都记，关键信息被淹没 | 分类分级，只记重要的 |
| 日志里有敏感数据 | 日志里打了密码、token 之类的 | 敏感字段脱敏，绝不记密码和完整 token |
| 时间不对 | 日志时间不准，追溯混乱 | NTP 时间同步，统一 UTC 存储 |
| 保留期不够 | 合规要求一年，只存了 3 个月 | 了解合规要求，保留期按最高要求来 |

---

## 关联 SOP

- SSO 集成 → `saas-iam-sso-saml-oidc.md`
- RBAC / ABAC 权限 → `saas-iam-rbac-abac.md`
- 安全合规 → `../09-security-compliance/`
- 运维监控 → `../07-operations-reliability/saas-ops-monitoring-alerting.md`
