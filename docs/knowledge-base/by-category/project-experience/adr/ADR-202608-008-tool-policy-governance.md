---
type: adr
id: ADR-202608-008
date: 2026-08-22
title: L2 工具策略治理 — 「允许」与「可用」分离审计
status: accepted
supersedes: null
superseded_by: null
deciders: [Rex, Jerry]
layers: [L1, L2]
stage: manage
tags: [tools, policy, governance, least-privilege, silent-degradation, memory-search]
---

# [ADR-202608-008] L2 工具策略治理

## 1. 状态

**accepted** — 2026-08-22 · 审计机制已实现并验证；2 项待 Rex 定夺的修复见 §6

## 2. 背景

L2 建设的最后一个组件。架构文档 §5.4 原把工具策略问题定义为：

> **Issue 模式**：`tools.profile` 限制 + plugin 显式工具
> **预留位**：是否有其他 plugin 工具受同样影响？升级是否改变 coding profile 的 deny 列表？

**实测后发现这个定义不完整** —— 它只覆盖"授权边界"，漏掉了更危险的一类。

## 3. 核心决策

### 决策 1：工具治理必须区分三种状态，而非两种

`tools.profile` / `allow` / `deny` 只能表达"准不准用"。实测发现工具实际有三态：

| 状态 | 现有策略可表达 | 危险性 |
|---|---|---|
| `denied` | ✅ | 低 —— 明确失败，立刻发现 |
| `allowed-but-broken` | ❌ **不能** | **高 —— 静默失败** |
| `allowed-and-working` | ✅ | — |

**治理缺口是中间那层**：策略允许，但缺依赖/凭据/provider，于是静默降级或不出现。
不报错、不告警。

**决策**：审计必须同时回答"准不准用"和"能不能用"，两者分离检查。

### 决策 2：保持 `profile: "coding"`，新工具走 `alsoAllow` 逐个解锁

**决策**：不升级到 `full`。每个解锁项必须在 DESIGN.md 记录理由。

**理由**：最小权限。当前仅 `tavily_search` / `tavily_extract` 两项解锁，均有 EXP 背书。

**否决**：`profile: "full"`（省去逐个解锁的麻烦）。
**否决理由**：违反最小权限；且会掩盖"哪些工具真被需要"的信息。

### 决策 3：静默降级必须显式记录，不得假设标称能力

**决策**：文档与审计脚本必须标明能力的**真实状态**，而非配置声明的状态。

**触发案例**：`memory_search` 实测返回 `provider: "none"` +
`degradedTo: "keyword-only"`，因 OpenAI key 缺失。而系统级指令**强制要求**
先 `memory_search` 再回答记忆类问题 —— 指令假设了一个不存在的能力。

### 决策 4：不对未查清的机制下结论

**观察到的不对称**：
- Tavily 插件工具在 `coding` 下被 deny，需 `alsoAllow`（EXP-20260821-001 已验证）
- 但 `terminal` / `screen` / `dashboard` 属 `group:ui`，**不在官方 `coding` profile 列表内**，
  却实际可用且不在 `alsoAllow` 中

**决策**：记录现象，**不编造解释**。官方 profile 表不足以完整预测实际工具面。

**理由**：EXP-20260821-001 的教训就是 `contracts.tools` 与 `Capabilities` 是不同注册路径。
在没查源码前给出"可能是因为…"的推测，会污染知识库。**"未查清"是合法结论，"我猜"不是。**

---

#### ✅ 后续：机制已查清（2026-08-23 第三轮 review）

本决策的谨慎被证实是对的 —— 答案**必须读 dist 源码常量**，光看官方文档表格会得出错误结论。

| 项 | 真相 | 依据 |
|---|---|---|
| 运行时 `group:ui` | 仅 `["browser", "canvas"]` | `dist/register-pGYK5dOd.js:3928` |
| 官方文档 `group:ui` | 列 5 个：`browser`/`screen`/`terminal`/`canvas`/`show_widget` | `gateway/config-tools.md:41` |
| `terminal`/`screen` | **不被任何 `group:` 覆盖** ⇒ profile allowlist 不构成排除路径 ⇒ 天然可用 | 两表对比 |
| `dashboard` | **两版都不在 `group:ui`**，是 workboard 插件工具 | `plugins/manifest.md:165`、`web/dashboards.md:66` |

**两点修正**：
1. 本决策原文把 `dashboard` 归入 `group:ui` 是**事实错误**（它从未属于该组）。
2. 真因是**官方文档表格与运行时实现不一致** —— 属官方文档缺口，非本系统配置问题。

**新增方法论**：官方文档表格与运行时常量**都要查**，不一致时**以运行时为准**。
已入监控点：升级后重查 `POLICY_TOOL_GROUPS`。

## 4. 官方规则要点（一手来源：`docs/gateway/config-tools.md`）

| 规则 | 说明 |
|---|---|
| `allow` 与 `alsoAllow` 同 scope 互斥 | config 校验直接拒绝；用 `profile` + `alsoAllow` |
| **deny 优先于 allow** | — |
| `deny: ["write"]` **不**连带 deny `apply_patch` | 独立 tool id；禁全部写入须 deny `group:fs` |
| `allow: ["write"]` **会**连带启用 `apply_patch` | 不对称，易错 |
| `coding`/`messaging` 隐式允许 `bundle-mcp` | 已配置的 MCP server |

## 5. 实测发现

| # | 问题 | 严重性 | 证据 |
|---|---|---|---|
| A | 12 个技能允许但缺依赖 | 中 | `openclaw skills check` |
| B | **`memory_search` 静默降级为关键词匹配** | **高** | 工具返回 `provider:"none"`, `degradedTo:"keyword-only"` |
| C | 媒体工具在 profile 内但无 provider | 低 | 官方预期行为，非故障 |

**问题 A 的具体影响**：`AGENTS.md` 写着"如有 `sag` 就用语音讲故事"，但 `sag`
缺 `ELEVENLABS_API_KEY`，**当前不可用** —— 指令与环境不一致。

**问题 B 为何最严重**：
1. 系统指令强制要求先 `memory_search`
2. 它不报错，照常返回结果，只是从语义检索降级为关键词匹配
3. 中文记忆尤其吃亏：同义表述（"配置管理" vs "config 治理"）召回不到
4. `openclaw memory status --deep` 因缺 key 连 CLI 都启动不了

## 6. 待 Rex 定夺（涉及新依赖/凭据/成本，不自行决定）

### 修复 `memory_search`

| 选项 | 成本 | 备注 |
|---|---|---|
| **本地 GGUF**（推荐） | 一次性下载模型，**零 API 成本** | `openclaw plugins install @openclaw/llama-cpp-provider` + `memory.search.provider: "local"` |
| ARK `doubao-embedding-large` | 按量 ~¥0.0007/千 tok | **未实测** —— 配置中 key 是 SecretRef 占位符（`__OP...`），验证需取出真实凭据，**已主动放弃** |
| `OPENAI_API_KEY` | 新凭据 + 境外网络 | 官方默认 |
| 接受关键词模式 | 零 | 显式记录降级 |

**推荐本地 GGUF**：零成本、无数据外发、中文可用。属新增依赖，等拍板。

### 清理 12 个不可用技能

`openclaw doctor --fix` 会禁用它们。**属批量配置变更，先确认**。
好处：减少 catalog 噪音与误调用。

## 7. 后果

**正面**：
- 「允许但不可用」这类静默故障首次可见
- 一条命令审计工具策略健康度
- 官方规则要点成文，避免重复踩 `allow`/`alsoAllow` 互斥等坑

**负面 / 成本**：
- 审计依赖 `openclaw skills check` 等 CLI 输出格式，升级可能需适配
- 未查清的 `group:ui` 机制留作开放问题

**风险与缓解**：

| 风险 | 缓解 |
|---|---|
| OpenClaw 升级改变 `coding` profile 包含列表 | 升级后重跑审计；DESIGN.md 记录了当前官方表 |
| 新 plugin 工具默认 deny 而未察觉 | 审计输出提示用 `plugins inspect` 确认 |
| `memory_search` 修好后文档过期 | 已列入监控点 |

## 8. 验证

```bash
bash scripts/tool_policy_audit.sh   # 六项检查，退出码 0=健康
```

**实测通过**：
- ✅ 六项检查全部输出正确
- ✅ 技能数 12 与 `openclaw skills check` 完全一致
- ✅ `alsoAllow` 正确识别 2 项解锁
- ✅ 退出码 1 准确反映"存在 2 类未解决问题"（非误报）

**开发中修掉的 3 个自身 bug**（值得记录，属可复用教训）：
1. **heredoc 吃 stdin**：`printf '%s' "$X" | python3 - <<'PY'` 中 `<<'PY'`
   覆盖了管道 stdin，导致 `json.load(sys.stdin)` 读到脚本自身。
   **改用临时文件 + `sys.argv[1]`**。
2. **技能解析误报 50 个**（真实 12 个）：`grep -E '^\s+\S+\s'` 把
   `Eligible: ...` 等说明行和可用技能都算进 missing。
   **改为只匹配含 `(anyBins|bins|env|config):` 的依赖说明行**。
3. **`alsoAllow` 显示为空**：同 bug 1 的连带症状。

## 9. 相关

- **设计**: [components/tool-policy/DESIGN.md](../../../../architecture/components/tool-policy/DESIGN.md)
- **经验卡片**: `EXP-20260821-001`（Tavily `alsoAllow` 解锁）
- **官方文档**: `docs/gateway/config-tools.md`、`docs/concepts/memory-builtin.md`
- **同层 ADR**: 004 可观测性 · 005 凭据 · 006 持久化 · 007 配置管理
- **架构**: `00-system-architecture.md` §3.2 / §5.4

## 10. 变更历史

- 2026-08-22: 创建并 accepted（审计机制实现；2 项修复待定夺）
