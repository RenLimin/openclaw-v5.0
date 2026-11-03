# session-boundary-guard — 产品需求文档 (PRD)

> 组件：session-boundary-guard (L2 基础设施层)
> 版本：v1.0
> 日期：2026-11-03
> 关联：ADR-202611-036 · FB-20261103-03 · AGENTS.md「会话隔离铁律」

## 1. 概述

**会话边界护栏**是一个 OpenClaw `before_tool_call` 插件，从机制上拦截 agent 将消息/任务注入 pinned/live 会话（`agent:main:dashboard:*`）的跨会话调用，杜绝串台事故复发。

它解决的是**行为规则管不住**的问题：AGENTS.md 已写明「旁路排查只能 sessions_spawn(isolated)」，但 2026-11-03 仍发生明知规范还复用 live 会话的事故。护栏与行为规则正交 —— **规则管"应不应该"，护栏管"调不调得通"**，fail-closed。

## 2. 问题背景（事故回顾）

| 项 | 内容 |
|---|---|
| 事故编号 | FB-20261103-03 |
| 发生时间 | 2026-11-03 |
| 事故链 | ① 主会话 `sessions_send` 把用户截图转发给正在跑「升级手册核查」的 pinned 会话 `650f…` 做旁路排查 → ② 回执带着该会话自己的任务上下文 → ③ 主会话把无关任务内容写进用户回复 → ④ auto-compaction 混编两条线，恢复后沿用错误摘要 |
| 根因 | agent 违反自身规范（复用 live 会话做旁路排查），行为规则无机制性兜底 |

## 3. 功能清单

| # | 功能 | 优先级 | 验收要点 |
|---|---|---|---|
| F1 | 拦截 `sessions_send` → dashboard 会话 | P0 | 目标 key 前缀 `agent:main:dashboard:` → requireApproval（默认）/ block（可配置），调用不生效 |
| F2 | 拦截 `sessions_spawn(visible=true)` → dashboard 会话 | P0 | 同上（visible spawn 会创建持久 dashboard 会话） |
| F3 | 放行合法跨会话路径 | P0 | subagent spawn / resume 自己 child / cron / wecom / conversations_* 均不受影响 |
| F4 | 拦截审计日志 | P1 | 每次拦截写 `~/.openclaw/state/session-boundary-guard.jsonl`：时间/来源会话/目标会话/工具/决策 |
| F5 | 配置化策略 | P1 | `mode: approve|block`、allow 前缀白名单（默认最小集）、debug 开关 |

## 4. 验收标准

1. **拦截生效**：对 `agent:main:dashboard:*` 的 `sessions_send`，approve 模式弹批准、block 模式直接拒绝，目标会话**收不到消息**（验证方式：调用后目标会话 transcript 无新增）
2. **合法路径零影响**：`sessions_spawn` 普通 subagent（isolated）、resume 自己 paused child（`subagent:*`）、cron 会话投递、wecom 群投递全量回归通过
3. **审计完整**：每次拦截（无论批准还是拒绝）都落盘审计行，含 5 个必需字段
4. **fail-closed**：插件禁用/加载失败/判据异常 → 护栏调用被拒绝（拦截方向安全，绝不静默放行）
5. **无性能回归**：hook 为纯前缀匹配 + 同步返回，单次决策 < 5ms，不影响正常 tool call 路径

## 5. 用户故事

- **作为主会话 agent**：我想在旁路排查时只使用 `sessions_spawn(isolated)`，但担心自己"图省事"又去复用 live 会话 —— 护栏应让我"想犯错也调不通"，即使尝试也会先被批准门拦下。
- **作为 Rex**：我希望串台这类事故从机制上不可能发生（或至少必须我显式批准），并且每次拦截都有日志可追溯、可反哺质量账。
- **作为运维**：我希望护栏的放行/拦截策略可配置、可观测，升级 OpenClaw 后通过回归用例快速验证契约未漂移。

## 6. 非功能需求

| 维度 | 要求 |
|---|---|
| 可靠性 | fail-closed；hook 超时 15s（宿主默认）；拦截失败方向安全 |
| 性能 | 纯字符串前缀匹配，无 IO（审计异步追加），单次 < 5ms |
| 可维护性 | 单插件目录、configSchema 完整、VERIFICATION 黄金用例锁定 |
| 可审计 | 审计行结构化 JSONL，字段稳定，可被 delivery-quality 引用 |
| 兼容性 | 依赖 OpenClaw plugin-sdk `before_tool_call` 契约（2026.9.8 验证）；升级时跑回归 |

## 7. 范围与边界

### 7.1 范围内
- 拦截 `sessions_send` / `sessions_spawn(visible=true)` 指向 dashboard 会话的调用
- 拦截决策（approve/block）+ 审计日志 + 配置
- 与 AGENTS.md 行为规则、delivery-quality 记账协同

### 7.2 范围外（明确不做）
- ❌ 不拦截 `conversations_send`/`conversations_turn`（外部渠道投递，非会话注入）
- ❌ 不查询目标会话实时状态（`api.runtime.gateway.request` 拒绝 external plugin，ADR-036 §3 选项 C）
- ❌ 不干预 `sessions_spawn` 普通 subagent（隔离的合法旁路）
- ❌ 不做"内容语义检查"（只按目标 key 前缀判断，不解析消息内容）
- ❌ 不接管 session-isolation 的任务卡/状态/事件协议（职责正交）

## 8. 依赖关系

| 依赖 | 说明 |
|---|---|
| OpenClaw plugin-sdk | `before_tool_call` hook（tool-policy 契约，fail-closed 15s） |
| OpenClaw 会话 key 契约 | `agent:<agentId>:<kind>:<uuid>`，kind ∈ {main, dashboard, subagent, cron, wecom} |
| AGENTS.md 铁律 | 行为规则层（第一层），本护栏是第三层技术兜底 |
| delivery-quality | 拦截审计反哺质量账（FB-20261103-03 的长期监控） |

## 9. 里程碑

| 阶段 | 产出 | 审核 |
|---|---|---|
| M1 架构层 | ADR-036 + 架构文档 + 资产清单 | ✅ 已完成（本 PRD 前） |
| M2 组件设计 | PRD → DESIGN-OUTLINE → DESIGN-DETAIL | Rex 审核（当前阶段） |
| M3 建设 | 插件实现 + install 落盘 + 启用 | 设计审核后 |
| M4 验收 | OPERATIONS + VERIFICATION + 7 步验收 | Rex 验收 |
