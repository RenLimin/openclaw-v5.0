# knowledge-base — 通用知识库组件

> L2 基础设施层 · 知识库能力（六项子能力全备）
>
> 2026-09-10 从 `memory-embedding` 组件中独立出来。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 类型 | 通用能力组件 |
| 职责 | 文档解析 / 分块 / 向量化 / 索引构建 / 语义检索 / 知识管理 |
| 底层依赖 | `memory-embedding`（嵌入计算） |
| 上游调用方 | L3 业务组件、memory_search、CLI 工具 |

## 2. 六项子能力

| # | 子能力 | 模块 | 说明 |
|---|---|---|---|
| 1 | 文档解析 | `parser.py` | Markdown / 纯文本 / 代码文件，支持 YAML frontmatter |
| 2 | 文本分块 | `chunker.py` | 语义分块（按标题）/ 字符分块 / Token 分块 |
| 3 | 向量化 | `embedder.py` | 抽象基类 + 本地 GGUF 实现 + Mock 实现 |
| 4 | 索引构建 | `index.py` | 简单余弦索引（纯 Python，< 1 万条适用） |
| 5 | 检索 | `retriever.py` | 语义检索 / 关键词检索 / 混合检索（可配置权重） |
| 6 | 知识管理 | `manager.py` | 文档 CRUD / 分类 / 标签 / 持久化 |

统一入口：`core.py` → `KnowledgeBase` 类。

## 3. 目录结构

```
knowledge-base/
├── src/knowledge_base/
│   ├── __init__.py      # 公共 API 导出
│   ├── core.py          # KnowledgeBase 主类（统一门面）
│   ├── document.py      # 数据模型（Document / Chunk / SearchResult）
│   ├── parser.py        # 文档解析器
│   ├── chunker.py       # 文本分块器
│   ├── embedder.py      # 向量化接口
│   ├── index.py         # 向量索引
│   ├── retriever.py     # 检索器
│   ├── manager.py       # 知识管理
│   └── cli.py           # CLI 入口
├── tests/               # 测试（43 个用例）
├── kb_index.py          # 特定知识库 frontmatter 索引工具（特化应用）
├── DESIGN.md            # 架构设计文档
└── README.md            # 本文件
```

## 4. 快速开始

### 4.1 Python API

```python
from knowledge_base import KnowledgeBase, Document

# 创建知识库（默认 MockEmbedder，不依赖模型下载）
kb = KnowledgeBase()

# 添加文档
doc = Document(
    title="Python 入门",
    content="Python 是一种简单易学的编程语言...",
    category="tech",
    tags=["python", "编程"],
)
doc_id = kb.add_document(doc)

# 搜索（混合检索）
results = kb.search("编程入门", limit=5, mode="hybrid")
for r in results:
    print(f"[{r.score:.2f}] {r.title}: {r.snippet}")

# 切换检索模式
kb.retrieval_mode = "semantic"  # 纯语义
kb.retrieval_mode = "keyword"   # 纯关键词
kb.retrieval_mode = "hybrid"    # 混合（默认）

# 持久化
kb.save("./my_kb")              # 保存
kb2 = KnowledgeBase.load("./my_kb")  # 加载
```

### 4.2 CLI

```bash
# 添加文件
python3 -m knowledge_base.cli add docs/*.md --store ./.kb_store

# 搜索
python3 -m knowledge_base.cli search "查询关键词" --mode hybrid -n 10

# 列出文档
python3 -m knowledge_base.cli list --category tech

# 统计
python3 -m knowledge_base.cli stats

# 重建索引
python3 -m knowledge_base.cli rebuild
```

## 5. API 参考

### KnowledgeBase 主类

| 方法 | 说明 |
|---|---|
| `add_document(doc: Document \| str) -> str` | 添加文档，返回 doc_id |
| `add_documents(docs: list[Document]) -> list[str]` | 批量添加 |
| `add_file(path, doc_type=None) -> str` | 从文件添加 |
| `search(query, limit=10, mode=None, filters=None) -> list[SearchResult]` | 搜索 |
| `get_document(doc_id) -> Document \| None` | 获取文档 |
| `delete_document(doc_id) -> bool` | 删除文档 |
| `list_documents(category=None, tag=None) -> list[Document]` | 列出文档 |
| `rebuild_index() -> bool` | 重建向量索引 |
| `save(path)` / `load(path)` | 持久化 / 加载 |
| `stats() -> dict` | 统计信息 |

### 检索模式

| 模式 | 类 | 适用场景 |
|---|---|---|
| `semantic` | `SemanticRetriever` | 语义理解、同义匹配 |
| `keyword` | `KeywordRetriever` | 精确关键词、专有名词 |
| `hybrid` | `HybridRetriever` | 综合效果（默认） |

混合权重可通过 `set_weights(semantic_weight, keyword_weight)` 调整。

### 分块策略

| 策略 | 类 | 适用场景 |
|---|---|---|
| 语义分块 | `SemanticChunker` | Markdown（按标题切分，默认） |
| 字符分块 | `CharacterChunker` | 通用，按自然断点切分 |
| Token 分块 | `TokenChunker` | 对 token 数敏感的场景 |

## 6. 嵌入模型

默认使用 `MockEmbedder`（基于哈希的伪向量，用于测试和无模型环境）。

生产环境使用本地 GGUF 模型（与 memory_search 共享）：

```python
from knowledge_base import KnowledgeBase, LocalEmbedder

embedder = LocalEmbedder()  # 默认路径 ~/.node-llama-cpp/models/...
kb = KnowledgeBase(embedder=embedder)
```

模型不可用时自动降级为 MockEmbedder，不影响系统可用性。

## 7. 索引存储

- **格式**：JSON（元数据 + 映射）+ 二进制文件（float32 向量）
- **位置**：`storage_dir/` 下，包含：
  - `documents.json` — 文档内容与元数据
  - `vector_index.json` — 索引元数据
  - `vector_index.vec.bin` — 向量二进制（紧凑存储）
  - `chunk_mapping.json` — 文档→块映射
  - `config.json` — 配置

不依赖数据库，保持轻量。规模超过 1 万条时建议升级到 FAISS。

## 8. 测试

```bash
python3 -m pytest L2-infra/components/knowledge-base/tests/ -v
```

43 个测试用例，覆盖：
- 文档模型（5）
- 文档解析（5）
- 文本分块（6）
- 向量化 + 索引（8）
- 检索器 + 知识管理（10）
- KnowledgeBase 集成（9）

## 9. 迁移指南

### 从 memory-embedding 迁移

旧路径：
```python
# ❌ 旧方式
import sys
sys.path.insert(0, "L2-infra/components/memory-embedding")
from kb_index import parse_doc, load_docs
```

新方式（通用知识库）：
```python
# ✅ 新方式
import sys
sys.path.insert(0, "L2-infra/components/knowledge-base/src")
from knowledge_base import KnowledgeBase, Document, MarkdownParser

parser = MarkdownParser()
doc = parser.parse_file("path/to/doc.md")
```

新方式（kb_index 工具，兼容原功能）：
```python
# 直接使用 knowledge-base 下的 kb_index.py
python3 L2-infra/components/knowledge-base/kb_index.py --validate
```

### 向后兼容

`memory-embedding/kb_index.py` 保留为 wrapper，脚本调用和模块导入均兼容。建议逐步迁移。

## 10. 相关文档

- 架构设计：[DESIGN.md](./DESIGN.md)
- 知识库架构总览：`docs/architecture/03-knowledge-base-architecture.md`
- 依赖组件：`../memory-embedding/`
