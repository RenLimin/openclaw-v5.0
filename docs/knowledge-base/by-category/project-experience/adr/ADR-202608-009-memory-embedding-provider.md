---
type: adr
id: ADR-202608-009
date: 2026-08-22
title: L2 记忆语义检索 — 本地 GGUF embedding 为主 provider
status: accepted
supersedes: null
superseded_by: null
deciders: [Rex, Jerry]
layers: [L1, L2]
stage: design
tags: [memory, embedding, semantic-search, local-model, privacy, fail-closed]
related: [ADR-202608-008, ADR-202608-005, EXP-20260821-001]
---

# [ADR-202608-009] L2 记忆语义检索 — 本地 GGUF embedding

## 1. 状态

**accepted** — 2026-08-22 · Rex 明确授权（1. 安装本地 GGUF  2. 读官方文档，需要时自动启用火山 embedding）

## 2. 背景

ADR-008 实测发现 `memory_search` 静默降级：

```json
{"provider": "none",
 "embeddingBootstrap": {"ok": false, "provider": "openai",
   "reason": "No API key found for provider \"openai\"",
   "degradedTo": "keyword-only"}}
```

系统级指令**强制**要求回答记忆类问题前先调 `memory_search`。它不报错，
只是从语义检索降级为关键词匹配 —— 中文同义表述召回不到。
这是 ADR-008 三态模型里 `allowed-but-broken` 的典型案例。

## 3. 核心决策

### 决策 1：本地 GGUF 作为**主** provider，不是兜底

```json5
{ memory: { search: { provider: "local", fallback: "none" } } }
```

**依据**（官方 `reference/memory-config.md`）：

> Explicit non-local providers fail closed. If you set `memory.search.provider`
> to a concrete remote-backed provider … and that provider is unavailable at
> runtime, `memory_search` returns an unavailable result instead of silently
> using FTS-only recall.

| provider 设置 | 不可用时行为 |
|---|---|
| 未设置 / `auto` / `none` | 可退化为 FTS 词法检索 |
| **显式远程**（openai/gemini/ollama/openai-compatible…） | **fail closed** |
| `local` | ⚠️ **同样可静默退化为 keyword-only**（见 §3.1 修正） |

**这条否决了「远程为主 + 本地兜底」的直觉方案**：
- ❌ `provider: <远程>` + `fallback: local` —— 远程挂了**先 fail closed**，
  比现在"降级但能用"更糟
- ✅ `provider: local` —— 无网络依赖、无 API 成本、无数据外发（**但不等于不会降级**）

**否决 Ollama**：本机未安装 ollama（虽有 plugin），且它属"显式远程 provider"，
同样 fail closed。

### 3.1 ⚠️ 修正（2026-08-23 全盘 review）：`local` 也会静默降级

**本 ADR 原写「`provider: local` 不存在不可用」，该论证错误。**

官方 `concepts/memory-search.md:118-121` 原文：

> **FTS-only mode.** Set `provider: "none"` to intentionally disable embeddings
> and search with keywords only. Leaving `provider` unset or set to `"auto"`
> falls back to keyword-only ranking when embedding setup or a request fails,
> **as does `provider: "local"` (the GGUF/llama.cpp provider)**.

即 `local` 与 `auto`/未设置**属于同一类**：embedding 初始化或单次请求失败时
**静默退回 keyword-only**，不报错、不 fail closed。

**真实结论**：选 `local` 并未消除静默降级风险，只是把触发条件从

| 原触发条件（远程） | 新触发条件（local） |
|---|---|
| 缺 API key / 网络故障 / 额度耗尽 | 模型文件被移动或改名 / 插件失效 / GGUF 加载失败 / llama.cpp 二进制损坏 |

换成了另一组。**风险形状变了，风险没消失。**

这恰好放大了 §7.1 两个坑的危害 —— 改文件名或设 `modelPath` 不仅让索引身份不匹配，
还会**静默退回关键词检索**，而系统指令强制每次记忆查询都调 `memory_search`。

**因此本 ADR 新增决策 4（监控），见下。**

### 决策 4：必须监控 provider 实际值，不能假设配置生效

`memory_search` 返回体里有 `provider` 字段与 `debug.embeddingBootstrap`。
**断言 `provider === "local"` 且 `vectorScore` 非零**才算语义检索在工作。

```bash
# 快速断言（返回 provider 与首条 vectorScore）
openclaw memory status --agent main | grep -E 'Provider|Vector dims'
```

判据：

| 观察 | 含义 |
|---|---|
| `provider: local` + `vectorScore > 0` | ✅ 语义检索正常 |
| `provider: local` + 全部 `vectorScore: 0` | ⚠️ 已静默降级为 keyword-only |
| `debug.embeddingBootstrap.degradedTo` 存在 | ❌ 明确降级，读 `reason` |

**实测@2026-08-23**：查「密钥泄露到开源仓库」→ `provider: local`，
`vectorScore` 0.742 / 0.629 / 0.642 均非零，`USER.md#L103` 的 `textScore: 0` —— 纯向量召回，正常。

**教训（方法论）**：本 ADR 的原始论证是**选择性引用**的产物 —— 读到
「Explicit non-local providers fail closed」这句正好支持已选方案，就停止检索，
把"远程会 fail closed"推断成"local 不会降级"。而官方在**同一份文档另一段**
明确否定了这个推断。

→ **引用官方文档作为决策依据时，必须读完相关章节全文，不能引到支持自己的那句就停。**

### 决策 2：火山 embedding 不设为主 provider（即使开通）

Rex 要求"需要时自动启用火山 embedding"。**已实测，当前不可用**，且即使开通也不建议做主 provider：

1. **fail closed** —— 网络抖动/额度耗尽 → `memory_search` 直接 unavailable，
   而系统指令强制每次记忆查询都调它
2. **数据外发** —— 记忆含 `MEMORY.md`/`USER.md`/日常日志，
   每次检索把 query 发第三方，与 SOUL.md「不外发私有数据」冲突
3. **索引重建** —— 切 provider 会使 SQLite 向量索引失效

**保留作为未来选项**：若出现本地召回不足的**实测证据**（非猜测），
可用 `openai-compatible` 指向 `/api/v3`，或作离线批量重建索引的一次性工具。

### 决策 3：不自行修改 `~/.zshenv`

发现该文件有真实 bug（见 §5），但它含凭据且属 Rex 个人环境配置。
**给出验证过的修复方案，由 Rex 执行**，不代改。

## 4. 火山引擎 embedding 实测（一手证据）

用 `/api/v3` 与 `/api/coding/v3` 两个端点、3 个模型交叉测试：

| 端点 | 错误码 | 含义 |
|---|---|---|
| `/api/v3/embeddings` | `404 InvalidEndpointOrModel.NotFound` | 鉴权通过，**模型未开通** |
| `/api/coding/v3/embeddings` | `404 UnsupportedModel` | **Coding Plan 端点不提供 embedding** |

**两个错误码不同，信息量很大**：

- `coding/v3` 明确回 "does not support the coding plan feature"
  → 现有 Coding Plan 订阅**不覆盖** embedding，必须走标准 `/api/v3` 且**单独计费**
- `v3` 回 `NotFound` 而非 `Unauthorized`
  → key 有效，缺的是控制台**开通管理 → 向量模型**的开通动作

**候选模型**（LiteLLM 文档 + arkcli models search）：

| 模型 | 维度 |
|---|---|
| `doubao-embedding-large` | 2048 |
| `doubao-embedding-large-text-250515` | 2048（large 的 primary_version）|
| `doubao-embedding` | 2560 |
| `doubao-embedding-vision-251215` | 1024/2048（多模态，文本场景无必要）|

**定价**：文本输入 ~¥0.0007/千 tokens（官方模型卡）。

## 5. 附带发现：`~/.zshenv` 三个 key 全部未生效 ★

Rex 已预先配置 embedding 相关环境变量，但**全部没生效**：

```
export VOLCENGINE-EMBEDDING_API_KEY=...   ← 变量名含连字符，非法
export VOLCENGINE_API_KEY=...
export ARK_API_KEY=...
```

**根因**：shell 变量名不允许连字符。第 1 行 `export` 报
`not valid in this context` 并**中断整个文件的执行** —— 第 2、3 行也不会运行。

**实测证据**：
```
$ zsh -lc 'echo ${VOLCENGINE_API_KEY:-未设置}'
/Users/bangcle/.zshenv:export:1: not valid in this context: VOLCENGINE-EMBEDDING_API_KEY
未设置
```

**修复**（已在副本验证，待 Rex 执行）：把连字符改为下划线

```bash
sed -i '' 's/^export VOLCENGINE-EMBEDDING_API_KEY=/export VOLCENGINE_EMBEDDING_API_KEY=/' ~/.zshenv
```

改后三个变量全部正常加载（实测 len=46 均已加载）。

**另一发现**：三个变量值**完全相同**，都是 Coding Plan key
（`ark-c8c6...`，与 `models.providers.coding-plan.apiKey` 一致）。
所以即使修好 shell 语法，也仍然过不了 embedding —— 因为模型未开通，
且 Coding Plan 端点不支持 embedding。

> **教训**：环境变量"已写进 rc 文件" ≠ "已生效"。与 ADR-007 P2
> 「Applied ≠ 生效」同一类错误 —— 必须读回验证。

## 6. 后果

**正面**：
- 语义检索恢复，中文同义召回改善
- 零 API 成本、零数据外发
- 无网络依赖 → 不会 fail closed
- 顺带发现并诊断了 `~/.zshenv` 的静默失效

**负面 / 成本**：
- 插件占磁盘约 1.3 GB + 模型 313 MB（保留两个文件名副本则 626 MB）
- 中国大陆网络需手动经镜像预置模型（见 §7.1 坑 1）
- 本地 300m 模型效果理论上弱于云端大模型 —— 但实测中文语义召回已可用（§7）

**风险与缓解**：

| 风险 | 缓解 |
|---|---|
| 本地模型中文召回不足 | 已实测中文语义召回有效（§7）；持续抽查，确认不足再评估云端 |
| HuggingFace 不可达致 worker 挂起 | 模型已本地预置；文件名与缓存目录不可改（§7.1） |
| 换 provider/model 使索引失效 | `openclaw memory index --force`；官方会报 index identity warning 而非静默 |
| 磁盘占用 | 已记录到监控点 |
| **`local` 静默降级为 keyword-only** ★ | **决策 4 的 provider 断言**（§3.1）；模型文件名/路径变更后必须复验 |

## 7. 验证（已完成，实测通过）

```
Provider: local (requested: local)
Model: hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf
Indexed: 16/11 files · 557 chunks · Vector dims: 768
Embedding cache: 1078 entries · scripts=25 latin, 26 cjk, 182 mixed
```

**语义能力决定性证据**：查询「如何避免把密钥泄露到开源代码仓库」

| 命中 | `textScore` | `vectorScore` | 记忆实际写的 |
|---|---|---|---|
| `USER.md#L103` | **0** | 0.691 | 「Never 把凭据/API key 写到任何 markdown 文件」|
| `MEMORY.md#L73` | **0** | 0.595 | 「Tavily 和 GitHub 已有不一致的凭据管理方式」|

`textScore: 0` = **关键词检索完全无法命中**，纯向量语义召回。
查询用「密钥/开源仓库」，记忆写「凭据/API key/markdown」—— 修复前这类查询必然漏召。

## 7.1 实施中踩的两个坑（值得记录）

### 坑 1：HuggingFace 不可达导致 worker 静默挂起

`huggingface.co` 实测 `HTTP 000`（20s 超时）。自动下载不报错、不超时退出，
而是 **worker 无限挂起**：CPU 0.5%、零网络连接、零输出。
表现像"正在工作"，实际永远不会完成。

**解**：`hf-mirror.com` 可用（HTTP 200 / 1.5s / ~6 MB/s），手动预置模型。

### 坑 2：设 `local.modelPath` 绝对路径 → 索引身份永久不匹配 ★

直觉做法（下载后指向绝对路径）会造成**CLI 与 gateway 各说各话**：

```
error: index was built for model /Users/.../embeddinggemma-300m-qat-Q8_0.gguf,
       expected hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/...
```

CLI 按配置的绝对路径给索引打标签，运行中的 gateway 期望默认 `hf:` 标识 ——
两者永不相等，`memory_search` 一直 unavailable，反复 `index --force` 也没用。

**正解**（读插件源码 `dist/index.js` L25-27 才确认）：

| 事实 | 值 |
|---|---|
| 默认缓存目录 | `~/.node-llama-cpp/models` |
| **插件期望的文件名** | `hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf` |
| `hf:`/`http(s):` 前缀的 modelPath | 不做本地 resolve（L27 正则） |

把模型放默认目录、用 `hf_ggml-org_` 前缀命名、**不配** `modelPath` ——
插件命中缓存跳过下载，索引身份与 gateway 一致。

**教训**：配置项的"直觉用法"可能与实现假设冲突。
遇到身份/标识类不匹配，**读源码比试参数快** —— 我试了 3 轮 `index --force` 都没用，
读源码 2 分钟就定位了文件名规则。

## 8. 相关

- **设计**: [components/memory-embedding/DESIGN.md](../../../../architecture/components/memory-embedding/DESIGN.md)
- **ADR-008**: 工具策略治理 —— 本问题是 `allowed-but-broken` 实例
- **ADR-007**: 配置管理 —— §5 与「Applied ≠ 生效」同类教训
- **官方文档**: `concepts/memory-builtin.md` · `reference/memory-config.md`

## 9. 变更历史

- 2026-08-22: 创建并 accepted；实施完成并实测验证（含 §7.1 两个坑的记录）
- 2026-08-23: **§3.1 核心论证修正** —— 原写「`provider: local` 不存在不可用」，
  经官方 `concepts/memory-search.md:118-121` 核实**错误**：`local` 与 `auto` 同类，
  同样静默退化为 keyword-only。新增决策 4（provider 实际值监控）+ 风险表新增一行。
  根因是选择性引用官方文档（只读支持已选方案的那句）。决策结论（选 local）不变 ——
  零成本/零外发/无网络依赖仍成立 —— 但**理由中「不会降级」一条作废**。
