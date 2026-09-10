# 知识库能力组件设计

> L2 基础设施层 · 通用知识库能力组件
>
> **2026-09-10 重大更新**：从 `memory-embedding` 组件中独立出来，新增通用向量知识库能力（解析/分块/向量化/索引/检索/管理）。
> 原 `kb_index.py`（frontmatter 索引工具）作为本组件的一个特化应用保留。

## 1. 定位

| 维度 | 值 |
|---|---|
| 层级 | L2 基础设施层 |
| 组件类 | 知识库能力 |
| 组件 ID | 010 |
| 状态 | ✅ 已建设 (2026-08-23) — 2026-09-10 独立化升级 |
| ADR | ADR-010 (知识库工具链组件)、ADR-003 (知识库演进路径) |
| 验证 | pre-commit 第 3 段（阻塞性错误拒绝提交）、43 个单元测试 |

## 2. 设计约束

1. **轻量优先**：默认零外部依赖（纯 Python + JSON + 二进制向量文件），不依赖数据库。
2. **可扩展**：所有子能力均为抽象基类 + 默认实现，可替换（如 FAISS 替代 SimpleIndex、本地模型替代 MockEmbedder）。
3. **可降级**：嵌入模型不可用时自动降级为 MockEmbedder，保证系统可用。
4. **Markdown 是唯一来源**（ADR-003 §4.3）：kb_index 工具只读，不反向写内容文件。
5. **可重建**：所有索引/视图都是派生数据，可全量重建。
6. **幂等**：`--emit-index` 再跑一次结果不变。

## 3. 架构

```
┌─────────────────────────────────────────────────────┐
│                    KnowledgeBase                     │  统一门面 (core.py)
├──────────┬──────────┬──────────┬──────────┬──────────┤
│  parser  │ chunker  │ embedder │  index   │ retriever│  六大子能力
│ (解析)   │ (分块)   │ (向量化) │ (索引)   │ (检索)   │
├──────────┴──────────┴──────────┴──────────┴──────────┤
│                      manager                         │  知识管理 (CRUD/分类/标签)
├──────────────────────────────────────────────────────┤
│                  memory-embedding                    │  底层嵌入计算（依赖）
└──────────────────────────────────────────────────────┘
```

### 3.1 模块职责

| 模块 | 文件 | 职责 |
|---|---|---|
| core | `core.py` | KnowledgeBase 主类，统一门面，整合所有子能力 |
| document | `document.py` | 数据模型：Document / Chunk / SearchResult |
| parser | `parser.py` | 文档解析：Markdown(含 frontmatter) / 纯文本 / 代码 |
| chunker | `chunker.py` | 文本分块：语义 / 字符 / Token 三种策略 |
| embedder | `embedder.py` | 向量化接口：抽象基类 + LocalEmbedder + MockEmbedder |
| index | `index.py` | 向量索引：SimpleIndex（纯 Python 余弦相似度） |
| retriever | `retriever.py` | 检索器：语义 / 关键词(BM25简化) / 混合 |
| manager | `manager.py` | 知识管理：CRUD / 分类 / 标签 / 持久化 |
| cli | `cli.py` | CLI 入口 |

### 3.2 特化应用

| 工具 | 文件 | 说明 |
|---|---|---|
| kb_index | `kb_index.py` | 特定知识库 frontmatter 索引工具（ADR-003 阶段 2 工具链） |

## 4. 核心 API（KnowledgeBase）

```python
kb = KnowledgeBase()

# 文档管理
doc_id = kb.add_document(doc)          # 添加
kb.add_documents(docs)                 # 批量添加
doc = kb.get_document(doc_id)          # 获取
kb.delete_document(doc_id)             # 删除
docs = kb.list_documents(category=...) # 列出

# 检索
results = kb.search("query", limit=10, mode="hybrid")  # semantic/keyword/hybrid

# 索引
kb.rebuild_index()                     # 重建
kb.save("./kb_store")                  # 持久化
kb = KnowledgeBase.load("./kb_store")  # 加载
```

### 4.1 检索模式

| 模式 | 说明 | 默认权重 |
|---|---|---|
| semantic | 纯语义检索（向量相似度） | — |
| keyword | 纯关键词检索（BM25 简化版） | — |
| hybrid | 混合检索（语义 + 关键词加权） | 语义 0.6 / 关键词 0.4 |

## 5. kb_index 工具（特化应用）

针对 `docs/knowledge-base/` 下 Markdown 文件的 frontmatter 索引工具，ADR-003 阶段 2 工具链。

```bash
kb_index.py --validate              # schema 校验（pre-commit 集成）
          --stats                   # 三维分布统计
          --query layer=L2 stage=manage  # 三维交叉查询
          --tags                    # tag 聚合
          --xref                    # 交叉引用图 + 孤岛/断链检测
          --emit-index              # 重生 INDEX.md 派生小节（幂等）
          --json                    # 全量结构化输出
          --export DIR              # 导出便携 bundle（跨系统移植）
          --render ID_OR_PATH       # 渲染单篇人机协作视图
```

### 5.1 设计约束（kb_index 特有）

- **只读，不反向写**（ADR-003 §4.3 核心原则）。唯一例外：INDEX.md 标记区。
- **schema 容错，不卡内容**。已有内容漂移通过 `--validate` 的 drift 段报告，输出归一化但不报错。
- **CI 友好**。`--validate` 异常退出码，被 pre-commit 集成。

### 5.2 数据模型（kb_index）

`Doc` 对象字段：

```
path, doc_id, doc_type, title, date, status,
layers, stage, category, tags, related, body_refs, links,
is_template, errors, drift, refs (派生),
dimension, sub_area, xref, last_reviewed, source, version  (业务知识库扩展)
```

## 6. 存储格式

| 文件 | 格式 | 说明 |
|---|---|---|
| documents.json | JSON | 文档内容 + 元数据 |
| vector_index.json | JSON | 索引元数据 + chunk 信息 |
| vector_index.vec.bin | 二进制 | float32 向量（紧凑存储） |
| chunk_mapping.json | JSON | doc_id → [chunk_id] 映射 |
| config.json | JSON | 检索模式、权重、维度等配置 |

全部为本地文件，无数据库依赖。

## 7. 演进方向

| 方向 | 优先级 | 触发条件 |
|---|---|---|
| FAISS 索引替换 SimpleIndex | 中 | 知识库条目 > 10000 或检索变慢 |
| 增量索引 | 低 | 全量重建时间 > 30s |
| 多语言分词 | 低 | 非中英内容占比 > 20% |
| kb_index 功能迁移到通用层 | 中 | 通用能力成熟后，逐步将 kb_index 重构为 KnowledgeBase 的一个数据源 |
| 自建系统（服务层：DB + Web 渲染） | 暂缓 | ADR-003 §4.2 触发条件 ≥ 2 个达成 |

## 8. 验证

- **单元测试**：43 个用例，覆盖所有模块
  ```bash
  python3 -m pytest L2-infra/components/knowledge-base/tests/
  ```
- **kb_index 校验**：已被 pre-commit 第 3 段集成，阻断性错误拒绝提交
- **幂等性**：`--emit-index` 重复运行输出不变
- **向后兼容**：`memory-embedding/kb_index.py` 保留为 wrapper

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-23 | kb_index.py 首版（7 子命令） |
| 2026-08-24 | 补齐业务知识库支持（dimension / xref / source 等） |
| 2026-09-10 | 从 memory-embedding 独立为 knowledge-base 组件，新增通用向量知识库六模块 |
