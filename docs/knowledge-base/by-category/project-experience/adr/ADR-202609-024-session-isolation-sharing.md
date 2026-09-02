---
type: adr
id: ADR-202609-024
date: 2026-09-02
title: L2 会话隔离与共享 — 跨会话状态协作机制
status: proposed
deciders: [Rex]
layers: [L2]
stage: design
tags: [session, isolation, sharing, task-protocol, state-protocol, event-protocol]
supersedes: null
superseded_by: null
---

# [ADR-202609-024] L2 会话隔离与共享

## 1. 状态
**proposed** — 2026-09-02

## 2. 背景

Agent 运行时存在多种会话(主会话、子代理、cron 运行、探测),当前存在:

- **会话间无隔离**: 上下文可能污染,子代理与父会话共享上下文
- **会话间无共享**: 任务进度靠 transcript 传递,`/reset` 后丢失
- **任务上下文易失**: 重置后无法恢复任务现场
- **无故障隔离**: 单任务失败可能影响整体

需要标准化的**跨会话隔离与共享**机制。

## 3. 考虑的选项

### 选项 A: 只靠 OpenClaw 原生能力(不建设)
- 优点: 零工作量,复用 sessions_spawn/send/yield
- 缺点: 任务进度仍靠 transcript,reset 后丢失;无显式共享状态;无审计

### 选项 B: 全耦合建设(直接绑定 OpenClaw hooks/API)
- 优点: 实现快,直接调用 before_prompt_build / agent_end
- 缺点: **违反 ADR-012**(L2 只依赖抽象契约),切换运行时需重写

### 选项 C: 分层建设(零耦合协议层 + L1 适配层耦合)
- 优点: 协议层运行时无关,未来可移植;只适配层绑定 OpenClaw;符合 ADR-012
- 缺点: 需先设计协议层,初期工作量稍大

## 4. 决策

选择 **选项 C** —— 分层建设。

理由:
1. **符合 ADR-012**: L2 只依赖 L1 抽象契约,不绑定具体运行时
2. **可移植**: L3 协议层(纯文件/数据结构)可跨框架复用
3. **职责正交**: 与 ADR-013(清理) / ADR-018(溢出) / ADR-014(错误) 不重叠
4. **零耦合优先**: 共享状态用纯文件/数据结构,机制本身不依赖 LLM 驱动

## 5. 后果

### 5.1 正面
- 跨会话状态显式共享,默认隔离
- 任务进度可持久化,`/reset` 后可恢复
- 协议层零耦合,可移植到任何框架
- 事件审计可追溯

### 5.2 负面
- 初期需先设计协议层,工作量稍大
- 状态文件需要维护(归档/压缩)

### 5.3 风险
- 状态文件膨胀 → 按任务归档,定期压缩
- 并行写入冲突 → reducer 确定性合并
- 与上下文管理抢预算 → 独立 API,不占上下文

## 6. 实现计划

### P0: 手动版(当前阶段)
- [x] 组件目录创建
- [x] DESIGN.md
- [x] 本 ADR
- [ ] `tasks/` 目录 + TASK.yml 模板
- [ ] 迁移当前 BDMS 任务做验证

### P1: 半自动(脚本驱动)
- [ ] `scripts/session_isolation/` 工具集(task_init / state_reducer / event_logger)
- [ ] 适配层扩展 `adapters/openclaw/`(L1 接口)
- [ ] 手动触发 hook 同步

### P2: 全自动(plugin 驱动)
- [ ] OpenClaw plugin 化(适配层内)
- [ ] 完整 reducer + 子代理 supervisor
- [ ] 跨框架可移植验证

## 7. 验证标准

1. 隔离: 子代理独立上下文,不污染父会话
2. 共享: 跨会话通过 State Protocol 显式读写,reducer 正确处理并行写入
3. 恢复: `/reset` 后新会话通过 TASK.yml + events 恢复任务现场
4. 零耦合: L2 服务层零 OpenClaw 特有概念(对齐 ADR-012 验证标准)
5. 防冲突: 不影响会话生命周期清理 / 上下文管理 / 错误处理

## 8. 相关决策

- 相关 ADR: ADR-202608-012 (运行时抽象,约束 L2 只依赖抽象契约)
- 相关 ADR: ADR-202608-013 (会话生命周期,管清理,本组件管共享,正交)
- 相关 ADR: ADR-202608-014 (错误自动处理,子代理 supervisor 归其管)
- 相关 ADR: ADR-202608-018 (上下文管理,管溢出,本组件管共享,正交)

## 9. 变更历史

- 2026-09-02: proposed(组件 + DESIGN.md 同步创建)
