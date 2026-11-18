# context-guardian 修复版 — 产品需求文档 (PRD)

## 1. 概述

修复上下文保护插件 `openclaw-context-guardian` v5.1.1 的核心缺陷：**微压缩只写日志、不改写结果**，导致超大工具结果持续占据上下文、压力监控形同虚设。修复版以 v6 交付，行为对终端用户透明（无需改习惯），但结果必须**真实进入 transcript**。

## 2. 问题背景（事故回顾）

### 2.1 现象

- `gateway.log` 中 `Micro-compacted` 有 16 条，但主会话 transcript 中**从未出现**截断标记
- `Large result after compaction` 累计 1900+ 条，全部停在 `~8014 chars`（插件自身 `maxToolResultChars=8000` 的告警值），说明插件的压缩从未改变任何结果
- 压力分级日志里 `pressure=low` 与 `pressure=critical` 交替出现，但从未触发过真实的上下文削减

### 2.2 根因（两层，缺一不可）

**第 1 层：钩子语义误用（插件源码）**

host 对 `after_tool_call` 按 **Observe** 处理：

| 证据 | 位置 |
|---|---|
| 派发走 `runVoidHook`（fire-and-forget，返回值不回读） | `dist/hooks-BKWpaofg.mjs:691` |
| SDK 类型 `after_tool_call: AsyncPluginHook<Event, Ctx>`（**无 Result 泛型**） | `dist/types-BaOV3VIS.d.ts:18964` |
| `emitToolResultOutput` 在钩子之前已执行 | `dist/builtin-openclaw-DEib7rq9.mjs:3319` |
| 官方文档标注 `after_tool_call` = Observe；`tool_result_persist` = Sync modify | `docs/plugins/hooks/reference.md` |

→ 插件 `event.result = compactedResult` 永远丢弃。

**第 2 层：授权缺失（配置）**

非 bundled 插件读取会话内容的 typed hook（`before_prompt_build` 等）必须声明 `hooks.allowConversationAccess=true`。未声明则 host 在**注册期**直接 block：

```
typed hook "before_prompt_build" blocked because non-bundled plugins must set
plugins.entries.context-guardian.hooks.allowConversationAccess=true
```

→ 压力基线永不更新，`pressure` 分级失真。

**第 3 层（修正后剔除）**

曾判断 v5 的 `warn=12500` 高于 host 上限导致不可达——**该判断错误，已剔除**。

- 日志里的 `~8014 chars (limit=8000)` 是**插件自身** `maxToolResultChars=8000` 的告警值，不是 host 上限
- host 持久化 cap 由上下文窗口算出：`min(floor(ctx×0.3)×4, 分档hardCap)`，当前 196608 → **32000**
- 因此 v5 的 warn=12500 / critical=5000 均可触发；真正缺陷只有钩子误用 + 授权缺失两层

> 保留一条正向约束：插件阈值必须 < host cap（否则输入永远到不了阈值），v6 默认 7500/3000 满足。

### 2.3 归属判定

**自定义资产缺陷，非 OpenClaw 平台缺陷。** host 文档、SDK 类型、运行时行为三者一致；插件用错了 API。

## 3. 功能清单

| # | 功能 | 优先级 | 说明 |
|---|---|---|---|
| F1 | 结果改写迁至 `tool_result_persist` | P0 | 唯一 host 回读的改写点 |
| F2 | 保留工具三分类策略 | P0 | QUERY 压缩 / EDIT 保留 / PRESERVE 保留 |
| F3 | 阈值对齐 host cap | P0 | warn=base×2.5 且 < host 持久化 cap（当前 32000） |
| F4 | `before_prompt_build` 授权 | P0 | 随 entry 声明，恢复压力基线 |
| F5 | 会话状态有界化 | P1 | 修复 v5 无上限 Map 泄漏 |
| F6 | exec 输出预限流 | P1 | 保留，防患于未然 |
| F7 | `/compact` 自动触发 + 冷却 | P2 | 保留 |
| F8 | 可复现测试 | P0 | node:test 17 用例 |

## 4. 验收标准

| # | 标准 | 判定方式 |
|---|---|---|
| AC1 | 插件加载为 v6 | 日志出现 `[ContextGuardian] v6 loaded: ... rewrite=tool_result_persist` |
| AC2 | 无门禁 block | 新代际日志无 `context-guardian ... blocked` |
| AC3 | 压力基线恢复 | 日志出现 `session=...turn=... totalTokens=...` |
| AC4 | 压缩真实生效 | 日志出现 `Persist-compressed <tool>: N → M chars` |
| AC5 | **transcript 落库验证** | 被压缩结果的 transcript 文本含 `ContextGuardian` 标记且长度显著缩短 |
| AC6 | EDIT 工具不被压缩 | `edit`/`write` 结果无截断标记 |
| AC7 | 单元测试全绿 | `node --test tests/test_core.js` 17/17 |
| AC8 | `plugins update` 不覆盖 | 升级后仍为 v6（load.paths 优先级最高） |

## 5. 用户故事

- 作为长时间会话的使用者，我希望超大的日志/查询结果自动缩短，这样上下文不会溢出、任务不会中断。
- 作为审计者，我希望 `edit`/`write` 的完整结果始终保留，这样变更可追溯。
- 作为运维者，我希望压缩是否生效可被日志与 transcript 双重验证，这样不再出现"日志说压缩了、实际没压"的假象。

## 6. 非功能需求

- 零依赖（仅 `openclaw/plugin-sdk/plugin-entry`）
- 逻辑与注册分离，`core.js` 可单测
- 不引入新的全局锁持有行为
- 配置项向后兼容（保留 v5 键名）

## 7. 范围与边界

### 7.1 范围内
- 钩子迁移、阈值修正、授权声明、状态有界化、测试与文档

### 7.2 范围外（明确不做）
- 不改 OpenClaw host 源码
- 不修上游插件仓库（仅本地 vendor + shadow）
- 不处理 `wecom-openclaw-plugin` 的同类授权缺失（独立任务）
- 不调整 `compactionThreshold`（`/compact` 触发线，非本次缺陷）

## 8. 依赖关系

- OpenClaw ≥ 2026.3.24-beta.2（`tool_result_persist` 已在 2026.9.8 验证）
- 加载方式依赖 `plugins.load.paths` 优先级规则（config-selected 最高）

## 9. 里程碑

| 阶段 | 交付 |
|---|---|
| M1 | 核心逻辑 + 测试（17 用例通过） |
| M2 | 配置切换（load.paths + entry 授权） |
| M3 | 新代际验证（v6 loaded / 无 block / session= 恢复） |
| M4 | E2E transcript 验证 + 文档固化 |
