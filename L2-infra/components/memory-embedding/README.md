# memory-embedding — 内存嵌入计算组件

> L2 基础设施层 · 纯嵌入计算能力
>
> **职责变更（2026-09-10）**：知识库相关能力（文档解析、分块、索引构建、知识管理、语义检索）已迁移到独立的 `knowledge-base` 组件。本组件只保留纯嵌入计算能力。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 类型 | 基础能力组件 |
| 职责 | 文本向量化 / 嵌入模型管理 / 向量计算 |
| 下游依赖 | 无（直接调用本地 GGUF 模型） |
| 上游调用方 | `knowledge-base` 组件（主要）、memory_search 等 |

## 2. 职责范围

**本组件负责**：
- 嵌入模型的加载与管理（本地 GGUF embedding 模型）
- 文本 → 向量的计算（单条 / 批量）
- 向量的基础运算（归一化、相似度计算）
- 嵌入模型的健康检查与降级策略

**不再负责**（已迁移到 knowledge-base）：
- ~~文档解析~~ → `knowledge-base/parser.py`
- ~~文本分块~~ → `knowledge-base/chunker.py`
- ~~向量索引构建与存储~~ → `knowledge-base/index.py`
- ~~语义检索~~ → `knowledge-base/retriever.py`
- ~~知识库文档管理（CRUD / 分类 / 标签）~~ → `knowledge-base/manager.py`
- ~~kb_index.py 知识库索引工具~~ → `knowledge-base/kb_index.py`

## 3. 向后兼容

为避免破坏现有引用，以下文件保留为 wrapper：

| 文件 | 说明 |
|---|---|
| `kb_index.py` | 转发到 `../knowledge-base/kb_index.py`，脚本调用与模块导入均兼容 |

**新代码请直接引用 knowledge-base 组件**，本 wrapper 将在未来版本中移除。

## 4. 嵌入模型

默认使用与 `memory_search` 相同的本地 GGUF 嵌入模型：

```
~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf
```

- 维度：768
- 类型：embeddinggemma-300m（Q8_0 量化）
- 供应方：本地 llama-cpp-provider，零 API 成本，数据不出机器

### 降级策略

模型不可用时自动降级到 MockEmbedder（基于文本哈希的伪向量），保证系统可用但检索质量下降。

## 5. 测试

```bash
python3 -m pytest L2-infra/components/memory-embedding/tests/
```

## 6. 相关组件

- **knowledge-base** → `../knowledge-base/` — 通用知识库（解析/分块/索引/检索/管理）
- **memory_search** → 主会话 `memory_search` 工具，使用相同嵌入模型
