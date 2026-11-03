# session-boundary-guard — 详细设计 (DESIGN-DETAIL)

> 组件：session-boundary-guard (L2 基础设施层)
> 版本：v1.0
> 日期：2026-11-03
> 关联：ADR-202611-036 · PRD-v1.0 · DESIGN-OUTLINE-v1.0

## 1. 概述

本文档定义会话边界护栏插件的接口契约、数据模型、技术方案与测试方案。插件通过 OpenClaw `before_tool_call` hook 机制性拦截 agent 将消息/任务注入 pinned/live 会话（`agent:main:dashboard:*`）的跨会话调用，杜绝串台事故（FB-20261103-03）复发。

**设计基线（已实证）**：
- `before_tool_call` 返回契约：`{ params?, block?, blockReason?, requireApproval? }`，fail-closed 15s（`docs/plugins/hooks/tool-policy.md`）
- 会话 key 格式：`agent:<agentId>:<kind>:<uuid>`，kind ∈ {main, dashboard, subagent, cron, wecom}（`sessions_list` 实测）
- `api.runtime.gateway.request` 拒绝 external plugin → 判据不依赖实时状态查询（ADR-036 §3 选项 C 否决）

## 2. 接口契约

### 2.1 hook 注册契约

```javascript
api.on(
  "before_tool_call",
  handler,
  { matcher: ["sessions_send", "sessions_spawn"], priority: 50 }
);
```

- **matcher**：仅匹配两个跨会话工具，其余 tool call 零开销
- **priority 50**：低于 trusted tool policies，高于默认；不覆盖其他插件的决策
- **handler 签名**：`(event, ctx) => BeforeToolCallResult | undefined`

### 2.2 事件输入（host 提供）

| 字段 | 来源 | 用途 |
|---|---|---|
| `event.toolName` | host | 区分 `sessions_send` / `sessions_spawn` |
| `event.params.sessionKey` | host（send） | 目标会话 key → 判据 |
| `event.params.visible` | host（spawn） | `true` = 创建持久 dashboard 会话 → 拦截 |
| `event.params.label` / `agentId` | host（send，无 sessionKey 时） | 目标不可判 → 保守拦截 |
| `ctx.sessionKey` | host | 来源会话（审计用） |

### 2.3 判据函数

```javascript
// 输入目标 sessionKey，输出会话类别
function classifyTarget(sessionKey) {
  if (typeof sessionKey !== "string" || sessionKey.length === 0) return "unknown";
  const parts = sessionKey.split(":");
  // agent:<agentId>:<kind>[:...]
  if (parts.length < 3) return "unknown";
  const kind = parts[2];
  switch (kind) {
    case "dashboard": return "dashboard";   // pinned/live 会话 → 拦截
    case "subagent":  return "subagent";    // 一次性子会话 → 放行
    case "main":      return "main";        // 主会话 → 放行
    case "cron":      return "cron";        // cron 会话 → 放行
    case "wecom":     return "wecom";       // 渠道会话 → 放行
    default:          return "unknown";     // 不可判 → 保守
  }
}
```

### 2.4 决策函数

```javascript
function decide(event, config) {
  const tool = event.toolName;

  // 白名单精确匹配优先放行（合法通知场景）
  if (config.allowTargets?.includes(event.params?.sessionKey)) return undefined;

  if (tool === "sessions_send") {
    const target = event.params?.sessionKey;
    if (!target) {
      // 无 sessionKey（label/agentId 定向）→ 目标不可判，保守拦截
      return gate("sessions_send", "(label/agentId)", config);
    }
    const cls = classifyTarget(target);
    if (cls === "dashboard") return gate("sessions_send", target, config);
    return undefined; // subagent/main/cron/wecom → 放行
  }

  if (tool === "sessions_spawn") {
    if (event.params?.visible === true) {
      // visible=true → 创建持久 dashboard 会话
      return gate("sessions_spawn(visible)", "(new-dashboard)", config);
    }
    return undefined; // 普通 isolated subagent → 放行
  }

  return undefined;
}

function gate(tool, target, config) {
  audit({ tool, target, decision: config.mode === "block" ? "blocked" : "approval" });
  if (config.mode === "block") {
    return {
      block: true,
      blockReason: `跨会话注入被 session-boundary-guard 拦截：目标 ${target} 是 pinned/live 会话。旁路排查请改用 sessions_spawn(isolated)。`,
    };
  }
  return {
    requireApproval: {
      title: "跨会话注入拦截",
      description: `${tool} → ${target}（pinned/live 会话）。旁路排查请改用 sessions_spawn(isolated)；确需发送请 allow-once 放行。`,
      severity: "warning",
      timeoutMs: 60_000,
      allowedDecisions: ["allow-once", "deny"],
    },
  };
}
```

### 2.5 配置 Schema（`plugins.entries.session-boundary-guard.config`）

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `mode` | `"approve" \| "block"` | `"approve"` | 软闸门（弹批准） / 硬闸门（直接拒绝） |
| `allowTargets` | `string[]` | `[]` | 精确 sessionKey 白名单（合法通知目标），命中直接放行 |
| `debug` | `boolean` | `false` | 调试模式：审计记录全部决策（含放行） |

## 3. 数据模型

### 3.1 审计日志（`~/.openclaw/state/session-boundary-guard.jsonl`）

每行一个 JSON 对象，追加写：

```json
{
  "ts": "2026-11-03T12:00:00.000+08:00",
  "sourceSessionKey": "agent:main:main",
  "toolName": "sessions_send",
  "targetSessionKey": "agent:main:dashboard:650f782a-0f28-481c-a4c5-9447c392c62f",
  "decision": "blocked",
  "mode": "block"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `ts` | string (ISO8601) | ✅ | 决策时间 |
| `sourceSessionKey` | string | ✅ | `ctx.sessionKey`，来源会话 |
| `toolName` | string | ✅ | `sessions_send` / `sessions_spawn` |
| `targetSessionKey` | string | ✅ | 目标 key；无 sessionKey 时记 `(label/agentId)` |
| `decision` | string | ✅ | `blocked` / `approval` / `allowed` / `error` |
| `mode` | string | ✅ | 当前配置模式 |

### 3.2 审计写入语义

- **同步 append**（`fs.appendFileSync`）：拦截频率低（每次拦截 1 行），同步保证不丢审计、无竞态
- 文件不存在自动创建；写失败降级为 `console.warn`（拦截决策不受审计失败影响）
- 轮转：超 1MB 时归档为 `session-boundary-guard.jsonl.<ts>`，保留最近 5 份（对齐 compaction-state 约定）

## 4. 技术方案

### 4.1 插件文件结构

```
L2-infra/components/session-boundary-guard/
├── index.js                  # 插件主体（ESM：register + handler + classify + decide + audit）
├── package.json              # name/version/main/openclaw 兼容声明
├── openclaw.plugin.json      # id/configSchema/activation
├── README.md                 # 组件说明 + 快速开始
├── PRD-v1.0.md
├── DESIGN-OUTLINE-v1.0.md
├── DESIGN-DETAIL-v1.0.md     # 本文档
├── OPERATIONS-v1.0.md
├── VERIFICATION-v1.0.md
└── tests/
    └── test_classify.js      # 判据/决策黄金用例（node:test，零依赖）
```

### 4.2 插件主体（index.js 骨架）

```javascript
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import fs from "node:fs";
import path from "node:path";

const AUDIT_FILE = path.join(process.env.HOME, ".openclaw/state/session-boundary-guard.jsonl");

export default definePluginEntry({
  id: "session-boundary-guard",
  name: "Session Boundary Guard",
  description: "机制性拦截 agent 向 pinned/live 会话注入消息/任务（FB-20261103-03）",
  register(api) {
    api.on("before_tool_call", (event, ctx) => {
      const config = { mode: "approve", allowTargets: [], debug: false, ...(api.pluginConfig ?? {}) };
      const decision = decide(event, config);
      if (decision === undefined && config.debug) {
        audit(ctx, event, { decision: "allowed", mode: config.mode });
      }
      return decision;
    }, { matcher: ["sessions_send", "sessions_spawn"], priority: 50 });
  },
});
```

### 4.3 安装与启用（保护通道）

```bash
# 1) 插件落盘（managed install --link，参照 context-guardian 模式）
openclaw plugins install --link /Users/bangcle/.openclaw/workspace/L2-infra/components/session-boundary-guard

# 2) 启用（写 openclaw.json 走 CLI 保护通道，禁止手改）
openclaw plugins enable session-boundary-guard

# 3) 配置（approve 默认；如需硬闸门）
openclaw plugins config session-boundary-guard --set '{"mode":"block"}'

# 4) 验证
openclaw plugins list | grep session-boundary-guard
```

> 安装走 `openclaw plugins install/enable/config` CLI（managed install 记录 + 配置保护），**不手改 openclaw.json**（AGENTS.md「配置安全保护」五步流程由 CLI 内部保证）。

### 4.4 架构边界合规

- 判据基于 sessionKey 前缀（稳定契约），**不调用** `api.runtime.gateway.request`（external plugin 被拒）
- 不触碰运行时内部 API（ADR-012 / 架构 §5.2）
- 与 session-isolation（任务卡协议）、tool-policy（审计）、delivery-quality（质量账）职责正交

## 5. 错误处理

| 场景 | 行为 | 方向 |
|---|---|---|
| hook 超时（15s 宿主默认） | 宿主 fail-closed → 调用被 block | ✅ 安全（拦截方向） |
| 插件加载失败 | 插件不可用 → matcher 未注册 → 无拦截 | ⚠️ 需注意：此时护栏失效是"不拦"而非"全拦"。缓解：VERIFICATION 启动自检 + `openclaw plugins list` 巡检 |
| `api.pluginConfig` 缺失 | 使用默认值（approve/空白名单） | ✅ 保守 |
| 审计写失败 | `console.warn` 降级，不阻断决策 | ✅ 决策优先 |
| 未知 sessionKey 格式 | classify 返回 unknown → sessions_send 无 key 时保守拦截；有 key 且 unknown → 放行并 debug 审计 | ⚠️ 保守方向见 §2.4 |

> **fail-closed 语义澄清**：`before_tool_call` 的 fail-closed 指"hook 本身超时/异常 → 拒绝该 tool call"，本插件决策路径为纯同步前缀匹配，无 IO 依赖（审计为同步 append），实际超时概率≈0。插件未加载时 matcher 不生效（不拦），属配置层面问题，由 VERIFICATION 启动自检覆盖。

## 6. 测试方案

### 6.1 黄金用例（tests/test_classify.js，node:test）

| # | 输入 | 预期 |
|---|---|---|
| G1 | sessions_send → `agent:main:dashboard:650f...`，mode=approve | 返回 `requireApproval`，allowedDecisions=[allow-once, deny] |
| G2 | sessions_send → `agent:main:dashboard:650f...`，mode=block | 返回 `{block:true}`，blockReason 含"pinned/live" |
| G3 | sessions_send → `agent:main:subagent:abc` | `undefined`（放行） |
| G4 | sessions_send → `agent:main:cron:4dd...` | `undefined`（放行） |
| G5 | sessions_send → `agent:main:wecom:group:1313` | `undefined`（放行） |
| G6 | sessions_send → `agent:main:main` | `undefined`（放行） |
| G7 | sessions_send 无 sessionKey（仅 label/agentId） | `requireApproval` / `block`（保守拦截） |
| G8 | sessions_spawn visible=true | `requireApproval` / `block` |
| G9 | sessions_spawn visible=false / 缺省 | `undefined`（放行） |
| G10 | allowTargets 含目标 key | `undefined`（放行） |
| G11 | classify 边界：空串 / 非 string / 未知 kind | `unknown`（按 §2.4 处理） |
| G12 | 审计：拦截后 JSONL 落盘，6 字段完整 | 断言通过 |

### 6.2 E2E 验证（真实调用，VERIFICATION 阶段）

| # | 场景 | 预期 |
|---|---|---|
| E1 | 主会话尝试 sessions_send → 真实 dashboard 会话 | approve 模式：弹批准窗；deny 后目标 transcript 无新增 |
| E2 | sessions_spawn 普通 subagent（isolated） | 正常创建、运行、回执 |
| E3 | sessions_send resume 自己 paused child | 正常续跑（subagent:* 放行） |
| E4 | cron 会话投递 | 正常（不触发） |
| E5 | 插件禁用后 | matcher 不生效（文档注明风险 + 巡检覆盖） |

### 6.3 回归锁定

- `tests/test_classify.js` 全量通过（node --test）
- pre-commit 不挂载（纯插件代码，非 Python；VERIFICATION 手动触发）
- 升级 OpenClaw 后重跑 E1-E4

## 7. 交付检查（对齐 AGENTS.md「既有组件增量扩展完成检查」）

| # | 检查项 | 状态 |
|---|---|---|
| 1 | 技能固化（分层 SKILL 加能力描述与路由） | 本组件为插件非技能；README 承担入口说明；L2 skill 目录不动 |
| 2 | 资产清单 frontmatter → pre-commit 重生成 `01-asset-inventory.md` | 已手工同步（架构层）；pre-commit 复核 |
| 3 | 文档版本对齐（ADR/PRD/OUTLINE/DETAIL/OPERATIONS/VERIFICATION 全套） | 本次同步产出 |
| 4 | README/scripts 脚本清单与用法 | README 随建设补齐 |
