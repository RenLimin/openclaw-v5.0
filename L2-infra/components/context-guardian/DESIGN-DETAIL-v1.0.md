# context-guardian 修复版 — 详细设计 (DESIGN-DETAIL)

## 1. 概述

v6 与上游 v5.1.1 的差异集中在三点：**改写钩子**、**阈值**、**授权**。行为策略（工具三分类、中间省略）保持不变。

## 2. 接口契约

### 2.1 hook 注册契约

| Hook | 语义 | 本插件行为 | 返回值 |
|---|---|---|---|
| `before_tool_call` | modifying | exec 追加 `\| head -N` | `{ params }` |
| `before_prompt_build` | modifying | 压力基线 + 临界注入 `/compact` | `{ appendContext }` |
| `after_tool_call` | **observe（不再改写）** | 累加压力统计 | 无 |
| `tool_result_persist` | **sync modify** | 压缩 toolResult 文本 | `{ message }` |

> host 对 `tool_result_persist` 的消费：`runToolResultPersist(...)?.message ?? message`（`resource-loader-DGY8KcdK.mjs`）。返回 `undefined` 时保持原消息。

### 2.2 `tool_result_persist` 事件结构（host 提供）

```ts
type PluginHookToolResultPersistEvent = {
  toolName?: string;
  toolCallId?: string;
  message: AgentMessage;      // role === "toolResult"
  isSynthetic?: boolean;
};
type PluginHookToolResultPersistResult = { message?: AgentMessage };
```

`message.content` 为 block 数组：`{ type: "text", text }` 或 `{ type: "image", data, mimeType }`。仅改写 `type === "text"` 的 block。

### 2.3 判据函数（core.js）

```
shouldMicroCompact(toolName, pressure, cfg):
  !microCompactEnabled            → false
  pressure === "low"              → false
  EDIT_TOOLS.has(toolName)        → false   # 审计保留
  PRESERVE_TOOLS.has(toolName)    → false   # web_search
  QUERY_TOOLS.has(toolName)       → true
  其他                            → pressure === "critical"

getMicroCompactThreshold(pressure, cfg):
  critical → microCompactMaxChars          (默认 3000)
  warn     → floor(microCompactMaxChars × 2.5) (默认 7500)
  low      → Infinity
```

### 2.4 截断函数

```
middleTruncate(text, maxChars, headRatio=0.4, tailRatio=0.2):
  若 len ≤ maxChars → 原样返回
  否则迭代收敛（提示语长度依赖截断数）：
    budget = maxChars - notice(truncatedCount).length
    head = floor(budget × 0.4); tail = floor(budget × 0.2)
  返回 head + notice + tail，总长 ≤ maxChars
```

### 2.5 配置 Schema（`plugins.entries.context-guardian.config`）

| 键 | 默认 | 说明 |
|---|---|---|
| `microCompactEnabled` | true | 总开关 |
| `microCompactMaxChars` | 3000 | critical 阈值（warn = ×2.5） |
| `microCompactPreserveEditTools` | true | EDIT 工具保留 |
| `warnThreshold` | 0.3 | warn 压力比例 |
| `compactionThreshold` | 0.45 | `/compact` 触发比例 |
| `effectiveContextWindow` | 0 | 0=自动读取 |
| `autoLimitExecOutput` / `execMaxLines` | true / 200 | exec 预限流 |
| `debug` | false | 调试日志 |

## 3. 数据模型

无持久化状态；会话状态为进程内 `Map`（有界 200，LRU 淘汰最旧）：

```
sessionState[sessionKey] = {
  estimatedTokens, lastCompactedAt, turnCount, toolCallsInCurrentTurn, pressure
}
```

## 4. 技术方案

### 4.1 插件文件结构

```
L2-infra/components/context-guardian/
├── index.js             # 注册入口
├── core.js              # 纯逻辑
├── tests/test_core.js   # 17 用例
├── openclaw.plugin.json
├── package.json
└── *.md                 # PRD/OUTLINE/DETAIL/OPERATIONS/VERIFICATION
```

### 4.2 加载与启用

```bash
# 1) 把本目录加入 load.paths（config-selected，最高优先级）
openclaw config patch --stdin   # plugins.load.paths 追加本目录
# 2) 声明会话访问授权
openclaw config patch --stdin   # plugins.entries.context-guardian.hooks.allowConversationAccess=true
# 3) 热加载
openclaw plugins reload context-guardian --json
```

### 4.3 架构边界合规

- 不修改 host 源码
- 不写凭据
- 不新增全局锁持有
- 插件 id 保持 `context-guardian`（同 id 只保留最高优先级 manifest）

## 5. 错误处理

| 场景 | 处理 |
|---|---|
| `tool_result_persist` 返回结构异常 | host 回退原 message（`?? message`），不会崩溃 |
| 单条 block 无 text | 原样保留 |
| `enqueueNextTurnInjection` 失败 | 降级为 `appendContext` 提示手动 `/compact` |
| 会话状态超限 | LRU 淘汰最旧 sessionKey |

## 6. 测试方案

### 6.1 黄金用例（`tests/test_core.js`，node:test，17 用例）

G1–G7 分类决策；G8–G9 阈值与 host 上限关系；G10–G13 截断原语（含"总长不超预算"不变量）；G14–G15 估算；G16 压力分级；G17 三分类互斥。

### 6.2 E2E 验证（真实运行环境）

1. 加载后日志 `v6 loaded ... rewrite=tool_result_persist`
2. 无 `blocked because non-bundled`
3. 出现 `session=...turn=...`
4. 构造 >3000 chars 的 exec 结果 → 日志 `Persist-compressed`，且该 toolResult 在 `sessions_history` 中长度显著缩短并含 `ContextGuardian` 标记

### 6.3 回归锁定

`node --test tests/test_core.js` 必须 17/17；每次改动 core.js 后重跑。

## 7. 交付检查（对齐 AGENTS.md）

| # | 检查项 | 状态 |
|---|---|---|
| 1 | 技能固化 | 本组件为插件非技能；README 承担入口说明 |
| 2 | 资产清单同步 | 待 pre-commit 复核 |
| 3 | 文档版本对齐 | 本次同步产出 |
| 4 | README/scripts 清单 | README 已含验证命令 |
