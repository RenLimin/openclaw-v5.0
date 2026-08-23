---
type: experience
id: EXP-20260821-003
date: 2026-08-21
title: 跨模型会话溢出死锁 — 用 compaction.model 委托大 ctx 模型解压
layers: [L1]                    # OpenClaw 系统层：会话/上下文管理契约
stage: manage
severity: high                 # 会导致会话完全不可用，需 /reset 才能恢复
category: correct
tags: [openclaw, compaction, context-window, model-switch, ark-code-latest, longcat]
status: active
supersedes: null
superseded_by: null
---

# [EXP-20260821-003] 跨模型切换导致的 compaction 死锁与修复

## 1. 背景

单一 webchat 会话中在两个 provider 间切换模型：

| 模型 | OpenClaw 认定 ctx | 备注 |
|---|---|---|
| `longcat/LongCat-2.0` | 1049k | 配置中显式声明 `contextWindow: 1048576` |
| `coding-plan/ark-code-latest` | **200k** | 配置中**未声明** `contextWindow`，走默认值 |

**环境**：OpenClaw 2026.7.2-beta.7，`agents.defaults.compaction.mode = "safeguard"`。

## 2. 问题

**症状**（LongCat 下正常，切到 coding-plan 后）：
- 正常对话无法进行（上下文已满）
- `/compact` **同样失败**
- `/status` 显示 `📚 Context: 287k/200k (143%)`

**根因（死锁机制）**：
1. 会话在 LongCat（1049k ctx）下累积到 ~252k tokens — 完全合法
2. 切到 `ark-code-latest`（200k ctx）后，历史 context **超出新模型上限 43%**
3. `/compact` 的摘要请求**本身要用当前会话模型**（默认行为：`compaction` 使用 agent primary model）
4. 该模型已无法接收超限 prompt → 摘要请求失败 → **无法压缩，也无法对话**

关键点：**compaction 不是免费的逃生舱**。它需要一次成功的模型调用，而调用用的正是那个已经溢出的模型。

**次生问题（我自己的错误）**：初次排查时反复查 LongCat 的 context window，方向完全错了 — 出问题的是**目标模型**的容量，不是源模型。

## 3. 方案

### 3.1 应急恢复（会话已死锁时）

三条路，按侵入性排序：

| 方案 | 操作 | 代价 |
|---|---|---|
| A | 切回大 ctx 模型 → `/compact` → 再切回小 ctx 模型 | 保留摘要，最优 |
| B | `/reset` | 丢弃活跃 context（transcript 仍在磁盘） |
| C | `/new` | 开新会话 |

实际采用：**B (`/reset`)** — A 方案在本次已错过时机。

### 3.2 结构性修复（防复发）

把 compaction 的摘要工作**委托给大 ctx 模型**，与会话模型解耦：

```json5
// ~/.openclaw/openclaw.json
{
  agents: {
    defaults: {
      compaction: {
        model: "longcat/LongCat-2.0",        // 摘要用 1049k ctx 模型
        memoryFlush: {
          model: "longcat/LongCat-2.0",      // pre-compaction 记忆落盘同理
        },
        notifyUser: true,                     // 压缩时可见，不再静默失败
      },
    },
  },
}
```

**命令**：
```bash
cat > /tmp/compaction.patch.json5 <<'EOF'
{ agents: { defaults: { compaction: {
  model: "longcat/LongCat-2.0",
  memoryFlush: { model: "longcat/LongCat-2.0" },
  notifyUser: true,
} } } }
EOF
openclaw config patch --file /tmp/compaction.patch.json5 --dry-run
openclaw config patch --file /tmp/compaction.patch.json5
```

### 3.3 contextWindow 校准（2026-08-21 更新）

**已验证并调整**（之前"保持 200k 不动"的结论已过时）：

通过 `arkcli models search/get` + 官方文档，确认了 Coding Plan 各模型的真实 context window：

| 模型 | 调整前 | 调整后 | 来源 |
|---|---|---|---|
| `glm-5.3` | 200,000 (默认) | **1,048,576** (1M) | 官方文档明确 1M ctx |
| `kimi-k2.7-code` | 200,000 (默认) | **262,144** (262k) | HuggingFace/官方 262k |
| `minimax-m3` | 200,000 (默认) | **1,048,576** (1M) | MiniMax 官方 1M |
| `ark-code-latest` | 200,000 (默认) | **262,144** (262k) | Auto 池最小值 (kimi/doubao) |

**`ark-code-latest` 的 Auto 池分析**（来源：`arkcli plans model-list`）：
- doubao-seed-2-1-turbo → 262k
- doubao-seed-2.0-lite → 262k
- glm-5.3 → 1M
- deepseek-v4-flash → 1M
- glm-5.2 → 1M
- kimi-k2.7-code → 262k
- minimax-m3 → 1M
- deepseek-v4-pro → 1M
- **池最小值 = 262k** → 这是 `ark-code-latest` 的安全上界

**关键认知修正**：
- 之前认为 200k 是正确下界 → 实际上 OpenClaw 默认 200k 只是 fallback，火山官方模型 ctx 都 ≥262k
- `ark-code-latest` 设 262k（而非 200k）更精确，但仍保守安全
- 如果未来 Auto 池加入 <262k 模型，需再次下调

## 4. 验证

```bash
openclaw config get agents.defaults.compaction
# → { model: "longcat/LongCat-2.0", memoryFlush: {...}, notifyUser: true, mode: "safeguard" }
openclaw config validate
# → Config valid
```

- ✅ `Applied 3 config update(s). No gateway restart needed.` — 热生效
- ✅ 备份链完好：`openclaw.json.bak{,.1..4}` + `.last-good`
- ⏳ **待验证**：下次真实触发 compaction 时确认摘要由 LongCat 执行（看 `notifyUser` 提示 + gateway 日志 `embedded run auto-compaction start`）

## 5. 教训

**规则**（可推广）：
1. **compaction 模型应始终指向全局最大 ctx 模型**，与会话模型解耦。这是跨模型切换环境的必要配置，不是优化项。
2. **切换到更小 ctx 的模型前先 `/compact`**。切模型不是免费操作 — 先压缩，再切。
3. **排查溢出时看目标模型容量，不是源模型**。`/status` 的 `Context: A/B` 中 B 是**当前**模型的上限。
4. **`contextWindow` 必须按真实下界声明**。Auto/路由类模型 ID（如 `ark-code-latest`）取其可能路由到的**最小**模型容量，不能取最大。
5. `memoryFlush.model` 要一起改 — 它是 pre-compaction 的记忆落盘turn，同样会被溢出模型卡死。

**监控点**：
- ⚠️ LongCat provider 失效/key 过期 → compaction 整体失效（单点依赖）。届时把 `compaction.model` 切到 `coding-plan/deepseek-v4-flash`（1049k）作为备选。
- ⚠️ OpenClaw 升级后确认 `compaction.model` 仍接受 `provider/model-id` 字符串形式。
- ⚠️ 若火山方舟调整 Coding Plan 的 Auto 池（加入 <200k 模型），需下调 `ark-code-latest` 的假定 ctx。

**升级判断**：
- [x] 涉及 L1 契约（OpenClaw 会话/上下文管理）
- [ ] 影响 ≥2 层
- [ ] 多模块对齐
- **决定**：保持经验卡片。本卡是"配置方法 + 故障恢复手册"，非架构决策。若未来演进为"多模型路由策略"（哪个模型干什么活的系统性分工），再升级为 ADR。

## 6. 相关

- **OpenClaw 文档**：`docs/concepts/compaction.md`（`### Using a different model` 节）
- **深度参考**：`docs/reference/session-management-compaction.md`（overflow recovery 错误模式、reserve 机制）
- **配置**：`~/.openclaw/openclaw.json` → `agents.defaults.compaction`
- **相关卡片**：`EXP-20260821-001`（同样是 `config patch --dry-run` 优先的操作范式）

## 7. 变更历史

- 2026-08-21: 创建（含死锁机制分析、被否决方案、监控点）
- 2026-08-21: **决策撤销** — 取消摘要委托，改为各模型自行处理自身上下文溢出
  - 原因: 死锁根源是 contextWindow 误设为 200k 默认值，现已校准至官方值（≥262k）
  - 所有模型自身 ctx 均 ≥262k，足以执行摘要操作，无需外部兜底
  - 原则: 模型自治，不引入跨模型依赖

- 2026-08-22: **§3.3 数值被实测推翻**，标记为过时，新结论见 `EXP-20260822-004`
  - `minimax-m3` 真值 1,048,576（不是 512,000 — 引用的第三方 issue 测的是直连 API）
  - `ark-code-latest` 真值 229,376 / 224k（不是 262,144 — 忽略了 max_input < context_window）
  - 方法论修正：容量声明只信实测，不信文档推断
