---
type: experience
id: EXP-20260824-011
date: 2026-08-24
title: 平台目录 ≠ 当前套餐权限 — 邻近信息源代替权威源的第三次同源错误
category: correct
layers: [L1, L2]
stage: manage
status: active
tags: [evidence, methodology, entitlement, embedding, volcengine, memory-search, false-memory]
related: [ADR-202608-009, EXP-20260823-009, EXP-20260823-010]
---

# 平台目录 ≠ 当前套餐权限

## 1. 背景

修复上下文压缩失效时，需确认火山 embedding 能否替代本地 llama-cpp。
连续两轮得出「Coding Plan 不含 embedding，需单独开通付费」的结论，**全部是错的**。

这是 EXP-009（选择性引用官方文档）、EXP-010（用启发式代替证据）之后
**同一病灶的第三次形态**。

## 2. 错误经过

### 我用的证据

```bash
arkcli models search embedding
# → doubao-embedding-vision  (primary_version: 251215)
# → doubao-embedding-large   (primary_version: text-250515)
# → doubao-embedding         (primary_version: text-240715)
```

据此推断「文本向量模型可用」，依次实测 4 个 ID：

| 尝试的 model ID | 结果 |
|---|---|
| `doubao-embedding-large` | `InvalidEndpointOrModel.NotFound` |
| `doubao-embedding` | 同上 |
| `doubao-embedding-large-text-250515` | 同上 |
| `doubao-embedding-text-240715` | 同上 |

**得出的结论**（写进了 `MEMORY.md`）：

> 火山 embedding 实测不可用：模型未开通、Coding Plan 不含 embedding，需单独开通+计费

### 真相

Rex 提供套餐专属权益文档（`/docs/82379/2279748` 记忆增强-Embedding模型）后：

> 支持的 Embedding 模型：**doubao-embedding-vision**（对应模型 `doubao-embedding-vision-251215`）
> 专属 Base URL（兼容 OpenAI 接口协议）
> Embedding 模型与其他模型一致，**均会消耗套餐额度**，按模型调用次数进行估算

- Coding Plan **本身就含** embedding
- **无需单独开通、无额外计费**（消耗套餐额度）
- 唯一可用模型是 vision 那个（它同时支持纯文本输入）
- 我试的 4 个里**没有一个是它**

实测确认可用：

```
POST /api/coding/v3/embeddings   model=doubao-embedding-vision-251215
→ OK dims=2048
```

语义有效性自测（余弦相似度）：

| 对比 | 相似度 |
|---|---|
| 「密钥泄露到开源仓库」vs「凭据不要写进 markdown」 | **0.5273** |
| 同上 vs「今天天气很好适合散步」 | **0.1829** |

## 3. 根因

**拿一个「邻近但不等价」的信息源代替真正的权威源，且未验证等价性。**

| 我查的 | 它实际回答的问题 | 我以为它回答的问题 |
|---|---|---|
| `arkcli models search` | 平台**全量目录**里有哪些模型 | **我当前套餐**能调哪些模型 |

目录是「平台卖什么」，权益文档是「我买到了什么」。两者**结构相似、语义不同**。

### 与前两次的同构关系

| 卡片 | 形态 | 共同点 |
|---|---|---|
| EXP-009 | 读官方文档读到支持自己的那句就停 | 用**部分证据**代替完整证据 |
| EXP-010 | 「我打算做」「长度像凭据」「dry-run 通过」当成事实 | 用**启发式**代替证据 |
| EXP-011（本卡） | 全量目录当权限清单 | 用**邻近信息源**代替权威源 |

三者都是**在证据链上抄近路**，且都**没有验证替代品与目标的等价性**。

## 4. 次生危害：假记忆

错误结论进了 `MEMORY.md`（长期记忆，主会话每次加载）：

> 需单独开通+计费

这比技术隐患更严重 —— **技术隐患可以再修，假事实会污染后续所有决策**。
若不纠正，未来任何「要不要用火山 embedding」的讨论都会基于「要额外花钱」这个假前提。

已就地标注证伪（保留原文 + `~~删除线~~` + 纠正说明），而非删除 —— 保留错误痕迹供审计。

## 5. 正确做法

**查「我能用什么」时，权威源是权益/套餐文档，不是产品目录。**

| 问题 | 正确的源 |
|---|---|
| 平台有哪些模型 | `arkcli models search` / 模型广场 |
| **我的套餐能调哪些** | **该套餐的专属权益文档** |
| 计费方式 | 套餐计费说明（可能「消耗额度」而非「额外付费」） |

### 通用规则

1. **区分「目录」与「权限」**：任何 `list`/`search`/`catalog` 类接口返回的是**可能性**，不是**授权**
2. **多个 ID 连续 NotFound 是信号**：不是「没开通」，先怀疑**ID 形态或可用集合搞错了**
   —— 4 个全挂而端点本身能通（返回业务错误而非网络错误），说明**认证没问题、模型集合错了**
3. **写进 MEMORY.md 前问一句**：这个结论的权威源是什么？如果是推断，标注「推断」而非事实
4. **被证伪后立即就地纠正**，标注而非删除

## 6. 真正的阻塞（与本卡主题无关但需记录）

模型可用 ≠ 能接入。火山 embedding 最终仍未启用，原因完全在别处：

```
HTTP 400 InvalidParameter: Embeddings API input limit exceeded: max 10, got 81
```

源码求证（dist）：

| 位置 | 事实 |
|---|---|
| `embedding-provider-DQt_MtNJ.js:24-58` | openai-compatible 的 `embedBatch` 把整个数组**原样透传**，无分片 |
| `manager-DSpvP_Or.js:3470-3506` | 有 `runMemoryEmbeddingBatchRetryWithSplit` 自动二分机制 |
| `manager-DSpvP_Or.js:864` | **但** split 只认 `SPLITTABLE_…TRANSPORT_ERROR_RE`：仅 ECONNRESET/EPIPE/socket hang up 等**传输层**错误 |
| — | **HTTP 400 不匹配 ⇒ 不分片，直接抛** |
| 全局 grep | **无任何** `batchSize`/`maxInputsPerRequest` 配项（`reference/memory-config.md:442-449` 只有 `nonBatchConcurrency` / `batch.enabled`，后者仅支持 gemini/openai/voyage） |

⇒ 无配置可解。**Rex 拍板保持本地 llama-cpp 为主**（无成本损失：套餐内权益，不用不产生开销）。

## 7. 验证

回退后实测：

- `memory index --force` → 成功
- `provider: local` / **406 chunks** / Embeddings ready / dims=768
- 实查「如何避免把密钥泄露到开源代码仓库」→ `USER.md#L103`
  textScore=**0** / vectorScore=**0.691**（纯向量召回）
- 配置快照 `git diff` **为空** ⇒ 回退是字节级精确的

## 8. 关联

- [ADR-202608-009](../adr/ADR-202608-009-memory-embedding-provider.md) — 本地 embedding provider 决策
- [EXP-20260823-009](./EXP-20260823-009-review-selective-citation-and-drift-taxonomy.md) — 选择性引用
- [EXP-20260823-010](./EXP-20260823-010-heuristics-instead-of-evidence.md) — 启发式代替证据
