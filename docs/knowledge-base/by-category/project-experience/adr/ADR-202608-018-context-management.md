---
type: adr
id: ADR-202608-018
date: 2026-09-01
title: L2 上下文管理 — 三层防线 + 溢出防护状态机
status: accepted
deciders: [Rex]
layers: [L2]
tags: [context, compaction, overflow, safeguard]
supersedes: null
superseded_by: null
---

# [ADR-202608-018] L2 上下文管理

## 1. 状态
**accepted** — 2026-09-01 起生效

## 2. 背景

AI Agent 长会话运行时会持续累积 token，导致上下文溢出、会话卡死。需要标准化的上下文管理能力，防止因上下文溢出导致的服务中断。

## 3. 考虑的选项

### 选项 A: 被动压缩（仅 auto-compaction）
- 优点：配置简单
- 缺点：压缩时机不可控，可能来不及

### 选项 B: 三层防线（auto-compaction + mid-turn precheck + keepRecentTokens）
- 优点：多层保护，溢出前主动干预
- 缺点：配置复杂

### 选项 C: 外部上下文管理（委托给 LLM provider）
- 优点：零维护
- 缺点：不可控，不同 provider 行为不一致

## 4. 决策
我们选择 **选项 B**，因为需要主动防护而非被动等待。

## 5. 后果
### 5.1 正面
- 三层防线确保上下文不会溢出
- 状态机可视化当前水位
- 各模型独立阈值，精确控制

### 5.2 负面
- 配置复杂度高
- compaction 会消耗额外 token

### 5.3 风险
- compaction 模型不可用时会降级

## 6. 实现计划
- [x] 配置 auto-compaction (mode=safeguard)
- [x] 配置 mid-turn precheck
- [x] 校准各模型水位阈值
- [x] 配置 compaction 模型委托

## 7. 验证标准
- 长会话（>100 轮）不触发 HARD_LIMIT
- 压缩后关键上下文不丢失

## 8. 相关决策
- 相关 ADR: ADR-202608-015 (动态压缩模型路由)

## 9. 引用
- 设计文档: `docs/architecture/components/context-management/DESIGN.md`

## 10. 变更历史
- 2026-08-21: proposed
- 2026-09-01: accepted
