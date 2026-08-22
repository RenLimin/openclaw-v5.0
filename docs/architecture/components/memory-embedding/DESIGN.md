---
type: design
component: memory-embedding
layer: L2
status: active
date: 2026-08-22
owner: Rex + Jerry
---

# L2 记忆语义检索 — embedding provider 设计

> **ADR**: [ADR-202608-009](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-009-memory-embedding-provider.md)
> **Rex 授权**: 2026-08-22 — 1) 安装本地 GGUF  2) 读官方文档，需要时自动启用火山 embedding
> **官方文档**: `docs/concepts/memory-builtin.md` · `docs/reference/memory-config.md`

## 1. 问题

`memory_search` 静默降级为 keyword-only：

```json
{"provider": "none",
 "embeddingBootstrap": {"ok": false, "provider": "openai",
   "reason": "No API key found for provider \"openai\"",
   "degradedTo": "keyword-only"}}
```

**为什么必须修**：系统级指令强制要求回答记忆类问题前先调 `memory_search`。
它不报错，只是召回变差 —— 中文同义表述（"配置管理" vs "config 治理"）检索不到。
这是 ADR-008 定义的 `allowed-but-broken` 状态的典型案例。

## 2. 关键机制：fallback 语义（决定架构的核心事实）

官方文档 `reference/memory-config.md` §Provider selection 明确区分两种行为：

| provider 设置 | 不可用时的行为 |
|---|---|
| 未设置 / `"auto"`（legacy）/ `"none"` | **可退化**为 FTS 词法检索 |
| **显式远程 provider**（openai / gemini / ollama / openai-compatible…） | **fail closed** —— `memory_search` 返回 unavailable，**不静默退化** |
| `"local"` | 本地模型，不依赖网络 |

> Explicit non-local providers fail closed. If you set `memory.search.provider` to
> a concrete remote-backed provider … and that provider is unavailable at runtime,
> `memory_search` returns an unavailable result instead of silently using FTS-only recall.

**这条直接否决了「远程为主 + 本地兜底」的直觉方案**：

- ❌ `provider: "<远程>"` + `fallback: "local"` —— 远程挂了先 fail closed，
  比现在的"降级但能用"更糟（现在至少有关键词检索）
- ✅ `provider: "local"` + `fallback: "none"` —— 本地无网络依赖，不存在"不可用"

**结论：本地必须是主 provider，不是兜底。**

## 3. 方案：本地 GGUF 为主

```json5
{
  memory: {
    search: {
      provider: "local",
      fallback: "none",
      // local 留空 → 用默认模型标识 hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/...
      // ⚠️ 关键：**不要**设 local.modelPath 指向绝对路径（见 §3.1）
      // local.contextSize 默认 4096，覆盖典型 chunk（128~512 tokens）
    },
  },
}
```

### 3.1 ⚠️ 中国大陆网络：必须手动预置模型，但**不能**改 modelPath

**问题**：`huggingface.co` 在本网络不可达（实测 `HTTP 000` 20s 超时），
自动下载会让 embedding worker **无限挂起**（CPU 0.5%、无网络连接、无输出、无报错）。

**踩过的坑**：直觉做法是下载模型后设 `local.modelPath` 指向绝对路径。
**这会导致索引身份永久不匹配**：

```
error: index was built for model /Users/.../embeddinggemma-300m-qat-Q8_0.gguf,
       expected hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf
```

CLI 用配置里的绝对路径给索引打标签，而运行中的 gateway 期望默认的 `hf:` 标识，
两边永远对不上，`memory_search` 一直 unavailable。

**正确做法**（依据插件源码 `dist/index.js`）：

```js
// L25-26: 默认缓存目录与文件名
const modelCacheDir = local.modelCacheDir ?? path.join(os.homedir(), ".node-llama-cpp", "models");
const DEFAULT_..._CACHE_FILE_NAME = "hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf";
// L27: hf:/http(s): 前缀的 modelPath 不做本地 resolve
```

把模型放到默认缓存位置、**用插件期望的文件名**，然后**不配** `modelPath`：

```bash
mkdir -p ~/.node-llama-cpp/models && cd ~/.node-llama-cpp/models
curl -L -o hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf \
  "https://hf-mirror.com/ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/resolve/main/embeddinggemma-300m-qat-Q8_0.gguf"

# 校验：328577056 bytes + GGUF magic
stat -f%z hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf   # 应为 328577056
head -c 4 hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf | xxd   # 应为 "GGUF"

openclaw config unset memory.search.local.modelPath   # 若之前设过，必须清掉
openclaw memory index --force --agent main
```

**镜像**：`hf-mirror.com` 实测可用（HTTP 200，1.5s，约 6 MB/s）。

**核心教训**：文件名必须是 `hf_ggml-org_` 前缀那个 —— 插件按此名在缓存目录查找，
命中即跳过下载；配置保持默认标识，索引身份才能与 gateway 一致。

**默认模型**：`embeddinggemma-300m-qat-Q8_0.gguf`（~0.6 GB，自动下载）
基于 Gemma 3，官方称支持 100+ 语言，含中文。

**为什么选它**：
- 零 API 成本、零数据外发（记忆内容含 `MEMORY.md`/`USER.md`，本就不该出网）
- 无网络依赖 → 不会 fail closed
- 300m 参数，CPU 可跑，本机 M 系列足够

**成本**：一次性 ~0.6 GB 模型 + 插件依赖（实测 llama.cpp 预编译二进制约 1.4 GB）。

## 4. 火山引擎 embedding：实测结论

Rex 要求"需要时自动启用对应 embedding 模型"。已实测，**当前不可用**，原因明确：

| 端点 | 结果 | 含义 |
|---|---|---|
| `/api/v3/embeddings` | `404 InvalidEndpointOrModel.NotFound` | 鉴权通过，但**模型未开通** |
| `/api/coding/v3/embeddings` | `404 UnsupportedModel` | **Coding Plan 端点不提供 embedding** |

两个错误码不同，信息量很大：

- `coding/v3` 报 `UnsupportedModel` + "does not support the coding plan feature"
  → 现有 Coding Plan 订阅**不覆盖** embedding，必须走标准 `/api/v3` 并**单独计费**
- `v3` 报 `InvalidEndpointOrModel.NotFound`
  → key 有效，但需在控制台**开通管理 → 向量模型**开通模型

**候选模型**（据 LiteLLM 文档与 arkcli）：

| 模型 | 维度 | 备注 |
|---|---|---|
| `doubao-embedding-large` | 2048 | MTEB 中文 SOTA 宣称 |
| `doubao-embedding-large-text-250515` | 2048 | large 的 primary_version |
| `doubao-embedding` | 2560 | 上一代 |
| `doubao-embedding-vision-251215` | 1024/2048 | 多模态，文本场景无必要 |

**定价**（官方模型卡）：文本输入 ~¥0.0007/千 tokens。

### 4.1 为什么不设为主 provider

即使开通，也**不建议**设为 `provider`：

1. **fail closed** —— 网络抖动/额度耗尽 → `memory_search` 直接 unavailable。
   而系统指令强制每次记忆查询都调它。
2. **数据外发** —— 记忆含 `MEMORY.md`/`USER.md`/日常日志。每次检索把 query
   发给第三方，与 SOUL.md「不外发私有数据」冲突。
3. **重建索引** —— 切换 provider 会使 SQLite 向量索引失效，需 `memory index --force`。

### 4.2 适用场景

若将来出现**本地模型明显召回不足**的实测证据（不是猜测），再考虑：
- 开通模型 → 用 `openai-compatible` 指向 `/api/v3`
- 或作为**离线批量重建索引**的一次性工具，而非在线检索路径

**判断依据必须是实测对比，不是"云模型应该更好"的假设。**

## 5. 索引重建注意

官方警告：改 provider / model / chunking / sources / scope / tokenizer 会使
现有向量索引不兼容。OpenClaw **不会**自动全量重嵌入，而是暂停向量检索并报
index identity warning。

```bash
openclaw memory index --force --agent main   # 就绪后手动重建
openclaw memory status --deep --agent main   # 确认 backend/device/offload
```

## 6. 验证（已完成，实测通过）

```bash
openclaw memory status --agent main
```

**实测结果**：
```
Provider: local (requested: local)
Model: hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf
Indexed: 16/11 files · 557 chunks
Vector dims: 768
FTS: ready
Embedding cache: enabled (1078 entries)
Recall store: scripts=25 latin, 26 cjk, 182 mixed
```

**语义检索能力证明**（决定性证据）：

查询「如何避免把密钥泄露到开源代码仓库」——**字面词一个都不在记忆里**：

| 命中 | `textScore` | `vectorScore` | 实际内容 |
|---|---|---|---|
| `USER.md#L103` | **0** | 0.691 | 「Never 把凭据/API key 写到任何 markdown 文件」|
| `MEMORY.md#L73` | **0** | 0.595 | 「Tavily 和 GitHub 已有不一致的凭据管理方式」|

`textScore: 0` 意味着**关键词检索完全无法命中**，纯靠向量语义召回。
查询说「密钥/开源仓库」，记忆写「凭据/API key/markdown」—— 这正是修复前做不到的。

另一例：「config 治理与变更可追溯」→ 命中 ADR-007 相关段落，
`vectorScore` 0.58~0.65 与 `textScore` 0.56~0.71 混合排序，命中准确。

> ⚠️ `openclaw memory status --deep` 曾因缺 OpenAI key 导致 CLI 启动即失败
> （`missing-provider-auth`）。改为 `local` 后 `memory status` 正常运行 —— 已验证。

## 7. 监控点

- ⚠️ OpenClaw 升级后确认 `memory.search` 字段语义未变（尤其 fail-closed 规则）
- ⚠️ 若换 embedding 模型，必须 `memory index --force`，否则向量检索静默暂停
- ⚠️ 定期抽查中文召回质量；若确认不足，才评估云端方案
- ⚠️ 插件占用约 1.3 GB + 模型 313 MB（若保留两个文件名副本则 626 MB）
- ⚠️ **模型文件名不可改** —— 必须是 `hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf`，
  否则插件找不到会尝试联网下载并挂起
- ⚠️ **不要设 `local.modelPath` 绝对路径** —— 会造成索引身份与 gateway 永久不匹配
- ⚠️ 重建索引前先确认无残留 `*.reindex-lock.sqlite`（进程被 kill 会留下陈旧锁）

## 8. 相关

- **ADR**: [ADR-202608-009](../../../knowledge-base/by-category/project-experience/adr/ADR-202608-009-memory-embedding-provider.md)
- **ADR-008**: 工具策略治理 —— 本问题是 `allowed-but-broken` 的实例
- **官方文档**: `concepts/memory-builtin.md` · `reference/memory-config.md`
