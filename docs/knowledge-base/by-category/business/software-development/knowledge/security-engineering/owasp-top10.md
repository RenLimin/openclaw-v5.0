---
title: OWASP Top 10 威胁与防护
description: OWASP 2021 十大 Web 应用安全威胁与防护实践
source: OWASP Foundation; OWASP Top 10 2021
version: 1.0
category: business
dimension: software-development
sub_area: owasp-top10
type: knowledge
tags: [owasp, security, vulnerability, web-security]
last_reviewed: 2026-08-27
---

# OWASP Top 10 威胁与防护

## 2021 版 Top 10

| 排名 | 威胁 | 防护措施 |
|------|------|----------|
| A01 | 访问控制失效 | RBAC/ABAC、最小权限、鉴权中间件 |
| A02 | 加密失败 | TLS 1.3、敏感数据加密、密钥轮换 |
| A03 | 注入（SQL/NoSQL/命令） | 参数化查询、ORM、输入校验 |
| A04 | 不安全设计 | 威胁建模、安全设计评审 |
| A05 | 安全配置错误 | 默认安全、最小暴露、定期扫描 |
| A06 | 脆弱组件 | 依赖扫描（Snyk/Dependabot）、及时升级 |
| A07 | 认证失败 | MFA、密码策略、账户锁定 |
| A08 | 数据完整性失败 | 签名验证、依赖锁定、CI 校验 |
| A09 | 日志不足 | 审计日志、异常告警、不可篡改 |
| A10 | SSRF | URL 白名单、网络隔离 |

## 防护实践

### 安全编码清单

- [ ] 所有输入校验（白名单优于黑名单）
- [ ] 所有输出编码（HTML/URL/JS 上下文）
- [ ] 参数化查询（禁止拼接 SQL）
- [ ] 密码哈希（bcrypt/argon2，禁止 MD5/SHA1）
- [ ] CSRF Token（所有状态变更请求）
- [ ] CSP Header（限制资源加载来源）
- [ ] 文件上传校验（类型、大小、内容）

### 安全测试

| 类型 | 工具 | 频率 |
|------|------|------|
| SAST（静态扫描） | SonarQube、Semgrep | 每次提交 |
| DAST（动态扫描） | OWASP ZAP、Burp Suite | 每次发布 |
| 依赖扫描 | Snyk、Dependabot | 持续 |
| 渗透测试 | 人工 + 工具 | 季度 |
