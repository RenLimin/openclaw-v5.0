---
type: adr
id: ADR-202608-013
date: 2026-08-24
title: L2 会话生命周期管理
status: accepted
deciders: [Rex]
layers: [L2]
stage: develop
tags: [session, lifecycle, cleanup, maintenance, automation]
supersedes: null
superseded_by: null
---

# [ADR-202608-013] L2 会话生命周期管理

## 1. 状态
**accepted** (2026-08-24)

## 2. 背景

Agent 运行时会持续产生会话。08-23 清理前累积 19 个会话,靠 Rex 手动触发清理。`pruneAfter=48h` 是被动清理,不清理被 cron 历史引用的 cron run 会话。需要主动、分级、自动的会话生命周期管理。

## 3. 考虑的选项

### 选项 A: 维持现状(仅 pruneAfter)
- 优点: 零工作量
- 缺点: 被动清理,cron run 残留,会话持续增长

### 选项 B: 每日手动 cleanup
- 优点: 简单
- 缺点: 依赖人工,不可持续

### 选项 C: 自动分级清理(cron + deleteAfterRun + 分级策略)
- 优点: 全自动,不同会话类型不同策略,主会话受保护
- 缺点: 需要设计分级策略

## 4. 决策

选择 **选项 C** —— 自动分级清理。

## 5. 后果

### 5.1 正面
- 会话数量稳定在合理范围(主会话 + 活跃子代理 + 最近 7d 已完成 subagent)
- cron run 完成后立即清理
- 主会话绝对受保护

### 5.2 负面
- 已完成 subagent 7d 后清理,如需回溯需提前归档

## 6. 实现计划

- [x] DESIGN.md
- [x] 本 ADR
- [ ] 新增 cron:每日 02:00 自动 cleanup
- [ ] 为现有 cron 启用 deleteAfterRun
- [ ] 验证清理效果

## 7. 验证标准

- 会话数稳定在 ≤ 10 个(主会话 + 活跃 + 7d 内已完成)
- cron run 完成后 24h 内自动清理
- 主会话永不受影响

## 8. 相关决策

- 相关 ADR: ADR-202608-011(Error Contract,错误分级)

## 9. 变更历史

- 2026-08-24: proposed + accepted
