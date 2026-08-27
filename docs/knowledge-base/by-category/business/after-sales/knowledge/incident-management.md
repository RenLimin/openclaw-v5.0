---
title: 事件管理
description: 事件分级、响应流程、升级机制与 Post-Mortem
source: ITIL 4; PagerDuty Best Practices
version: 1.0
category: business
dimension: after-sales
sub_area: incident
type: knowledge
tags: [incident-management, escalation, post-mortem, on-call]
last_reviewed: 2026-08-27
---

# 事件管理

## 事件分级

| 级别 | 影响 | 响应时间 | 示例 |
|------|------|----------|------|
| Sev1 | 核心服务不可用 | 5min | 全站宕机、支付失败 |
| Sev2 | 主要功能受损 | 15min | 登录失败、搜索异常 |
| Sev3 | 次要功能异常 | 1h | 非核心页面报错 |
| Sev4 | 轻微问题 | 工作时间内 | UI 错位、文案错误 |

## 响应流程

```
检测 → 确认 → 止损 → 根因分析 → 修复 → 验证 → 闭环
```

## 升级机制

| 条件 | 动作 |
|------|------|
| 10min 未响应 | 升级到二线 |
| 30min 未恢复 | 升级到管理层 |
| 影响 > 100 客户 | 启动危机响应 |

## Post-Mortem

| 要素 | 说明 |
|------|------|
| 时间线 | 发现 → 响应 → 恢复 |
| 根因 | 5 Whys 分析 |
| 影响范围 | 客户数、时长、业务损失 |
| 改进项 | Action Item + Owner + Deadline |

**原则**：追因不追责，关注系统改进而非个人错误。
