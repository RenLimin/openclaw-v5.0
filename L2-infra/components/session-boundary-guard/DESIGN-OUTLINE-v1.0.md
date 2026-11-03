# session-boundary-guard — 概要设计 (DESIGN-OUTLINE)

> 组件：session-boundary-guard (L2 基础设施层)
> 版本：v1.0
> 日期：2026-11-03
> 关联：ADR-202611-036 · PRD-v1.0

## 1. 定位

**会话边界护栏**：OpenClaw `before_tool_call` 插件，机制性拦截 agent 将消息/任务注入 pinned/live 会话（`agent:main:dashboard:*`）的跨会话调用。

- **层级**：L2 基础设施层（通过受控扩展点 §5.3 插件机制实现，不触碰运行时内部 API §5.2）
- **与 session-isolation 的关系**：正交补强 —— session-isolation 管"跨会话如何协作"（任务卡/状态/事件协议），本组件管"哪些跨会话调用被禁止"（机制性闸门）
- **与 tool-policy 的关系**：tool-policy 是审计工具（验证允许≠可用），本组件是运行时执行器（在 hook 层实际拦截）

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway (L1)                     │
│                                                             │
│  agent 发起 tool call ──► before_tool_call hook 链           │
│                                │                            │
│                     ┌──────────▼──────────┐                 │
│                     │ session-boundary-   │                 │
│                     │ guard 插件 (L2)      │                 │
│                     │  ├ 判据: sessionKey  │                 │
│                     │  │     前缀匹配       │                 │
│                     │  ├ 决策: approve/    │                 │
│                     │  │     block/allow   │                 │
│                     │  └ 审计: JSONL 落盘  │                 │
│                     └──────────┬──────────┘                 │
│                                │                            │
│              ┌─────────────────▼─────────────────┐          │
│              │ 命中 dashboard:* ?                 │          │
│              │  ├ 是 → requireApproval / block    │          │
│              │  └ 否 → 放行（不干预）              │          │
│              └───────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块划分

| 模块 | 职责 | 载体 |
|---|---|---|
| **判据模块** | 解析 `event.toolName` + `event.params.sessionKey`，按前缀分类目标会话 | `index.js` 内 `classifyTarget()` |
| **决策模块** | 命中 dashboard → 按配置返回 `requireApproval` / `block`；命中 allow 白名单 → 放行 | `index.js` 内 `decide()` |
| **审计模块** | 拦截事件（无论批准/拒绝）异步追加 JSONL；debug 模式记录全部决策 | `audit.js`（或内联） |
| **配置模块** | `plugins.entries.session-boundary-guard.config`：mode / allowPrefixes / debug | `openclaw.plugin.json` configSchema |

### 2.3 与既有机制的分层

| 层 | 机制 | 作用 | 状态 |
|---|---|---|---|
| 第 1 层 | AGENTS.md「会话隔离铁律」 | 行为规则：旁路排查只能 spawn(isolated) | ✅ 已落地 |
| 第 2 层 | session-isolation 任务卡 | 任务身份锚定：恢复后核对 current-task | ✅ 已上线 |
| 第 3 层 | **本组件（session-boundary-guard）** | 技术护栏：想犯错也调不通 | 📋 本次建设 |

## 3. 接口契约

### 3.1 对宿主（OpenClaw）的契约

| 接口 | 方向 | 输入 | 输出 |
|---|---|---|---|
| `before_tool_call` hook | 宿主 → 插件 | `event.toolName`、`event.params`、`ctx.sessionKey` | `{ block?: boolean, blockReason?, requireApproval?: {...} }` |
| configSchema | 宿主 → 插件 | 配置 | `api.pluginConfig` |

### 3.2 判据契约（核心）

目标会话 key 前缀分类（OpenClaw 稳定契约，2026.9.8 实测）：

| key 前缀 | 类型 | 护栏动作 |
|---|---|---|
| `agent:<agentId>:dashboard:` | pinned/live 会话 | **拦截**（approve/block） |
| `agent:<agentId>:subagent:` | 一次性子会话 | 放行（isolated 旁路 / resume 自己 child） |
| `agent:<agentId>:main` | 主会话 | 放行 |
| `agent:<agentId>:cron:` | cron 会话 | 放行 |
| `agent:<agentId>:wecom:` | wecom 会话 | 放行 |

### 3.3 拦截返回契约

**approve 模式**（默认，软闸门）：
```javascript
{
  requireApproval: {
    title: "跨会话注入拦截",
    description: `sessions_send → ${targetKey}（pinned/live 会话）。旁路排查请改用 sessions_spawn(isolated)。`,
    severity: "warning",
    timeoutMs: 60_000,
    allowedDecisions: ["allow-once", "deny"]
  }
}
```

**block 模式**（硬闸门，可配置）：
```javascript
{
  block: true,
  blockReason: `跨会话注入被 session-boundary-guard 拦截：目标 ${targetKey} 是 pinned/live 会话。请改用 sessions_spawn(isolated)。`
}
```

### 3.4 审计契约

`~/.openclaw/state/session-boundary-guard.jsonl`，每行：

```json
{
  "ts": "2026-11-03T12:00:00+08:00",
  "sourceSessionKey": "agent:main:main",
  "toolName": "sessions_send",
  "targetSessionKey": "agent:main:dashboard:650f...",
  "decision": "blocked|approved|allowed|error",
  "mode": "approve|block"
}
```

## 4. 数据流

```
tool call 发起
  → hook 收到 {toolName, params, ctx}
  → classifyTarget(): 解析 params.sessionKey / params.agentId
  → 前缀判定
      ├─ dashboard:* → 查 allow 白名单 → 命中? 放行 / 未命中 → decide(): approve|block
      ├─ 其他前缀 → 放行
  → 审计落盘（异步，不阻塞决策）
  → 返回决策给宿主
```

## 5. 依赖关系

| 依赖 | 用途 | 版本约束 |
|---|---|---|
| OpenClaw plugin-sdk `before_tool_call` | 拦截入口 | 2026.9.8 已验证（docs/plugins/hooks/tool-policy.md） |
| 会话 key 前缀格式 | 判据 | 稳定契约（sessions_list 实测） |
| `~/.openclaw/state/` | 审计落盘 | 与 compaction-guard 同目录约定 |

## 6. 部署形态

- 组件目录：`L2-infra/components/session-boundary-guard/`（源码 + 文档 + 测试）
- 插件注册：`openclaw plugins install --link <组件目录>` → 生成 managed install 记录（参照 context-guardian 落盘 `~/.openclaw/extensions/`）
- 启用：`openclaw.json` `plugins.allow` 加 `session-boundary-guard` + `plugins.entries.session-boundary-guard.config`

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 误拦合法调用 | 默认 approve 模式（allow-once 可放行）；allow 白名单可配置 |
| hook 契约版本漂移 | VERIFICATION 黄金用例锁定，升级 OpenClaw 时回归 |
| 插件加载失败 | fail-closed（护栏失效 = 调用被 block，不放行） |
| 审计文件膨胀 | 按周轮转（参照 compaction-state 约定），保留 N 份 |
