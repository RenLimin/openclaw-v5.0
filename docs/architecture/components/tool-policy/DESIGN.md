---
type: design
component: tool-policy
layer: L2
status: active
date: 2026-08-22
owner: Rex + Jerry
---

# L2 工具策略治理 — 设计

> **状态**: ✅ 已上线 (2026-08-23) — ADR-008 已实现,三态模型 + 六项审计,工具策略治理落地
> **ADR**: [ADR-202608-008](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md)
> **架构文档**: `00-system-architecture.md` §3.2 / §5.4

## 1. 核心洞察：「允许」≠「可用」

架构文档 §5.4 原本把工具策略问题定义为"哪些工具被 deny"。**这个定义不完整。**

实测发现工具实际有**三种状态**，而 `tools.profile` / `allow` / `deny` 只治理第一条边界：

| 状态 | 含义 | 现有策略能否表达 | 危险性 |
|---|---|---|---|
| **denied** | 策略拒绝，工具不出现 | ✅ 能 | 低 —— 明确失败 |
| **allowed-but-broken** | 策略允许，但缺依赖/凭据/provider，**静默降级或不出现** | ❌ **不能** | **高 —— 静默失败** |
| **allowed-and-working** | 策略允许且真实可用 | ✅ 能 | — |

**治理缺口就是中间那一层。** 它不报错、不告警，只是悄悄不干活或降级。

## 2. 当前状态（实测）

配置极简：

```json5
{ tools: { profile: "coding", alsoAllow: ["tavily_search", "tavily_extract"] } }
```

### 2.1 官方 profile 定义（一手来源）

来源：`docs/gateway/config-tools.md`

| Profile | 包含 |
|---|---|
| `minimal` | 仅 `session_status` |
| `coding` | `group:fs` `group:runtime` `group:web` `group:sessions` `group:memory` `cron` `get_goal` `create_goal` `update_goal` `update_plan` `ask_user` `skill_workshop` `image` `image_generate` `music_generate` `video_generate` |
| `messaging` | `group:messaging` + sessions 编排子集 |
| `full` | 无限制 |

`coding` 与 `messaging` 隐式允许 `bundle-mcp`（已配置的 MCP server）。

**关键规则**（易错）：
- `allow` 与 `alsoAllow` **不能在同一 scope 并存**，config 校验会拒绝。用 `profile` + `alsoAllow`。
- **deny 优先于 allow**。
- `deny: ["write"]` **不会**连带 deny `apply_patch` —— 它们是独立 tool id。要禁全部文件写入须 deny `group:fs` 或逐个列出。
- `allow: ["write"]` **会**连带启用 `apply_patch`（不对称）。

### 2.2 实测发现的三类问题

#### 问题 A：12 个技能「允许但不可用」

`openclaw skills check` 输出（缺依赖，非策略拒绝）：

| 技能 | 缺什么 |
|---|---|
| `coding-agent` | bins: claude/codex/opencode 之一 + config 开关 |
| `goplaces` | bins: goplaces + env: `GOOGLE_PLACES_API_KEY` |
| `mcporter` / `obsidian` / `oracle` | 对应 bins |
| `openai-whisper` | bins: whisper |
| `openai-whisper-api` | env: `OPENAI_API_KEY` |
| `sag` | env: `ELEVENLABS_API_KEY` |
| `session-logs` | bins: rg |
| `sherpa-onnx-tts` | env: `SHERPA_ONNX_RUNTIME_DIR` + `SHERPA_ONNX_MODEL_DIR` |
| `spotify-player` | bins: spogo/spotify_player |
| `trello` | env: `TRELLO_API_KEY` + `TRELLO_TOKEN` |

**影响**：技能在 catalog 里可见，agent 可能尝试调用后失败。浪费 token 与轮次。

> ⚠️ `AGENTS.md` 里的「Voice storytelling: 如有 `sag` 就用语音讲故事」**当前不可用**（缺 `ELEVENLABS_API_KEY`）。指令与环境不一致。

#### 问题 B：`memory_search` 静默降级 ★ 最严重

**实测证据**（调用 `memory_search` 的返回元数据）：

```json
{
  "provider": "none",
  "debug": {
    "embeddingBootstrap": {
      "ok": false,
      "provider": "openai",
      "reason": "No API key found for provider \"openai\" ... missing-provider-auth",
      "degradedTo": "keyword-only"
    }
  }
}
```

**为什么最严重**：
1. 系统级指令**强制要求**先 `memory_search` 再回答记忆类问题
2. 它**不报错**——照常返回结果，只是从语义检索降级为关键词匹配
3. 中文记忆尤其吃亏：语义检索失效后，同义表述（如"配置管理"vs"config 治理"）召回不到
4. `openclaw memory status --deep` 本身也因缺 key 无法运行（CLI 启动即失败）

**修复选项**（需 Rex 定夺，涉及凭据/成本）：

| 选项 | 代价 | 备注 |
|---|---|---|
| 本地 GGUF embedding | 一次性下载模型，**零 API 成本** | `openclaw plugins install @openclaw/llama-cpp-provider` + `memory.search.provider: "local"` |
| ARK `doubao-embedding-large` | 按量计费（文本 ~¥0.0007/千 tok） | `provider: "openai-compatible"`；**未实测** —— 配置里的 key 是 SecretRef 占位符（`__OP...`），验证需取出真实凭据，已主动放弃 |
| `OPENAI_API_KEY` | 需新凭据 + 境外网络 | 官方默认路径 |
| 接受关键词模式 | 零成本 | 显式记录降级，别假装有语义检索 |

**推荐**：本地 GGUF（零成本 + 无外发 + 中文可用）。属新增依赖，等 Rex 拍板。

#### 问题 C：媒体工具在 profile 内但无 provider

`coding` profile 含 `image_generate` / `music_generate` / `video_generate`，但
`agents.defaults.mediaModels` **未配置**。据官方文档，工具"只在至少配置一个
provider 时出现"。属预期行为，非故障 —— 但说明**profile 声明 ≠ 工具可用**。

### 2.3 不对称现象（已查清@2026-08-23 第三轮 review）

| 观察 | 说明 |
|---|---|
| Tavily 插件工具在 `coding` 下**被 deny**，需 `alsoAllow` 显式解锁（EXP-20260821-001） | 已验证 |
| `terminal` / `screen` 官方文档表格列入 `group:ui`，但**运行时 `POLICY_TOOL_GROUPS` 仅含 `browser`+`canvas`** | ✅ 已查清 |
| `dashboard` **不在** `group:ui` 里 —— 文档版与运行时版都没有。它是 workboard 插件工具 | ✅ 已查清 |

**运行时真值**（`dist/register-pGYK5dOd.js:3928`）：

```js
"group:ui": ["browser", "canvas"],
```

**官方文档说法**（`gateway/config-tools.md:41`）：

> `group:ui` | `browser`, `screen`, `terminal`, `canvas`, `show_widget`

**结论**：

1. **`terminal`/`screen` 天然可用** —— 它们不被任何 `group:` 覆盖，因此 `coding` profile
   的 allowlist **不构成对它们的排除路径**。这就是「实际可用却不在 profile 列表内」的答案。
2. **`dashboard` 属插件工具** —— 走 plugin 注册路径（`plugins/manifest.md:165`、
   `web/dashboards.md:66`），不受 profile 约束。**v1 把它归入 `group:ui` 是事实错误。**
3. **官方文档表格已过期** —— 列 5 个工具，运行时只有 2 个。属官方文档缺陷，
   记入「官方文档缺口」类目。

> **ADR-008 决策 4 的谨慎是对的** —— 当时没瞎猜「可能是因为…」，而是明确记「未查清」。
> 现在查清了：答案确实需要读 dist 源码常量，光看官方文档表格会得出错误结论
> （表格说 `terminal` 属 `group:ui` ⇒ 会误以为 `coding` profile 应该排除它）。
> **教训**：官方文档表格与运行时常量都要查，不一致时以运行时为准。

## 3. 治理原则

1. **最小权限**：保持 `profile: "coding"`，不升 `full`。新工具走 `alsoAllow` 逐个解锁并记录理由。
2. **可用性与授权分开审计**：`allow` 只答"准不准用"，必须另有机制答"能不能用"。
3. **静默降级必须显式化**：降级不报错的能力（如 `memory_search`）要在文档中标明真实状态，不能假设它按标称工作。
4. **指令与环境一致**：`AGENTS.md` 不应引用不可用的工具（如 `sag`）。
5. **禁用而非放任**：长期不可用的技能应 `openclaw doctor --fix` 关掉，减少 catalog 噪音与误调用。

## 4. 工具清单与理由

| 工具/组 | 状态 | 理由 |
|---|---|---|
| `group:fs` `group:runtime` | allow | 核心：系统建设需读写文件、执行命令 |
| `group:sessions` | allow | subagent 并行、跨会话协作 |
| `group:memory` | allow **but degraded** | 见问题 B |
| `group:web` | allow | 查官方文档/一手来源 |
| `tavily_search` `tavily_extract` | `alsoAllow` 解锁 | 深度检索；EXP-20260821-001 |
| `cron` | allow | L2 调度（每日观测摘要） |
| `skill_workshop` | allow | 经验沉淀 |
| 媒体工具 | allow 但无 provider | 见问题 C，暂不需要 |
| `group:messaging` | **不在 coding profile** | 本机零 channel 配置，无需求 |
| `full` profile | **拒绝** | 违反最小权限 |

## 4.1 `tools.elevated` — 提权 exec 门禁（2026-08-23 补登，同日修正）

> ⚠️ **2026-08-23 第三轮 review 修正**：本节 v2 内容有严重论证错误 —— 把 `allowFrom` 说成
> 「外部渠道触发提权 exec 的唯一白名单门禁」，并断言「提权 exec 全面禁用，此为期望状态」。
> **方向反了**。错因与 ADR-009 同构：读 `gateway/config-tools.md:184-203` 拿到字段语义就停，
> 没读 `tools/elevated.md` 开头那个 Info 框里的决定性前提。

### 决定性前提：sandbox 未开启 ⇒ elevated 是 no-op

三处官方原文一致：

| 出处 | 原文 |
|---|---|
| `tools/elevated.md:10-12`（Info 框） | Elevated mode only changes behavior when the agent is **sandboxed**. For unsandboxed agents, **exec already runs on the host**. |
| `gateway/sandboxing.md:9` | Sandboxing is **off by default** |
| `gateway/sandboxing.md:23` | **If sandboxing is off, `tools.elevated` changes nothing** since exec already runs on the host. |

**本机实测**：`openclaw config get agents.defaults.sandbox` → `Config path not found`
（未配置 → 走默认 `off`，`sandboxing.md:31` 默认值表确认）。

上一轮记录的报错原文恰是铁证：`elevated is not available right now (runtime.direct)`
—— `direct` 即「未沙箱化」，由 `dist/elevated-unavailable-BU5O8gUq.js:71` 的
`params.runtimeSandboxed ? "sandboxed" : "direct"` 生成。

### 当前真实状态（实测@2026-08-23）

```json5
// tools 下只有两个字段，elevated 未配置 → 走默认关闭
{ tools: { profile: "coding", alsoAllow: ["tavily_search", "tavily_extract"] } }
```

| 说法 | 判定 |
|---|---|
| 「提权 exec 全面禁用」 | ⚠️ **误导**。被禁的是 `elevated` **标志位**；`exec` 实际权限**已是 host 全权**（sandbox=off + `group:runtime` 已 allow） |
| 「`allowFrom` 是唯一门禁」 | ❌ **错误**。sandbox=off 下它管的那条路本来就不存在 |
| 「此为期望状态」 | ⚠️ 结论巧合正确（不该开 elevated），但**理由错**——不是「有一道墙」，而是「那道墙在 sandbox=off 下不存在」 |

### 真正有效的门禁

| 门禁 | 作用 | 官方依据 |
|---|---|---|
| `tools.deny` | **hard stop**，elevated 无法覆盖 | `tools/elevated.md` §What elevated does not control：if `exec` is denied by tool policy, elevated cannot override it |
| `tools.toolsBySender` | 按**渠道 + 发送者**收紧当前轮工具集，可 `deny: ["group:runtime"]` | `gateway/config-tools.md:164-182` |
| `channels.wecom.dmPolicy` / `allowFrom` | 渠道层准入（谁能触达 agent） | 渠道配置 |

**若要限制 WeCom 触发 host exec，正确的键是 `tools.toolsBySender`，不是 `tools.elevated`。**
这是当前唯一真实有效的对外渠道 exec 收紧手段：

```json5
{ tools: { toolsBySender: {
    "channel:wecom:*": { deny: ["group:runtime", "group:fs"] },
} } }
```

> ⚠️ 上述为**建议形态，未实测**。`config-tools.md:166` 强调 sender 值必须来自
> channel adapter 而非消息文本；启用前需验证 WeCom adapter 提供的 sender 键形态。

### 字段语义（官方 `gateway/config-tools.md:184-204` + `tools/elevated.md:85-102`）

| 字段 | 语义 |
|---|---|
| `tools.elevated.enabled` | 总开关，必须为 `true` |
| `tools.elevated.allowFrom.<provider>: [senderIds]` | 按 **provider（渠道）→ 发送者列表**；渠道维度在 **key** 上 |
| `agents.entries.*.tools.elevated.enabled` | per-agent 门禁，**只能更严**；全局与 per-agent 必须都为 `true` |
| `agents.entries.*.tools.elevated.allowFrom` | per-agent 白名单，发送者需**同时**匹配全局 + per-agent |
| `/elevated on\|off\|ask\|full` | per-session 状态；行内指令仅影响单条消息 |

**allowFrom 条目前缀**（`tools/elevated.md:94-102`）：

| 前缀 | 匹配 |
|---|---|
| （无前缀） | Sender ID、E.164 或 From 字段 |
| `name:` | 发送者显示名 |
| `username:` | 发送者用户名 |
| `tag:` | 发送者 tag |
| `id:` / `from:` / `e164:` | 显式身份定向 |

> ⚠️ **v2 抄错表已更正**：原写 `channel:<channelId>:<senderId>` 前缀与 `"*"` 通配符 ——
> 那是 `toolsBySender` 的格式（`config-tools.md:172-174`）。`tools.elevated.allowFrom`
> **无** `channel:` 前缀、**无**通配符条目，渠道维度体现在 key 上。

另注（`tools/elevated.md:89`）：渠道插件可通过 SDK hook 提供 fallback allowlist，但
**目前无任何 bundled 渠道实现该 hook**，故实践中每个 provider 都需显式
`tools.elevated.allowFrom.<provider>` 条目。

提权 `exec` **绕过 sandbox**，走配置的 escape path（默认 `gateway`）。

### 实测教训：授权 ≠ 能力 ★

2026-08-23 删 root 属主 plist 时，Rex 口头授权 sudo 后**两条路都被挡**：

| 方式 | 失败 |
|---|---|
| `exec(elevated=true)` | `elevated is not available right now (runtime.direct). Failing gates: allowFrom` |
| `sudo -n` | `a password is required`（非交互 exec 无法输入密码） |

**`tools.elevated` 是配置层门禁，用户口头授权无法绕过。**

> 补充理解：该报错的 `runtime.direct` 本身就说明未沙箱化 —— 即 elevated 在本机
> 无论如何都不可用（no-op + 门禁双重挡）。但 `sudo` 仍需密码，与 elevated 无关。

正确做法（已写入技能 `macos-orphan-launchagent-cleanup`）：

1. 完成所有不需 sudo 的步骤（备份、检查、bootout）
2. 把确切命令交给用户手动执行
3. 用 `test -e` 验证结果

**不要为删一个小文件去改 `tools.*` 安全策略。**

### 治理规则

1. `tools.elevated.enabled` 保持**未配置/关闭**。开启需新增 ADR，说明具体场景与白名单范围
2. 若必须开，`allowFrom` **只列具体 senderId**（该字段本就无通配符条目）
3. WeCom 等外部渠道**永不列入** `allowFrom` —— 消息可伪造，提权不应受外部输入驱动
   - ⚠️ **注意**：sandbox=off 时这是**空条款**（它防的路径不存在）。真正需要防的
     「WeCom 消息驱动 host 上的 `exec`」由规则 5 覆盖
4. 需要提权的一次性操作 → 交用户终端执行，不改配置
5. **（新增）** 收紧外部渠道的 host exec 用 `tools.toolsBySender`；若将来开启 sandbox
   （`mode: "non-main"`），需重新评估本节全部结论 —— elevated 届时才真正成为门禁

## 5. 审计

```bash
bash scripts/tool_policy_audit.sh
```

六项检查：策略配置 / `allow`+`alsoAllow` 冲突 / 技能可用性 / `memory_search` 真实状态 /
媒体 provider / plugin 工具解锁状态。退出码 0=健康。

## 6. 监控点

- ⚠️ **OpenClaw 升级后重跑审计** —— `coding` profile 的包含列表可能变化（官方曾调整）
- ⚠️ 新增 plugin 后确认其工具是否需 `alsoAllow`（不要假设自动可用）
- ⚠️ `memory_search` 修好后，更新本文与审计脚本的期望值
- ⚠️ 若未来配置 channel，重新评估是否需要 `group:messaging`
- ⚠️ **`tools.elevated` 保持关闭** —— 任何开启请求需走 ADR，并确认 `allowFrom` 不含外部渠道与通配符
- ⚠️ **`plugins.allow` 不得为空** —— 空值时非内置插件可自动加载，包括已停用的（实测@2026-08-23 `doctor --lint` 报告）
- ⚠️ **`group:ui` 运行时常量漂移** —— 官方文档表格列 5 个工具，运行时仅含 `browser`/`canvas`；
  升级后重查 `dist/register-pGYK5dOd.js` 的 `POLICY_TOOL_GROUPS`（官方可能修文档或改实现）

## 7. 相关

- **ADR**: [ADR-202608-008](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md)
- **经验卡片**: `EXP-20260821-001`（Tavily `alsoAllow`）
- **官方文档**: `docs/gateway/config-tools.md`、`docs/concepts/memory-builtin.md`
- **同层组件**: 配置管理（ADR-007）、凭据管理（ADR-005）
