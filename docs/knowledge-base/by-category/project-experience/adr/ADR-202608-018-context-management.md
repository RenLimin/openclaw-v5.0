---
type: adr
id: ADR-202608-018
date: 2026-09-01
title: L2 上下文管理 — 两层压缩防线 + 生命周期治理
status: accepted
deciders: [Rex]
layers: [L2]
tags: [context, compaction, overflow, safeguard]
supersedes: null
superseded_by: null
---

# [ADR-202608-018] L2 上下文管理

## 1. 状态
**accepted** — 2026-09-01 起生效，2026-09-07 修订（补齐覆盖缺口）

## 2. 背景

AI Agent 长会话运行时会持续累积 token，导致上下文溢出、会话卡死。需要标准化的上下文管理能力，防止因上下文溢出导致的服务中断。

原设计为"三层防线"（auto-compaction + mid-turn precheck + session pruning），但实际运行中发现 session pruning 因运行时 provider 白名单限制不生效，存在覆盖缺口。同时 subagent 隔离会话无 compaction 保护、compaction 模型无 fallback 链也是已知风险。

## 3. 考虑的选项

### 选项 A: 被动压缩（仅 auto-compaction）
- 优点：配置简单
- 缺点：压缩时机不可控，可能来不及

### 选项 B: 两层压缩防线 + 生命周期治理
- 第 1 层：Auto-compaction（mode=safeguard，阈值维护 + 溢出恢复）
- 第 2 层：Mid-turn precheck（中途检查，中止并交给 recovery）
- 生命周期治理：会话生命周期管理 cron（每日 02:00 清理过期会话 + deleteAfterRun + 分级策略），替代原设计中不生效的 session pruning
- Subagent 上下文保护：分段执行 + runTimeoutSeconds + 输出精简
- Compaction fallback：同 provider 模型复用 + memoryFlush 独立模型兜底
- 优点：多层保护，溢出前主动干预，覆盖主会话 + subagent + 过期会话全场景
- 缺点：配置复杂度高，依赖 cron 做生命周期治理

### 选项 C: 外部上下文管理（委托给 LLM provider）
- 优点：零维护
- 缺点：不可控，不同 provider 行为不一致

## 4. 决策
我们选择 **选项 B（修订版）**：两层压缩防线 + 生命周期治理，因为需要主动防护而非被动等待，且需覆盖主会话、subagent、过期会话全场景。

### 4.1 关于 session pruning 的决策修订
原设计中第 3 层 session pruning（`session.maintenance.pruneAfter`）因运行时 provider 白名单限制不生效，**已由「会话生命周期管理」cron 替代**：
- cron 任务名：会话生命周期管理（ID: `2f7846b7-f4da-4d3e-b3bf-e7036bb80e4a`）
- 调度：每日 02:00 @ Asia/Shanghai
- 策略：分级清理 + deleteAfterRun + 过期会话回收
- 状态：2026-09-07 实查，运行正常（status: ok）

## 5. 后果
### 5.1 正面
- 两层压缩防线（主会话内）+ 生命周期治理（跨会话）确保上下文不会溢出
- 状态机可视化当前水位
- 各模型独立阈值，精确控制
- subagent 有明确的上下文保护规范
- compaction 模型故障时有降级路径

### 5.2 负面
- 配置复杂度高
- compaction 会消耗额外 token
- subagent 分段执行增加了主会话的调度复杂度

### 5.3 风险
- compaction 模型不可用时会降级到主模型（同 provider，网络命运共同体）
- subagent 长任务若未按规范分段仍可能溢出（依赖开发纪律 + 脚本辅助）
- 生命周期治理依赖 cron，若 cron 故障则过期会话堆积

## 6. 实现计划
- [x] 配置 auto-compaction (mode=safeguard)
- [x] 配置 mid-turn precheck
- [x] 校准各模型水位阈值
- [x] 配置 compaction 模型委托
- [x] 会话生命周期管理 cron 替代 session pruning
- [x] Subagent 上下文保护规范 + 辅助脚本
- [x] Compaction fallback 降级方案（同 provider + memoryFlush 兜底）

## 7. 验证标准
- 主会话：长会话（>100 轮）不触发 HARD_LIMIT
- 压缩后：关键上下文不丢失
- 生命周期：过期会话 48h 内被清理
- Subagent：长任务分段执行，不出现上下文溢出
- Compaction：模型故障时能降级到同 provider 备用模型

## 8. 相关决策
- 相关 ADR: ADR-202608-015 (动态压缩模型路由)
- 相关组件：会话生命周期管理（L2 基础设施层）
- 相关脚本：`L2-infra/components/context-management/subagent_ctx_guard.py`

## 9. 引用
- 设计文档: `docs/architecture/components/context-management/DESIGN.md`
- 架构文档: `docs/architecture/00-system-architecture.md` §6.1
- 经验记录: `docs/knowledge-base/by-category/project-experience/correct/EXP-20260821-003-compaction-model-delegation.md`

## 10. 变更历史
- 2026-08-21: proposed（三层防线初版）
- 2026-09-01: accepted（三层防线 + 溢出防护状态机）
- 2026-09-07: 修订 v2 — 补齐覆盖缺口：
  - session pruning → 会话生命周期管理 cron 替代
  - 新增 subagent 上下文保护规范
  - 新增 compaction fallback 降级方案
