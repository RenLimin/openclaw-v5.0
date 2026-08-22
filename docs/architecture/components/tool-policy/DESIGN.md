---
type: design
component: tool-policy
layer: L2
status: active
date: 2026-08-22
owner: Rex + Jerry
---

# L2 工具策略治理 — 设计

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

### 2.3 待查清的不对称现象

| 观察 | 说明 |
|---|---|
| Tavily 插件工具在 `coding` 下**被 deny**，需 `alsoAllow` 显式解锁（EXP-20260821-001） | 已验证 |
| 但 `terminal` / `screen` / `dashboard` 属 `group:ui`，**不在 `coding` profile 列表内**，却实际可用且未出现在 `alsoAllow` | ⚠️ **机制未查清** |

**诚实结论**：官方 profile 表**不足以完整预测实际工具面**。可能原因（均未验证）：
plugin 工具走独立注册路径 / 文档表格不完整 / 运行时 surface 另有补充规则。

**不下结论，只记录现象**。需要时用 `openclaw plugins inspect` + 源码确认。
这正是 EXP-20260821-001 的教训：`contracts.tools` 与 `Capabilities` 是不同注册路径。

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

## 7. 相关

- **ADR**: [ADR-202608-008](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-008-tool-policy-governance.md)
- **经验卡片**: `EXP-20260821-001`（Tavily `alsoAllow`）
- **官方文档**: `docs/gateway/config-tools.md`、`docs/concepts/memory-builtin.md`
- **同层组件**: 配置管理（ADR-007）、凭据管理（ADR-005）
