---
type: adr
id: ADR-202611-036
date: 2026-11-03
title: 会话边界护栏 — 跨会话工具调用的机制性拦截
status: proposed
deciders: [Rex]
layers: [L2]
stage: design
tags: [session, isolation, guard, tool-policy, before_tool_call, cross-session, FB-20261103-03]
supersedes: null
superseded_by: null
---

# [ADR-202611-036] 会话边界护栏

## 1. 状态
**proposed** — 2026-11-03

## 2. 背景

2026-11-03 发生串台事故（FB-20261103-03）：主会话将用户截图用 `sessions_send` 转发给一个正在执行无关任务的 pinned dashboard 会话（`agent:main:dashboard:650f...`）做旁路排查，其回执携带该会话自身任务上下文，被误当作本会话内容写入用户回复；随后 auto-compaction 将两条线混编进恢复摘要，错误延续。

会话隔离机制本身存在且生效（每个会话独立 sessionKey + context/transcript），但**隔离只约束上下文可见性，不约束 agent 主动的跨会话写入**。根因是 agent 行为违规（复用 live 会话做旁路排查），而行为规则依赖模型自觉，明知规范仍可能违反（本次即如此）。

需要从机制层面兜底：**拦截 agent 将消息/任务注入 pinned/live 会话的跨会话调用**，让"想犯错也调不通"。

## 3. 考虑的选项

### 选项 A: 仅行为规则（AGENTS.md 硬规则 + delivery-quality 记账）
- 优点: 零成本，已落地（2026-11-03 写入 AGENTS.md）
- 缺点: **不可靠** —— 依赖模型自觉，本次事故正是"明知规范仍违反"；无机制性阻断
- 结论: 保留为第一层，但不足以独立承担

### 选项 B: `before_tool_call` 插件护栏（sessionKey 前缀判据）
- 机制: 插件订阅 `before_tool_call`（15s fail-closed），匹配 `sessions_send`/`sessions_spawn(visible)`，对目标 sessionKey 前缀为 `agent:main:dashboard:` 的调用返回 `block` 或 `requireApproval`
- 判据可行性: 会话 key 格式固定（`agent:main:dashboard:<uuid>` = pinned 会话、`agent:main:subagent:<uuid>` = 一次性子会话、`agent:main:main` = 主会话、`agent:main:cron:*` / `agent:main:wecom:*`），**无需查询实时会话状态**
- 优点: 机制性兜底，fail-closed；事件含 `ctx.sessionKey`/`event.params.sessionKey`，判据充分；无需 conversation access
- 缺点: 依赖 OpenClaw hook 契约；插件需维护

### 选项 C: `api.runtime.gateway.request` 查询目标会话实时状态后决策
- 机制: 插件在 hook 内调用 Gateway RPC 获取目标会话 pinned/running 状态，动态决策
- **否决**: 文档明确 `api.runtime.gateway.request` **拒绝来自 arbitrary external plugins 的调用**（`Calls from arbitrary external plugins are rejected`），仅限 bundled/trusted 官方插件
- 结论: 不可行，且引入运行时耦合与超时风险，违背 ADR-012 抽象契约

### 选项 D: 上层工具策略 deny（tools.deny 禁掉 sessions_send）
- 优点: 配置级，零代码
- 缺点: **一刀切** —— 同时禁掉合法用途（resume 自己 paused 的 subagent、cron 会话投递、子会话编排）；粒度不足以区分"目标是谁"
- 结论: 拒绝

## 4. 决策

选择 **选项 B** —— `before_tool_call` 插件护栏，以 **sessionKey 前缀判据** 拦截跨会话注入。

理由:
1. **机制性兜底**: 与行为规则正交 —— 规则管"应不应该"，护栏管"调不调得通"，fail-closed
2. **零运行时耦合**: 不依赖查询实时会话状态（选项 C 被否决后唯一可靠判据）；key 前缀是 OpenClaw 稳定契约
3. **粒度精确**: 仅拦 `sessions_send`/`sessions_spawn(visible)` 指向 `dashboard:` 前缀的调用；subagent/cron/主会话合法路径不受影响
4. **可审计**: 拦截事件落盘 state 文件（参考 compaction-guard 模式），支持事后追溯
5. **符合架构**: L2 层通过插件机制（受控扩展点 §5.3）实现，不触碰运行时内部 API（§5.2）

## 5. 后果

### 5.1 正面
- 串台路径（向 pinned/live 会话注入）从机制上不可达，或至少需 Rex 显式批准
- 拦截有日志，违反可追溯、可统计（反哺 delivery-quality）
- 合法旁路路径（isolated subagent spawn）完全不受影响

### 5.2 负面
- 引入一个需维护的 L2 插件（升级 OpenClaw 时需验证 hook 契约兼容性）
- 若未来会话 key 格式变化，判据需同步更新（风险低，key 为稳定契约）
- block 模式下若模型误用合法路径（如 resume 自己的 child），需人工干预

### 5.3 风险与缓解
- 误拦合法调用 → 默认 `requireApproval`（allow-once 可放行），而非硬 block；Rex 拍板后收敛
- hook 契约漂移 → VERIFICATION 锁定黄金用例，升级时回归
- 插件加载失败 → fail-closed（拦截方向安全：护栏失效 = 调用被 block，不会放行）
- 白名单泄漏（如向 dashboard 会话发送 legit 通知）→ 配置化 allow 前缀，默认最小集

## 6. 实现计划（自上而下，Rex 逐级审核）

### 架构层（本 ADR 所属阶段）
- [x] ADR-202611-036（本文档）
- [ ] `00-system-architecture.md` 更新（L2 组件表 + §5 契约边界新增小节）
- [ ] `01-asset-inventory.md` 更新（ADR 清单 + L2 组件表）

### 组件层
- [ ] 组件 PRD（`L2-infra/components/session-boundary-guard/PRD-v1.0.md`）→ Rex 审核
- [ ] DESIGN-OUTLINE-v1.0.md → Rex 审核
- [ ] DESIGN-DETAIL-v1.0.md → Rex 审核

### 建设层
- [ ] 插件实现（`session-boundary-guard` plugin：before_tool_call + state 审计 + config）
- [ ] `openclaw plugins install --link` 落盘 + 启用
- [ ] OPERATIONS-v1.0.md + VERIFICATION-v1.0.md
- [ ] 验收 7 步法（黄金用例：dashboard 拦截 / subagent 放行 / cron 放行 / resume 放行）

## 7. 验证标准

1. **拦截**: `sessions_send` 指向 `agent:main:dashboard:*` → requireApproval/block，调用不生效
2. **放行**: `sessions_spawn` 普通 subagent、`sessions_send` 指向 `agent:main:subagent:*`（resume 自己 child）→ 不受影响
3. **审计**: 每次拦截写入 state 日志（时间/来源会话/目标会话/工具/决策）
4. **fail-closed**: 插件禁用/加载失败 → 护栏调用被 block（方向安全）
5. **无回归**: 现有 cron（wecom/1313）、任务卡、spawn 流程全量通过

## 8. 相关决策

- 相关 ADR: ADR-202608-012（运行时抽象，约束 L2 不绑定运行时内部 API）
- 相关 ADR: ADR-202609-024（会话隔离与共享 —— 本护栏是其机制性补强，将隔离从"上下文不可见"升级到"不可注入"）
- 相关 ADR: ADR-202610-035（Prompt 治理 —— 行为规则属 P1 契约，护栏是规则之外的机制层）
- 相关事故: FB-20261103-03（会话串台，本 ADR 的直接触发）

## 9. 变更历史

- 2026-11-03: proposed（架构层首份产出，待 Rex 审核）
