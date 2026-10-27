# Bangcle 产品/服务知识库 设计大纲

| 项 | 值 |
|---|---|
| 文档 | DESIGN-OUTLINE |
| 版本 | v1.0 |
| 层级 | L4 Bangcle 专有业务模块 |
| 状态 | 设计待审 |
| 模块编码 | product-kb |
| 业务域 | 产品销售支撑 |

---

## 1. 架构设计

### 1.1 遵循 4 层架构

本模块是 **L4 专有业务模块**，属于 Bangcle 专属产品知识库，依赖 L2 基础设施层组件：

| L2 组件 | 依赖用途 |
|---|---|
| `persistence-006` | SQLite 持久化存储 |
| `memory-search-009` | 向量嵌入与检索 |
| `ocr-digitalization` | 扫描版文档 OCR 抽取兜底 |
| `role-library` | 角色代理框架，支持特定问答角色 |

### 1.2 四层架构设计（模块内）

```
┌─────────────────────────────────────────────────────┐
│  应用层  (API + CLI + Web UI)                         │
│  - contract_match: 合同标的比对                        │
│  - product_query: 产品多维度查询                        │
│  - product_qa: 产品知识问答                            │
│  - product_compare: 多产品对比                          │
├─────────────────────────────────────────────────────┤
│  知识图谱层  (Entity + Relation + Inference)           │
│  - 产品线 → 产品 → 分类 → SKU → 价格 → 文档 → 功能点        │
│  - 推理：产品聚类 / 版本演进 / 关联推荐                  │
├─────────────────────────────────────────────────────┤
│  文档切片层  (Chunking + Indexing)                     │
│  - 文档解析 → 文本抽取 → 语义切片 → 向量化 → 混合索引        │
├─────────────────────────────────────────────────────┤
│  主数据层  (Structured Master Data)                    │
│  - 产品线表 + 产品主档表 + SKU表 + 分类表 + 文档资产表        │
└─────────────────────────────────────────────────────┘
```

这个设计复用了之前梳理的架构，符合分层原则，所有依赖都在现有 L2 组件内，不新增外部依赖。

---

## 2. 模块划分

| 模块 | 职责 | 依赖 |
|---|---|---|
| `io` | 价格表导入 / 文档扫描 / 文件解析 | openpyxl / python-docx / python-pptx / PyPDF2 / L2 OCR |
| `index` | 文档切片 / 向量化 / FTS 索引构建 / 向量索引 | L2 memory-search embedding 能力 |
| `db` | 主数据操作 / 增删改查 / 事务 | L2 persistence SQLite 封装 |
| `graph` | 实体关系构建 / 推理查询 | 无（纯 Python 三元组遍历） |
| `search` | 混合检索（关键词 + 向量） / 排序 | FTS5 + 向量余弦相似度 |
| `contract` | 合同标的匹配 / 比对 / 预警 | 搜索模块 + 主数据 |
| `qa` | 问答检索 / 结果排序 / 摘要生成 | 搜索模块 + 当前大模型 |
| `compare` | 多产品对比矩阵生成 | 主数据 + 知识图谱 |
| `cli` | CLI 命令行入口 | 所有模块 |
| `web` | Web UI | FastAPI + 前端模板（复用现有） |

---

## 3. 核心接口契约

### 3.1 CLI 入口

```bash
# 导入价格表
python -m product_kb cli import-price --xlsx /path/to/price.xlsx

# 扫描文档目录并关联
python -m product_kb cli scan --root /path/to/docs

# 全量抽取文档并构建索引
python -m product_kb cli build-index [--full]

# 数据质量校验
python -m product_kb cli check

# 合同比对
python -m product_kb cli match --input contract.csv --output result.xlsx

# 问答查询
python -m product_kb cli query "问题"

# 产品对比
python -m product_kb cli compare --products "产品A,产品B,产品C"
```

### 3.2 Python API

```python
from product_kb import ProductKB

kb = ProductKB()
kb.import_price(xlsx_path)
kb.scan_docs(root_path)
kb.build_index()

# 合同比对
result = kb.match_contract(contract_items)

# 问答
results = kb.search(query, top_k=5)

# 产品对比
matrix = kb.compare_products(product_ids)
```

---

## 4. 演进路线（分阶段交付）

| Phase | 功能范围 | 预估工时 |
|---|---|---|
| Phase 1 | 主数据层 + IO 模块 + DB + CLI 价格导入 + 文档扫描 + 基础查询 | 8-10h |
| Phase 2 | 文档抽取 + 切片 + 索引构建 + 合同比对 CLI + 质量校验 | 8-10h |
| Phase 3 | 问答检索 + 知识图谱基础 + 产品对比 CLI | 4-6h |
| Phase 4 | Web UI + 导出 + 增量更新 + 权限控制 | 6-8h |

---

## 5. 已知问题与教训

| 问题 | 教训 |
|---|---|
| 原始文件不在项目目录，路径迁移后索引失效 | 设计相对路径 + 配置文件记录原始根目录，支持重配置根路径 |
| 产品命名不一致导致匹配失败 | 建立别名表 + 相似度匹配兜底 + 质量检查工具自动发现 |
| 版本号提取不准确 | 多正则匹配策略 + 人工标注兜底 |
| 扫描版 PDF 文字识别错误 | 复用 L2 OCR 组件，支持人工修正后重新索引 |
| 产品与文档一对多/多对多关联 | 不强制一对一，保留所有关联，检索时加权排序 |

