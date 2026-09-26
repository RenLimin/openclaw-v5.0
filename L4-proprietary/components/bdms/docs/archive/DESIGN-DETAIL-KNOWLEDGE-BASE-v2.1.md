# BDMS v2.1 知识库（Knowledge Base）详细设计

| 项 | 值 |
|---|---|
| 版本 | v2.1 |
| 层级 | L4 BDMS 模块详细设计 |
| 继承 | L3 横切域（Cross-Cutting） |
| 状态 | 设计中 |
| 模块编码 | knowledge_base |
| 对应 L3 域 | Cross-Cutting / Knowledge Base |
| 横切依赖 | Base Engine / Service / Importer 框架，L2 Memory-009（本地 GGUF embedding），L2 Persistence-006（SQLite + FTS5） |

---

## 1 模块概述

### 1.1 业务定位

知识库模块是 BDMS 的**横切支撑模块**，为项目管理、售后管理、合同管理等多个业务模块提供产品/服务知识支撑。

核心能力：
- **结构化知识管理**：产品规格书、服务 SLA、部署手册、验收标准、合同条款模板、定价参考、故障排查 FAQ
- **混合检索**：全文检索（SQLite FTS5）+ 语义检索（本地 GGUF embedding）+ 标签/产品维度过滤
- **知识生命周期**：创建 → 审核 → 发布 → 版本迭代 → 归档 → 删除

### 1.2 与 master_data 的区别

master_data 和 knowledge_base 同属横切域，但定位完全不同：

| 维度 | master_data（主数据） | knowledge_base（知识库） |
|---|---|---|
| 数据形态 | 字典条目（code → label） | 知识文档（长文本 + 结构化字段） |
| 典型数据 | 项目类型、客户行业、人员职级 | 产品规格书、SLA 标准、FAQ |
| 数据量 | 几十到几百条 | 几千到几万条 |
| 检索方式 | 精确匹配（by code / by label） | 语义检索 + 全文检索 + 精确过滤 |
| 更新频率 | 低（季度/年度） | 中（月度/周度） |
| 版本管理 | 简单（启用/停用） | 完整版本链（v1 → v2 → v3） |
| 审核流程 | 无（直接生效） | 有（创建→审核→发布） |
| 消费方式 | 下拉选项、枚举值 | 搜索结果、详情页、推荐位 |

### 1.3 知识类型清单

知识库支持 7 种核心知识类型：

| 类型编码 | 类型名称 | 典型内容 | 使用场景 |
|---|---|---|---|
| `product_spec` | 产品规格书 | 功能清单、技术参数、部署要求、兼容性矩阵 | 售前方案、项目规划 |
| `service_sla` | 服务 SLA 标准 | 响应时间、解决时效、服务范围、排除项 | 售后工单、合同签署 |
| `deploy_manual` | 部署实施手册 | 安装步骤、配置指南、环境要求、常见问题 | 项目实施、交付 |
| `acceptance_std` | 验收标准 | 验收项、验收方法、通过准则、交付物清单 | 项目验收、合同条款 |
| `contract_clause` | 合同条款模板 | 标准条款、免责声明、违约责任、保密协议 | 合同起草、法务审核 |
| `pricing_ref` | 产品定价参考 | 指导价、折扣策略、报价模板、成本构成 | 售前报价、商务谈判 |
| `trouble_faq` | 故障排查 FAQ | 问题描述、原因分析、解决方案、适用版本 | 售后支持、一线工程师 |

### 1.4 服务模块矩阵

| 业务模块 | 使用知识类型 | 集成方式 |
|---|---|---|
| 项目管理（project_management） | product_spec / deploy_manual / acceptance_std | 项目启动时推荐实施手册；验收时关联验收标准 |
| 售后管理（after_sales） | service_sla / trouble_faq / product_spec | 工单创建时自动匹配 FAQ；SLA 时效计算 |
| 合同管理（contract_management） | contract_clause / pricing_ref / service_sla | 合同起草时引用条款模板；报价时参考定价 |
| 客户管理（customer_management） | product_spec / pricing_ref | 客户视图中展示已购产品知识 |
| 销售管理（sales_management） | pricing_ref / product_spec / contract_clause | 商机阶段推荐方案和报价 |

---

## 2 架构图

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                   Knowledge Base Module (kb_)                 │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │          KnowledgeBaseService (服务编排层)              │    │
│  │   权限校验 / 事务编排 / 生命周期管理 / 检索路由          │    │
│  └──────┬───────────┬──────────────┬───────────┬──────┘    │
│         │           │              │           │            │
│  ┌──────▼──┐ ┌──────▼──────┐ ┌────▼─────┐ ┌───▼───────┐  │
│  │ CRUD    │ │ Search      │ │ Import   │ │ Version   │  │
│  │ Engine  │ │ Engine      │ │ Engine   │ │ Engine    │  │
│  │ (知识   │ │ (混合检索   │ │ (知识导  │ │ (版本管理  │  │
│  │  维护)  │ │  + 推荐)    │ │  入)     │ │  + 审核)   │  │
│  └──────┬──┘ └──────┬──────┘ └────┬─────┘ └───┬───────┘  │
│         │           │              │           │            │
│  ┌──────▼───────────▼──────────────▼───────────▼──────┐    │
│  │              数据层 (kb_ 系列表)                        │    │
│  │  kb_item / kb_version / kb_tag / kb_embedding / FTS5  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌─────────────────────┐  ┌───────────────────────────┐   │
│  │ EmbeddingProvider   │  │ FullTextSearchEngine      │   │
│  │ (L2 Memory-009)     │  │ (SQLite FTS5 + 中文分词)  │   │
│  │ 768-dim GGUF 本地   │  │ BM25 排序 + 权重配置      │   │
│  └─────────────────────┘  └───────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 混合检索流程

```
用户查询 "等保三级测评多久做一次"
        │
        ▼
┌───────────────────┐
│  查询预处理        │
│  - 中文分词        │
│  - 关键词提取      │
│  - 生成 embedding  │
└─────────┬─────────┘
          │
   ┌──────┴───────┐
   ▼              ▼
┌─────────┐  ┌──────────┐
│ FTS5    │  │ 语义检索  │
│ 全文检索 │  │ 向量相似度│
│ BM25    │  │ cosine   │
│ 得分    │  │ 得分     │
└────┬────┘  └────┬─────┘
     │            │
     └──────┬─────┘
            ▼
   ┌──────────────────┐
   │  结果融合 + Rerank│
   │  - 权重加权融合   │
   │  - 标签过滤       │
   │  - 产品过滤       │
   │  - 类型过滤       │
   └─────────┬────────┘
             ▼
   ┌──────────────────┐
   │  结果排序 + 分页  │
   │  Top-K 返回      │
   └──────────────────┘
```

### 2.3 知识生命周期

```
  创建草稿    提交审核    审核通过      更新迭代      归档
  ────────► ────────► ────────► ... ────────► ... ────────►
  (draft)   (pending)  (published)  (new version)  (archived)
                │                                    │
                │ 审核驳回                            │ 恢复
                ▼                                    ▼
             (rejected)                          (archived ↔ published)

  删除（软删除）：任何状态 → deleted（仅管理员可见，30 天后物理删除）
```

---

## 3 核心类设计

### 3.1 KnowledgeBaseService（主服务类）

```python
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from enum import Enum
from decimal import Decimal


class KnowledgeType(str, Enum):
    """知识类型枚举。"""
    PRODUCT_SPEC = "product_spec"       # 产品规格书
    SERVICE_SLA = "service_sla"         # 服务 SLA 标准
    DEPLOY_MANUAL = "deploy_manual"     # 部署实施手册
    ACCEPTANCE_STD = "acceptance_std"   # 验收标准
    CONTRACT_CLAUSE = "contract_clause" # 合同条款模板
    PRICING_REF = "pricing_ref"         # 产品定价参考
    TROUBLE_FAQ = "trouble_faq"         # 故障排查 FAQ


class KnowledgeStatus(str, Enum):
    """知识状态枚举。"""
    DRAFT = "draft"              # 草稿
    PENDING_REVIEW = "pending"   # 待审核
    PUBLISHED = "published"      # 已发布
    REJECTED = "rejected"        # 已驳回
    ARCHIVED = "archived"        # 已归档
    DELETED = "deleted"          # 已删除（软删）


class KnowledgeBaseService(BaseService):
    """
    知识库主服务类：统一编排入口。
    负责权限校验、事务编排、生命周期管理、检索路由。
    """

    # ===== 知识 CRUD =====

    def create_knowledge(
        self,
        knowledge_type: KnowledgeType,
        title: str,
        content: str,
        product_code: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
        author: str = "",
    ) -> str:
        """
        创建知识条目（草稿状态）。
        同步触发：生成 embedding、写入 FTS5 索引（但标记为未发布）。
        返回 knowledge_id。
        """
        ...

    def update_knowledge(
        self,
        knowledge_id: str,
        **kwargs,
    ) -> None:
        """
        更新知识条目。
        已发布知识的更新会创建新版本（版本号自增），不影响已发布版本。
        草稿状态直接覆盖。
        """
        ...

    def get_knowledge(self, knowledge_id: str, version: Optional[int] = None) -> Dict:
        """
        获取知识详情。
        version=None 返回最新发布版本；指定版本返回对应版本。
        """
        ...

    def delete_knowledge(self, knowledge_id: str, operator: str, permanent: bool = False) -> None:
        """
        删除知识条目。
        permanent=False：软删除（status=deleted），30 天后自动清理。
        permanent=True：立即物理删除（需管理员权限）。
        """
        ...

    # ===== 生命周期 =====

    def submit_for_review(self, knowledge_id: str, submitter: str) -> None:
        """提交审核：draft → pending_review。"""
        ...

    def review_knowledge(
        self,
        knowledge_id: str,
        reviewer: str,
        approved: bool,
        comment: str = "",
    ) -> None:
        """
        审核知识。
        approved=True：pending → published，生成新版本号
        approved=False：pending → rejected，记录审核意见
        """
        ...

    def publish_knowledge(self, knowledge_id: str, operator: str) -> None:
        """
        直接发布（跳过审核，需管理员权限）。
        用于紧急更新或系统初始化。
        """
        ...

    def archive_knowledge(self, knowledge_id: str, operator: str, reason: str = "") -> None:
        """归档知识：published → archived。"""
        ...

    def restore_knowledge(self, knowledge_id: str, operator: str) -> None:
        """恢复知识：archived → published。"""
        ...

    # ===== 检索 =====

    def search(
        self,
        query: str,
        knowledge_type: Optional[KnowledgeType] = None,
        product_code: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search_mode: str = "hybrid",       # hybrid / semantic / fulltext
        top_k: int = 20,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict], int]:
        """
        混合检索入口。
        search_mode:
          - hybrid：语义 + 全文 融合（默认，推荐）
          - semantic：仅语义检索
          - fulltext：仅全文检索
        返回 (结果列表, 总数)。
        """
        ...

    def get_product_spec(self, product_code: str, version: Optional[str] = None) -> Optional[Dict]:
        """获取指定产品的规格书（类型过滤的快捷方法）。"""
        ...

    def get_sla_standard(self, service_level: str, product_code: Optional[str] = None) -> Optional[Dict]:
        """获取指定服务等级的 SLA 标准。"""
        ...

    def get_contract_clause_template(
        self,
        clause_type: str,
        product_code: Optional[str] = None,
    ) -> Optional[Dict]:
        """获取合同条款模板。"""
        ...

    def get_troubleshooting_faq(
        self,
        query: str,
        product_code: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """
        故障排查 FAQ 语义检索（优化版）。
        针对 FAQ 场景优化：问题 + 答案 联合 embedding，
        相似度阈值更高（≥0.75），返回更精准的结果。
        """
        ...

    # ===== 批量操作 =====

    def batch_import(
        self,
        items: List[Dict],
        knowledge_type: KnowledgeType,
        importer: str,
        auto_publish: bool = False,
    ) -> Tuple[int, int, List[str]]:
        """
        批量导入知识。
        返回 (成功数, 失败数, 失败详情列表)。
        """
        ...

    def batch_update_tags(self, knowledge_ids: List[str], tags: List[str], operator: str) -> int:
        """批量更新标签。"""
        ...
```

### 3.2 EmbeddingProvider（向量生成器）

```python
from typing import List, Optional
import numpy as np


class EmbeddingProvider:
    """
    Embedding 提供者：封装 L2 Memory-009 的本地 GGUF embedding。
    模型：embeddinggemma-300m-qat-Q8_0.gguf
    维度：768
    部署：本地 Node.js llama.cpp provider（@openclaw/llama-cpp-provider）
    调用方式：通过 HTTP 接口调用本地 embedding 服务
    """

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8787/embedding",
        model_path: str = "~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf",
        dim: int = 768,
        batch_size: int = 32,
    ):
        self.endpoint = endpoint
        self.model_path = model_path
        self.dim = dim
        self.batch_size = batch_size
        self._model_loaded = False

    def embed(self, text: str) -> np.ndarray:
        """
        生成单条文本的 embedding 向量。

        实现细节：
        1. 文本预处理：去除多余空白、截断超长文本（max_tokens=512）
        2. 调用本地 embedding 服务 HTTP POST /embedding
        3. 返回 768 维 float32 numpy 数组
        4. L2 归一化（便于 cosine = dot product）

        Args:
            text: 输入文本（中文/英文均可）

        Returns:
            np.ndarray shape (768,), dtype float32, L2 normalized
        """
        ...

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        批量生成 embedding。
        按 batch_size 分批调用，避免一次性发送过多文本。

        Args:
            texts: 文本列表

        Returns:
            np.ndarray shape (N, 768), dtype float32, L2 normalized
        """
        ...

    def cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """
        计算两个向量的余弦相似度。
        因向量已 L2 归一化，直接点积即可。

        Returns:
            float ∈ [-1, 1]，越接近 1 越相似
        """
        return float(np.dot(vec_a, vec_b))

    def semantic_search(
        self,
        query_vec: np.ndarray,
        candidate_vecs: np.ndarray,
        top_k: int = 20,
        threshold: float = 0.5,
    ) -> List[Tuple[int, float]]:
        """
        批量语义检索：从候选向量中找出与查询最相似的 Top-K。

        实现方式：矩阵乘法（向量化，性能高）
        scores = candidate_vecs @ query_vec  # shape (N,)

        Args:
            query_vec: 查询向量 (768,)
            candidate_vecs: 候选向量矩阵 (M, 768)
            top_k: 返回数量
            threshold: 相似度阈值，低于此值的结果被过滤

        Returns:
            [(index, score), ...]，按相似度降序排列
        """
        ...
```

### 3.3 SearchEngine（检索引擎）

```python
from typing import List, Dict, Tuple, Optional


class SearchEngine:
    """
    混合检索引擎：协调全文检索 + 语义检索 + 过滤 + 重排。
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        fts_connection,  # SQLite 连接（含 FTS5 虚拟表）
        db_connection,   # 主库连接
    ):
        self.embedding = embedding_provider
        self.fts = fts_connection
        self.db = db_connection

    def fulltext_search(
        self,
        query: str,
        knowledge_type: Optional[str] = None,
        product_code: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 50,
    ) -> List[Dict]:
        """
        全文检索（SQLite FTS5 + BM25）。

        步骤：
        1. 中文分词（jieba 或 simple 分词器）
        2. 构造 FTS5 MATCH 查询
        3. 按 bm25() 得分排序
        4. 关联 kb_item 表过滤类型/产品/标签
        5. 返回 Top-K 结果（含得分）

        Returns:
            [{id, title, snippet, bm25_score, type, product_code}, ...]
        """
        ...

    def semantic_search(
        self,
        query: str,
        knowledge_type: Optional[str] = None,
        product_code: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 50,
    ) -> List[Dict]:
        """
        语义检索（向量相似度）。

        步骤：
        1. 生成查询 embedding
        2. 从 kb_item_embedding 表加载候选向量（先按过滤条件缩小范围）
        3. 计算 cosine similarity
        4. 返回 Top-K 结果（含相似度得分）

        Returns:
            [{id, title, semantic_score, type, product_code}, ...]
        """
        ...

    def hybrid_search(
        self,
        query: str,
        knowledge_type: Optional[str] = None,
        product_code: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_k: int = 20,
        semantic_weight: float = 0.6,
        fulltext_weight: float = 0.4,
    ) -> List[Dict]:
        """
        混合检索：语义 + 全文 融合。

        融合策略（Reciprocal Rank Fusion, RRF）：
        score(d) = Σ 1 / (k + rank_i(d))
        k=60（经验值）

        也支持线性加权（需归一化得分）：
        final_score = semantic_weight * normalized_semantic_score
                    + fulltext_weight * normalized_bm25_score

        Args:
            semantic_weight: 语义检索权重（默认 0.6）
            fulltext_weight: 全文检索权重（默认 0.4）

        Returns:
            [{id, title, final_score, bm25_score, semantic_score,
              type, product_code, tags, snippet}, ...]
        """
        # 1. 分别检索
        ft_results = self.fulltext_search(
            query, knowledge_type, product_code, tags, top_k=50
        )
        sem_results = self.semantic_search(
            query, knowledge_type, product_code, tags, top_k=50
        )

        # 2. 构造 id → 得分映射
        ft_scores = {r["id"]: r["bm25_score"] for r in ft_results}
        sem_scores = {r["id"]: r["semantic_score"] for r in sem_results}

        # 3. 归一化 + 加权融合
        all_ids = set(ft_scores.keys()) | set(sem_scores.keys())
        fused = []
        for kid in all_ids:
            # 归一化（min-max scaling）
            ft_norm = self._min_max_norm(ft_scores.get(kid, 0), ft_scores)
            sem_norm = self._min_max_norm(sem_scores.get(kid, 0), sem_scores)
            # 加权融合
            final = semantic_weight * sem_norm + fulltext_weight * ft_norm
            fused.append({
                "id": kid,
                "final_score": final,
                "bm25_score": ft_scores.get(kid, 0),
                "semantic_score": sem_scores.get(kid, 0),
            })

        # 4. 排序 + 截断
        fused.sort(key=lambda x: x["final_score"], reverse=True)
        top_results = fused[:top_k]

        # 5. 补全元数据
        return self._enrich_metadata(top_results)

    def _min_max_norm(self, value: float, scores: Dict[str, float]) -> float:
        """Min-Max 归一化到 [0, 1]。"""
        if not scores:
            return 0.0
        min_s, max_s = min(scores.values()), max(scores.values())
        if max_s == min_s:
            return 1.0 if value > 0 else 0.0
        return (value - min_s) / (max_s - min_s)
```

### 3.4 KnowledgeImporter（知识导入器）

```python
from typing import List, Dict, Tuple
import os
import re
import markdown


class KnowledgeImporter(BaseImporter):
    """
    知识导入器：支持 Markdown 文件导入 / 批量 JSON 导入 / 手动录入。
    继承 BaseImporter 框架。
    """

    def import_markdown_file(
        self,
        file_path: str,
        knowledge_type: str,
        product_code: Optional[str] = None,
        tags: Optional[List[str]] = None,
        author: str = "import",
        auto_publish: bool = False,
    ) -> str:
        """
        导入单个 Markdown 文件作为知识条目。

        解析规则：
        - 文件名（去掉 .md）作为默认标题
        - 文件第一行 # 标题 覆盖默认标题
        - Front Matter（--- ... ---）解析为元数据（title / tags / product / ...）
        - 剩余内容作为知识正文

        Returns:
            新建的 knowledge_id
        """
        # 读取文件
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # 解析 Front Matter
        metadata, content = self._parse_front_matter(raw)

        # 提取标题
        title = metadata.get("title") or self._extract_first_heading(content) \
            or os.path.splitext(os.path.basename(file_path))[0]

        # 合并标签
        all_tags = list(set((tags or []) + metadata.get("tags", [])))

        # 创建知识条目
        return KnowledgeBaseService().create_knowledge(
            knowledge_type=knowledge_type,
            title=title,
            content=content,
            product_code=product_code or metadata.get("product"),
            tags=all_tags,
            metadata=metadata,
            author=author,
        )

    def import_markdown_directory(
        self,
        dir_path: str,
        knowledge_type: str,
        recursive: bool = True,
        **kwargs,
    ) -> Tuple[int, int, List[str]]:
        """
        批量导入一个目录下的所有 Markdown 文件。

        Returns:
            (成功数, 失败数, 失败详情)
        """
        ...

    def import_json_batch(
        self,
        json_path: str,
        knowledge_type: Optional[str] = None,
        **kwargs,
    ) -> Tuple[int, int, List[str]]:
        """
        从 JSON 文件批量导入。
        JSON 格式：[{"title": "...", "content": "...", "tags": [...], ...}, ...]
        """
        ...

    def _parse_front_matter(self, text: str) -> Tuple[Dict, str]:
        """
        解析 YAML Front Matter。
        返回 (metadata_dict, content_without_front_matter)
        """
        if not text.startswith("---"):
            return {}, text
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if not match:
            return {}, text
        # 简单 YAML 解析（仅支持 key: value 单行格式）
        meta = {}
        for line in match.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if v.startswith("[") and v.endswith("]"):
                    v = [x.strip() for x in v[1:-1].split(",")]
                meta[k] = v
        return meta, match.group(2)

    def _extract_first_heading(self, text: str) -> Optional[str]:
        """提取 Markdown 中第一个一级标题。"""
        for line in text.split("\n"):
            if line.startswith("# "):
                return line[2:].strip()
        return None
```

---

## 4 数据模型

### 4.1 表清单

| 表名 | 中文名 | 说明 |
|---|---|---|
| `kb_item` | 知识条目主表 | 知识基本信息、类型、状态、内容 |
| `kb_version` | 知识版本表 | 每个知识的历史版本快照 |
| `kb_tag` | 标签表 | 标签字典 |
| `kb_item_tag` | 知识-标签关联表 | 多对多关联 |
| `kb_item_embedding` | 知识向量表 | 每个知识最新版本的 embedding 向量 |
| `kb_fts` | 全文检索虚拟表 | SQLite FTS5 虚拟表（内容索引） |
| `kb_review_log` | 审核日志表 | 审核记录留痕 |

### 4.2 kb_item（知识条目主表）

```sql
CREATE TABLE kb_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 业务唯一标识（UUID）
    kb_id TEXT NOT NULL UNIQUE,

    -- 知识类型
    knowledge_type TEXT NOT NULL CHECK (knowledge_type IN (
        'product_spec', 'service_sla', 'deploy_manual',
        'acceptance_std', 'contract_clause', 'pricing_ref', 'trouble_faq'
    )),

    -- 标题
    title TEXT NOT NULL,

    -- 内容（Markdown 格式，最长约 100KB）
    content TEXT NOT NULL DEFAULT '',

    -- 摘要（自动生成或手动填写，用于搜索结果展示）
    summary TEXT DEFAULT '',

    -- 关联产品编码（关联 master_data 中的产品字典）
    product_code TEXT DEFAULT '',

    -- 服务等级（适用于 SLA 类型）
    service_level TEXT DEFAULT '',

    -- 适用版本（产品版本号，如 "v2.0", "v2.1"）
    applicable_version TEXT DEFAULT '',

    -- 状态
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'pending', 'published', 'rejected', 'archived', 'deleted'
    )),

    -- 当前版本号（每次发布自增）
    current_version INTEGER NOT NULL DEFAULT 0,

    -- 最新发布版本号（0 表示从未发布）
    published_version INTEGER NOT NULL DEFAULT 0,

    -- 作者
    author TEXT NOT NULL DEFAULT '',

    -- 最后编辑者
    last_editor TEXT NOT NULL DEFAULT '',

    -- 审核人
    reviewer TEXT DEFAULT '',

    -- 审核意见
    review_comment TEXT DEFAULT '',

    -- 浏览次数
    view_count INTEGER NOT NULL DEFAULT 0,

    -- 引用次数（被业务模块引用的次数）
    reference_count INTEGER NOT NULL DEFAULT 0,

    -- 点赞/有用 次数
    helpful_count INTEGER NOT NULL DEFAULT 0,

    -- 扩展元数据（JSON 格式，存各类型特有字段）
    metadata TEXT DEFAULT '{}',

    -- 时间戳
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT DEFAULT '',
    archived_at TEXT DEFAULT '',
    deleted_at TEXT DEFAULT ''
);

-- 索引
CREATE INDEX idx_kb_item_type ON kb_item(knowledge_type);
CREATE INDEX idx_kb_item_status ON kb_item(status);
CREATE INDEX idx_kb_item_product ON kb_item(product_code);
CREATE INDEX idx_kb_item_type_status ON kb_item(knowledge_type, status);
CREATE INDEX idx_kb_item_created ON kb_item(created_at DESC);
CREATE INDEX idx_kb_item_updated ON kb_item(updated_at DESC);
```

### 4.3 kb_version（知识版本表）

```sql
CREATE TABLE kb_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 关联知识条目
    kb_id TEXT NOT NULL,

    -- 版本号（从 1 开始，每次发布 +1）
    version INTEGER NOT NULL,

    -- 该版本的内容快照
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    summary TEXT DEFAULT '',
    product_code TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',

    -- 版本状态
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'published', 'archived', 'rejected'
    )),

    -- 变更说明（changelog）
    change_note TEXT DEFAULT '',

    -- 发布人
    publisher TEXT DEFAULT '',

    -- 时间戳
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    published_at TEXT DEFAULT '',

    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE,
    UNIQUE(kb_id, version)
);

CREATE INDEX idx_kb_version_kb_id ON kb_version(kb_id);
CREATE INDEX idx_kb_version_status ON kb_version(status);
```

### 4.4 kb_tag + kb_item_tag（标签系统）

```sql
-- 标签字典表
CREATE TABLE kb_tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name TEXT NOT NULL UNIQUE,
    tag_category TEXT DEFAULT 'general',  -- general / product / domain / custom
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 知识-标签多对多关联
CREATE TABLE kb_item_tag (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES kb_tag(id) ON DELETE CASCADE,
    UNIQUE(kb_id, tag_id)
);

CREATE INDEX idx_kb_item_tag_kb ON kb_item_tag(kb_id);
CREATE INDEX idx_kb_item_tag_tag ON kb_item_tag(tag_id);
```

### 4.5 kb_item_embedding（知识向量表）

```sql
CREATE TABLE kb_item_embedding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 关联知识条目
    kb_id TEXT NOT NULL UNIQUE,

    -- 对应的版本号
    version INTEGER NOT NULL DEFAULT 0,

    -- 标题向量（768 维，以 JSON 数组存储 float32）
    -- 注：SQLite 无原生向量类型，用 BLOB 存储二进制
    title_embedding BLOB NOT NULL,

    -- 内容向量（768 维，取内容前 512 token 生成）
    content_embedding BLOB NOT NULL,

    -- 联合向量（标题 + 摘要 + 内容前 N 字 的加权组合）
    combined_embedding BLOB NOT NULL,

    -- 模型标识（用于模型升级时判断是否需要重新生成）
    model_version TEXT NOT NULL DEFAULT 'embeddinggemma-300m-qat-Q8_0',

    -- 向量维度（冗余字段，便于校验）
    dim INTEGER NOT NULL DEFAULT 768,

    -- 生成时间
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE
);

CREATE INDEX idx_kb_embed_kb_id ON kb_item_embedding(kb_id);
CREATE INDEX idx_kb_embed_model ON kb_item_embedding(model_version);
```

**向量存储说明**：
- 向量以 `BLOB` 存储，格式为 `float32` 小端序连续字节（768 × 4 = 3072 字节/向量）
- Python 端使用 `numpy.ndarray.tobytes()` 写入，`np.frombuffer(..., dtype=np.float32)` 读取
- 检索时先按过滤条件（类型/产品/标签）从数据库取出候选向量，再在内存中计算相似度
- 数据量 < 10000 条时，内存计算完全够用（毫秒级）

### 4.6 kb_fts（FTS5 全文检索虚拟表）

```sql
-- FTS5 全文检索虚拟表
CREATE VIRTUAL TABLE kb_fts USING fts5(
    kb_id UNINDEXED,        -- 关联 kb_item.kb_id，不索引
    title,                   -- 标题（权重最高）
    summary,                 -- 摘要
    content,                 -- 正文内容
    tags,                    -- 标签名（空格分隔）
    product_name,            -- 产品名称（冗余，便于检索）

    -- 配置
    tokenize = 'unicode61 remove_diacritics 2',
    -- 使用 unicode61 分词器 + 去变音符号
    -- 中文分词：在应用层先做 jieba 分词，再写入 FTS5
    content = ''             -- 外部内容表（手动同步）
);

-- FTS5 不支持传统索引，依赖自身倒排索引
```

**FTS5 使用说明**：
- 中文检索采用 **应用层分词 + FTS5** 的方案：写入时先 jieba 分词，分词结果以空格分隔写入 FTS5 表
- 查询时同样先分词，再构造 FTS5 MATCH 查询
- 排序使用 `bm25(kb_fts)` 内置函数
- `title` 字段权重设置为 3.0，`summary` 为 2.0，`content` 为 1.0，`tags` 为 1.5

### 4.7 kb_review_log（审核日志表）

```sql
CREATE TABLE kb_review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    action TEXT NOT NULL,  -- submit / approve / reject / publish / archive / restore / delete
    operator TEXT NOT NULL,
    comment TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (kb_id) REFERENCES kb_item(kb_id) ON DELETE CASCADE
);

CREATE INDEX idx_kb_review_kb ON kb_review_log(kb_id);
CREATE INDEX idx_kb_review_action ON kb_review_log(action);
CREATE INDEX idx_kb_review_created ON kb_review_log(created_at DESC);
```

### 4.8 ER 关系图

```
kb_item (主表)
    │
    ├── 1:N → kb_version (版本历史)
    │
    ├── 1:1 → kb_item_embedding (向量索引)
    │
    ├── 1:1 → kb_fts (全文索引，虚拟表)
    │
    ├── M:N → kb_item_tag → kb_tag (标签)
    │
    └── 1:N → kb_review_log (审核日志)
```

---

## 5 语义检索实现

### 5.1 接入 L2 Memory-009

知识库复用 L2 Memory-009 的本地 GGUF embedding 能力，具体集成方式：

| 项目 | 配置 |
|---|---|
| 模型文件 | `~/.node-llama-cpp/models/hf_ggml-org_embeddinggemma-300m-qat-Q8_0.gguf` |
| 模型维度 | 768 维 |
| 量化方式 | QAT-Q8_0 |
| 推理引擎 | llama.cpp（Node.js 绑定：`@openclaw/llama-cpp-provider`） |
| 服务方式 | 本地 HTTP 服务（默认端口 8787） |
| 最大 token 数 | 512 tokens（约 300-400 中文字符） |
| 预期性能 | 单条 embedding ~20ms，批量 32 条 ~150ms |

### 5.2 Embedding 调用接口

**本地 Embedding 服务 API**：

```
POST /embedding
Content-Type: application/json

{
    "texts": ["文本1", "文本2", ...],
    "model": "embeddinggemma-300m-qat-Q8_0"
}

Response:
{
    "embeddings": [
        [0.0123, -0.0456, ...],  // 768 维
        ...
    ],
    "model": "embeddinggemma-300m-qat-Q8_0",
    "dim": 768
}
```

**Python 调用示例**：

```python
import requests
import numpy as np


class LocalEmbeddingClient:
    """本地 Embedding 服务客户端。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8787"):
        self.base_url = base_url
        self._session = requests.Session()

    def embed_text(self, text: str) -> np.ndarray:
        """生成单条文本的 embedding。"""
        resp = self._session.post(
            f"{self.base_url}/embedding",
            json={"texts": [text]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        vec = np.array(data["embeddings"][0], dtype=np.float32)
        # L2 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """批量生成 embedding。"""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self._session.post(
                f"{self.base_url}/embedding",
                json={"texts": batch},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            batch_vecs = np.array(data["embeddings"], dtype=np.float32)
            # L2 归一化（向量化）
            norms = np.linalg.norm(batch_vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            batch_vecs = batch_vecs / norms
            all_embeddings.append(batch_vecs)
        return np.vstack(all_embeddings) if all_embeddings else np.array(
            [], dtype=np.float32
        ).reshape(0, 768)
```

### 5.3 向量相似度计算

```python
import numpy as np


def cosine_similarity_matrix(query_vec: np.ndarray, candidate_vecs: np.ndarray) -> np.ndarray:
    """
    计算查询向量与所有候选向量的余弦相似度。
    向量已 L2 归一化，直接矩阵乘法。

    Args:
        query_vec: shape (768,)
        candidate_vecs: shape (N, 768)

    Returns:
        shape (N,)，每个候选的相似度 ∈ [-1, 1]
    """
    return candidate_vecs @ query_vec


def semantic_search(
    query_vec: np.ndarray,
    candidate_ids: List[int],
    candidate_vecs: np.ndarray,
    top_k: int = 20,
    threshold: float = 0.5,
) -> List[Tuple[int, float]]:
    """
    语义检索：返回 Top-K 最相似结果。

    Args:
        query_vec: 查询向量 (768,)
        candidate_ids: 候选 ID 列表（与 candidate_vecs 一一对应）
        candidate_vecs: 候选向量矩阵 (N, 768)
        top_k: 返回数量
        threshold: 相似度阈值

    Returns:
        [(id, score), ...]，按分数降序
    """
    if len(candidate_ids) == 0:
        return []

    # 计算相似度
    scores = cosine_similarity_matrix(query_vec, candidate_vecs)

    # 过滤阈值
    mask = scores >= threshold
    filtered_ids = [candidate_ids[i] for i in range(len(candidate_ids)) if mask[i]]
    filtered_scores = scores[mask]

    if len(filtered_ids) == 0:
        return []

    # 排序（降序）
    sorted_indices = np.argsort(-filtered_scores)
    top_indices = sorted_indices[:top_k]

    return [(filtered_ids[i], float(filtered_scores[i])) for i in top_indices]
```

### 5.4 文本分段策略

长文档（如部署手册可能上万字）无法一次性 embedding（最大 512 tokens），采用分段策略：

```
长文本切分策略：
┌─────────────────────────────────────────────┐
│  完整文档（deploy_manual 类型，约 5000 字）    │
└───────────────┬─────────────────────────────┘
                │
                ▼
        按章节/段落切分（chunk_size=300字，overlap=50字）
                │
                ▼
        ┌─────┬─────┬─────┬─────┬─────┐
        │chunk│chunk│chunk│chunk│chunk│  ← 每个 chunk 独立 embedding
        │  1  │  2  │  3  │  4  │  5  │
        └──┬──┴──┬──┴──┬──┴──┬──┴──┬──┘
           │     │     │     │     │
           └─────┴─────┼─────┴─────┘
                       ▼
              取均值 = 文档整体向量（存入 kb_item_embedding.combined_embedding）
              同时保留 chunk 级向量（用于细粒度检索，可选）
```

**分段参数**：

| 参数 | 值 | 说明 |
|---|---|---|
| chunk_size | 300 字 | 每段约 300 个中文字符 |
| chunk_overlap | 50 字 | 相邻段重叠 50 字，保证语义连续 |
| 分段方式 | 智能分段 | 优先按章节标题（## / ###）分段，不足再按段落 |
| 最大 chunks | 20 段 | 单篇文档最多切 20 段，超出则取首尾 |

### 5.5 向量索引方案选型

当前阶段（知识库规模 < 10000 条）使用**内存计算**方案，无需引入向量数据库。

| 方案 | 适用规模 | 复杂度 | 延迟 |
|---|---|---|---|
| 内存 numpy 计算 | < 10,000 条 | 低 | ~10ms |
| SQLite + 自定义函数 | < 50,000 条 | 中 | ~50ms |
| Faiss / Annoy | 10万 ~ 1000万 | 中 | ~1ms |
| Milvus / Qdrant | > 1000万 | 高 | ~1ms |

**演进路径**：
- Phase 1：内存计算（当前）
- Phase 2：数据量超过 1 万条 → 引入 Faiss（本地索引文件）
- Phase 3：数据量超过 100 万条 → 引入向量数据库（Milvus / Qdrant）

---

## 6 全文检索实现

### 6.1 SQLite FTS5 方案选型

| 方案 | 优点 | 缺点 | 选型结论 |
|---|---|---|---|
| SQLite FTS5 | 零依赖、内置、BM25 排序、支持前缀/短语查询 | 中文分词需额外处理 | ✅ 选用（符合 L2 Persistence-006） |
| Elasticsearch | 功能强大、中文支持好 | 重、需独立部署、运维成本高 | ❌ 过重 |
| Meilisearch | 轻量、中文支持好 | 需独立进程、资源占用 | ❌ 暂不需要 |
| Whoosh (Python) | 纯 Python、易集成 | 性能一般、与 SQLite 分开维护 | ❌ 一致性差 |

### 6.2 中文分词方案

FTS5 自带的 `unicode61` 分词器按 Unicode 字符类分词，对中文是逐字切分，效果不佳。采用**应用层 jieba 分词 + FTS5 存储**的方案：

```
写入流程：
  原始文本 → jieba 分词（精确模式）→ 空格拼接 → 写入 FTS5 表

查询流程：
  查询词 → jieba 分词（精确模式）→ 构造 FTS5 MATCH 语法 → 查询 FTS5
```

**分词配置**：

```python
import jieba

# 加载自定义词典（安全服务行业术语）
jieba.load_userdict("kb_sec_terms.txt")
# 示例内容：
#   等保测评 5 n
#   渗透测试 5 n
#   漏洞扫描 5 n
#   SLA 5 n
#   SOC 3 n

def tokenize(text: str) -> str:
    """中文分词，返回空格分隔的字符串。"""
    words = jieba.lcut(text, cut_all=False)
    # 过滤纯空白和单字（可选，根据效果调整）
    words = [w.strip() for w in words if w.strip() and len(w.strip()) > 1]
    return " ".join(words)
```

### 6.3 FTS5 查询构造

```python
def build_fts_query(query_text: str) -> str:
    """
    构造 FTS5 MATCH 查询字符串。
    策略：
    1. 分词后每个词用 AND 连接（必须全部出现）
    2. 最后一个词加前缀匹配（支持输入联想）
    3. 支持短语查询（用引号包裹）
    """
    tokens = jieba.lcut(query_text, cut_all=False)
    tokens = [t.strip() for t in tokens if t.strip()]

    if not tokens:
        return ""

    parts = []
    for i, token in enumerate(tokens):
        # 转义特殊字符
        token = token.replace('"', '""')
        if i == len(tokens) - 1 and len(token) > 1:
            # 最后一个 token 加前缀匹配
            parts.append(f'"{token}"*')
        else:
            parts.append(f'"{token}"')

    # 全部 AND
    return " AND ".join(parts)


def fulltext_search(
    conn,
    query_text: str,
    knowledge_type: str = None,
    top_k: int = 20,
) -> List[Dict]:
    """
    全文检索示例。

    SELECT
        f.kb_id,
        k.title,
        k.knowledge_type,
        k.product_code,
        bm25(kb_fts) AS score,
        snippet(kb_fts, 2, '<mark>', '</mark>', '...', 30) AS snippet
    FROM kb_fts f
    JOIN kb_item k ON f.kb_id = k.kb_id
    WHERE kb_fts MATCH ?
      AND k.status = 'published'
      [AND k.knowledge_type = ?]
    ORDER BY bm25(kb_fts)
    LIMIT ?
    """
    fts_query = build_fts_query(query_text)
    if not fts_query:
        return []

    params = [fts_query]
    sql = """
        SELECT
            f.kb_id,
            k.title,
            k.knowledge_type,
            k.product_code,
            bm25(kb_fts) AS score,
            snippet(kb_fts, 2, '<mark>', '</mark>', '...', 30) AS snippet
        FROM kb_fts f
        JOIN kb_item kb ON f.kb_id = k.kb_id
        WHERE kb_fts MATCH ?
          AND k.status = 'published'
    """
    if knowledge_type:
        sql += " AND k.knowledge_type = ?"
        params.append(knowledge_type)
    sql += " ORDER BY bm25(kb_fts) LIMIT ?"
    params.append(top_k)

    cursor = conn.execute(sql, params)
    return [dict(row) for row in cursor.fetchall()]
```

### 6.4 BM25 权重配置

FTS5 的 BM25 支持为不同列设置权重，通过 `bm25(table, w0, w1, w2, ...)` 指定：

```sql
-- 列顺序：kb_id(0), title(1), summary(2), content(3), tags(4), product_name(5)
-- 权重：title=3.0, summary=2.0, content=1.0, tags=1.5, product_name=2.0
SELECT * FROM kb_fts
WHERE kb_fts MATCH '等保测评'
ORDER BY bm25(kb_fts, 0.0, 3.0, 2.0, 1.0, 1.5, 2.0)
LIMIT 20;
```

### 6.5 FTS5 同步机制

知识内容变更时，需要同步更新 FTS5 索引：

```python
def sync_fts(conn, kb_id: str, action: str = "upsert"):
    """
    同步 FTS5 索引。
    action: upsert / delete
    """
    if action == "delete":
        conn.execute("DELETE FROM kb_fts WHERE kb_id = ?", (kb_id,))
        return

    # 从主表读取最新数据
    row = conn.execute(
        "SELECT title, summary, content, product_code FROM kb_item WHERE kb_id = ?",
        (kb_id,)
    ).fetchone()

    # 获取标签名
    tag_rows = conn.execute("""
        SELECT t.tag_name FROM kb_tag t
        JOIN kb_item_tag it ON t.id = it.tag_id
        WHERE it.kb_id = ?
    """, (kb_id,)).fetchall()
    tags_str = " ".join([r[0] for r in tag_rows])

    # 分词
    title_tokens = tokenize(row["title"])
    summary_tokens = tokenize(row["summary"] or "")
    content_tokens = tokenize(row["content"][:5000])  # 只索引前 5000 字
    product_name = row["product_code"]  # 产品名从主数据查，简化处理

    # upsert FTS5
    conn.execute("DELETE FROM kb_fts WHERE kb_id = ?", (kb_id,))
    conn.execute("""
        INSERT INTO kb_fts (kb_id, title, summary, content, tags, product_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (kb_id, title_tokens, summary_tokens, content_tokens, tags_str, product_name))
```

**同步触发时机**：
- 创建知识 → 写入 FTS5
- 更新知识 → 更新 FTS5（仅已发布版本）
- 发布知识 → 写入/更新 FTS5
- 归档/删除知识 → 从 FTS5 移除
- 批量导入 → 事务内批量写入

---

## 7 混合检索策略

### 7.1 融合算法选型

| 融合算法 | 原理 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| **RRF (Reciprocal Rank Fusion)** | `score = Σ 1/(k + rank)` | 无需归一化、鲁棒性好 | 不考虑得分绝对值 | 异构检索系统融合 |
| 线性加权 | `score = w1*s1 + w2*s2` | 简单直观、权重可调 | 需归一化、权重难调 | 得分分布已知时 |
| 加权乘 | `score = s1^a * s2^b` | 强调共同命中 | 极端值敏感 | 两者都重要时 |

**选型结论**：Phase 1 使用 **RRF**（鲁棒、无需调参），Phase 2 可切换为线性加权（权重可配置）。

### 7.2 RRF 融合实现

```python
def rrf_fuse(
    ranked_lists: List[List[Tuple[str, float]]],
    k: int = 60,
    top_k: int = 20,
) -> List[Tuple[str, float]]:
    """
    Reciprocal Rank Fusion 融合多个排好序的结果列表。

    Args:
        ranked_lists: 多个有序列表，每项为 (id, raw_score)
        k: RRF 常数，经验值 60
        top_k: 返回 Top-K

    Returns:
        [(id, fused_score), ...]，按融合分数降序
    """
    scores = {}  # id -> fused_score

    for ranked_list in ranked_lists:
        for rank, (item_id, _) in enumerate(ranked_list, start=1):
            rrf_score = 1.0 / (k + rank)
            scores[item_id] = scores.get(item_id, 0.0) + rrf_score

    # 排序
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused[:top_k]


# 使用示例
def hybrid_search_rrf(query: str, top_k: int = 20) -> List[Dict]:
    """
    混合检索（RRF 融合）。
    """
    # 1. 全文检索（按 BM25 排序，取 Top-50）
    ft_results = fulltext_search(query, top_k=50)  # [(id, bm25_score), ...]
    ft_ranked = [(r["kb_id"], r["score"]) for r in ft_results]

    # 2. 语义检索（按相似度排序，取 Top-50）
    sem_results = semantic_search(query, top_k=50)  # [(id, semantic_score), ...]
    sem_ranked = [(r[0], r[1]) for r in sem_results]

    # 3. RRF 融合
    fused = rrf_fuse([ft_ranked, sem_ranked], k=60, top_k=top_k)

    # 4. 补全元数据
    return enrich_results(fused)
```

### 7.3 多层过滤流水线

混合检索不仅是结果融合，还包括多层过滤：

```
查询输入
    │
    ▼
┌─────────────┐
│ 预处理层     │  分词 / 生成 embedding / 提取过滤条件
└──────┬──────┘
       │
       ├──────────────┐
       ▼              ▼
┌───────────┐  ┌───────────┐
│ 全文检索  │  │ 语义检索  │
│ (FTS5)    │  │ (向量)    │
│ Top-100   │  │ Top-100   │
└─────┬─────┘  └─────┬─────┘
      │              │
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │ 结果融合层     │  RRF / 线性加权
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │ 过滤层        │  状态过滤（仅 published）
      │              │  类型过滤（按 knowledge_type）
      │              │  产品过滤（按 product_code）
      │              │  标签过滤（按 tags）
      │              │  版本过滤（按 applicable_version）
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │ 重排层        │  业务权重调整
      │              │  - 高引用优先（reference_count）
      │              │  - 高好评优先（helpful_count）
      │              │  - 时效性加权（越新越优先）
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │ 分页输出      │  page / page_size
      └──────────────┘
```

### 7.4 重排（Rerank）策略

```python
def rerank(results: List[Dict]) -> List[Dict]:
    """
    业务重排：在融合得分基础上，叠加业务权重。

    调整因子：
    - 引用次数：log(reference_count + 1) * 0.05
    - 好评率：helpful_count / (view_count + 1) * 0.03
    - 时效性：exp(-days_since_publish / 365) * 0.02

    总调整幅度控制在 ±10% 以内，避免喧宾夺主。
    """
    import math
    from datetime import datetime

    for r in results:
        score = r["final_score"]
        boost = 1.0

        # 引用次数权重
        ref_boost = math.log(r.get("reference_count", 0) + 1) * 0.05
        boost += ref_boost

        # 好评率权重
        view = r.get("view_count", 0)
        helpful = r.get("helpful_count", 0)
        if view > 0:
            helpful_rate = helpful / (view + 1)
            boost += helpful_rate * 0.03

        # 时效性权重（越新越高）
        if r.get("published_at"):
            pub_date = datetime.fromisoformat(r["published_at"])
            days = (datetime.now() - pub_date).days
            time_boost = math.exp(-days / 365) * 0.02
            boost += time_boost

        # 限制调整范围 ±10%
        boost = max(0.9, min(1.1, boost))
        r["final_score"] = score * boost
        r["boost_factor"] = boost

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results
```

---

## 8 知识生命周期管理

### 8.1 状态机

```
         创建              提交审核           审核通过
  ───────────────► ───────────────► ───────────────►
  (draft)           (pending)         (published)
                      │                  │  ▲
                      │ 审核驳回          │  │ 更新迭代
                      ▼                  │  │（创建新版本）
                   (rejected)            │  │
                                         │  │
                                    归档 │  │ 恢复
                                         ▼  │
                                      (archived)

  任意状态 ──删除──► (deleted)  软删除，30 天后物理清理
```

### 8.2 版本管理机制

每次发布知识时，版本号递增：

```python
def publish_knowledge(kb_id: str, publisher: str, change_note: str = "") -> int:
    """
    发布知识。

    流程：
    1. 校验当前状态为 pending 或 draft（管理员跳过审核）
    2. current_version + 1 = 新版本号
    3. 将当前内容快照写入 kb_version 表
    4. 更新 kb_item: status=published, published_version=new_ver
    5. 更新 embedding 向量
    6. 同步 FTS5 索引
    7. 记录审核日志
    8. 返回新版本号
    """
    # 伪代码
    item = get_kb_item(kb_id)
    new_version = item["current_version"] + 1

    # 写入版本快照
    insert_kb_version(
        kb_id=kb_id,
        version=new_version,
        title=item["title"],
        content=item["content"],
        summary=item["summary"],
        product_code=item["product_code"],
        metadata=item["metadata"],
        status="published",
        change_note=change_note,
        publisher=publisher,
    )

    # 更新主表
    update_kb_item(
        kb_id,
        status="published",
        current_version=new_version,
        published_version=new_version,
        published_at=now(),
    )

    # 更新索引
    update_embedding(kb_id)
    sync_fts(kb_id, "upsert")

    # 记录日志
    add_review_log(kb_id, new_version, "publish", publisher, change_note)

    return new_version
```

### 8.3 审核流程

```
编辑者                       审核员
  │                            │
  │  1. 创建/编辑知识           │
  │  (status: draft)           │
  │                            │
  │  2. 提交审核               │
  │  ────────────────────────► │
  │  (status: pending)         │
  │                            │  3. 审核
  │                            │
  │  4a. 审核通过              │
  │  ◄──────────────────────── │
  │  (status: published)       │
  │                            │
  │  4b. 审核驳回              │
  │  ◄──────────────────────── │
  │  (status: rejected)        │
  │   附审核意见                │
  │                            │
  │  5. 修改后重新提交          │
  │  ────────────────────────► │
  │  (status: pending)         │
```

审核规则：
- 普通编辑者：创建 → 提交 → 等待审核 → 发布
- 知识库管理员：可直接发布（跳过审核）
- 驳回必须填写理由
- 审核超时 3 天自动提醒审核员

### 8.4 归档与删除

**归档**：
- 知识不再适用但需保留历史记录时使用
- 归档后从默认检索结果中排除
- 可随时恢复为 published 状态
- 归档操作需要管理员权限

**软删除**：
- status 设置为 deleted，从所有检索结果中排除
- 30 天内可恢复
- 30 天后由定时任务物理删除（连同版本/向量/标签关联）

**物理删除**：
- 需超级管理员权限
- 不可恢复
- 连同所有版本、向量、标签关联、审核日志一并删除

---

## 9 各知识类型详细设计

### 9.1 产品规格书（product_spec）

**定位**：描述产品/服务的功能清单、技术参数、部署要求等。

**特有字段（metadata JSON）**：

```json
{
  "product_code": "app-guard-v2",
  "product_name": "应用级防护系统 v2",
  "product_category": "安全产品",
  "version": "2.1.0",
  "specs": {
    "deployment": "私有化部署 / SaaS",
    "os_support": ["CentOS 7+", "Ubuntu 20.04+"],
    "min_hardware": {
      "cpu": "4 核",
      "memory": "8GB",
      "disk": "100GB SSD"
    },
    "supported_browsers": ["Chrome 90+", "Firefox 88+", "Edge 90+"],
    "max_concurrent_users": 500,
    "api_count": 120
  },
  "features": [
    {"name": "Web 应用防护", "description": "..."},
    {"name": "API 安全", "description": "..."}
  ]
}
```

**使用场景**：
- 售前方案编写时检索产品参数
- 项目规划阶段确认部署要求
- 客户咨询时快速调出规格信息

### 9.2 服务 SLA 标准（service_sla）

**定位**：定义不同服务等级的响应时间、解决时效、服务范围等。

**特有字段（metadata JSON）**：

```json
{
  "service_level": "gold",
  "level_name": "金牌服务",
  "response_time": {
    "critical": "15 分钟",
    "high": "30 分钟",
    "medium": "2 小时",
    "low": "8 小时"
  },
  "resolution_time": {
    "critical": "4 小时",
    "high": "24 小时",
    "medium": "3 个工作日",
    "low": "7 个工作日"
  },
  "service_hours": "7x24",
  "support_channels": ["电话", "企业微信", "邮件", "现场"],
  "exclusions": ["客户自行修改代码导致的问题", "第三方软件故障"],
  "escalation_path": ["一线工程师", "二线专家", "研发团队", "高管"]
}
```

**使用场景**：
- 合同签署时引用 SLA 条款
- 售后工单自动匹配 SLA 时效
- 客户查询服务等级时展示

### 9.3 部署实施手册（deploy_manual）

**定位**：产品部署、安装、配置的详细操作指南。

**特有字段（metadata JSON）**：

```json
{
  "product_code": "app-guard-v2",
  "applicable_version": "2.1.0",
  "manual_type": "deploy",  // deploy / upgrade / config / maintain
  "estimated_duration": "2 小时",
  "difficulty": "medium",    // easy / medium / hard
  "prerequisites": [
    "服务器已就位，操作系统已安装",
    "网络已配置，端口已开放",
    "License 已获取"
  ],
  "chapters": [
    {"title": "环境准备", "order": 1},
    {"title": "安装部署", "order": 2},
    {"title": "配置初始化", "order": 3},
    {"title": "验证测试", "order": 4}
  ],
  "related_products": ["db-guard", "auth-gateway"]
}
```

**使用场景**：
- 项目实施阶段工程师操作指南
- 客户自行部署时参考
- 升级操作指导

### 9.4 验收标准（acceptance_std）

**定位**：定义项目/产品的验收项、验收方法、通过准则。

**特有字段（metadata JSON）**：

```json
{
  "product_code": "app-guard-v2",
  "standard_code": "AC-APPGUARD-V2",
  "acceptance_items": [
    {
      "item": "功能验收",
      "method": "功能测试",
      "criteria": "全部 56 项功能点测试通过",
      "weight": 0.4
    },
    {
      "item": "性能验收",
      "method": "压力测试",
      "criteria": "并发 500 用户时响应时间 < 200ms",
      "weight": 0.3
    },
    {
      "item": "文档验收",
      "method": "文档检查",
      "criteria": "交付物齐全，格式符合规范",
      "weight": 0.15
    },
    {
      "item": "培训验收",
      "method": "培训+考核",
      "criteria": "参训人员考核通过率 ≥ 80%",
      "weight": 0.15
    }
  ],
  "deliverables": [
    "部署实施报告",
    "功能测试报告",
    "性能测试报告",
    "用户操作手册",
    "管理员手册"
  ],
  "acceptance_process": [
    "乙方提交验收申请",
    "甲方 3 个工作日内确认",
    "现场验收测试",
    "签署验收报告"
  ]
}
```

**使用场景**：
- 项目验收阶段对照检查
- 合同中引用验收标准条款

### 9.5 合同条款模板（contract_clause）

**定位**：标准化的合同条款模板，供合同起草时引用。

**特有字段（metadata JSON）**：

```json
{
  "clause_type": "service_level",
  "clause_code": "CLAUSE-SLA-001",
  "category": "服务条款",
  "applicable_contract_types": ["服务合同", "年度维护合同"],
  "risk_level": "medium",   // low / medium / high
  "legal_review_required": true,
  "variables": [
    {"name": "service_level", "type": "string", "default": "standard"},
    {"name": "response_time", "type": "string", "default": "4 小时"}
  ],
  "related_laws": ["《民法典》合同编", "《网络安全法》"],
  "last_legal_review_date": "2026-06-01",
  "review_cycle_days": 365
}
```

**使用场景**：
- 合同起草时自动匹配条款模板
- 法务审核时引用标准条款

### 9.6 产品定价参考（pricing_ref）

**定位**：产品指导价、折扣策略、报价模板等价格相关信息。

**特有字段（metadata JSON）**：

```json
{
  "product_code": "app-guard-v2",
  "pricing_model": "subscription",  // subscription / perpetual / usage_based
  "list_price": {
    "annual": 200000,
    "unit": "元/年",
    "currency": "CNY"
  },
  "discount_tiers": [
    {"tier": "strategic", "min_deal": 500000, "discount": 0.50},
    {"tier": "large", "min_deal": 200000, "discount": 0.65},
    {"tier": "standard", "min_deal": 50000, "discount": 0.80},
    {"tier": "small", "min_deal": 0, "discount": 0.95}
  ],
  "pricing_components": [
    {"name": "基础授权费", "proportion": 0.6},
    {"name": "实施服务费", "proportion": 0.25},
    {"name": "年度维护费", "proportion": 0.15}
  ],
  "cost_structure": {
    "license_cost": 0.2,
    "implementation_cost": 0.5,
    "maintenance_cost": 0.3
  }
}
```

**使用场景**：
- 销售报价时查询指导价和折扣权限
- 商务谈判时参考成本结构

### 9.7 故障排查 FAQ（trouble_faq）

**定位**：常见故障、问题的排查和解决方案。

**特有字段（metadata JSON）**：

```json
{
  "product_code": "app-guard-v2",
  "applicable_version": "2.0+",
  "question": "管理后台登录页面打不开，显示 502 错误",
  "severity": "high",
  "category": "系统故障",
  "symptoms": [
    "浏览器显示 502 Bad Gateway",
    "Nginx 日志中有 upstream timed out"
  ],
  "possible_causes": [
    {
      "cause": "后端服务未启动",
      "probability": 0.6,
      "solution_id": "SOL-001"
    },
    {
      "cause": "数据库连接超时",
      "probability": 0.3,
      "solution_id": "SOL-002"
    },
    {
      "cause": "内存不足导致 OOM",
      "probability": 0.1,
      "solution_id": "SOL-003"
    }
  ],
  "solution_steps": [
    "1. 检查后端服务状态：systemctl status app-guard",
    "2. 如未启动，尝试启动服务",
    "3. 检查数据库连接配置",
    "4. 查看系统资源使用情况"
  ],
  "related_faqs": ["FAQ-002", "FAQ-005"],
  "avg_resolution_time_minutes": 15
}
```

**使用场景**：
- 售后工单自动匹配 FAQ，辅助一线工程师快速排障
- 客户自助检索解决方案

---

## 10 知识导入

### 10.1 导入方式对比

| 导入方式 | 适用场景 | 批量大小 | 格式要求 |
|---|---|---|---|
| Markdown 单文件导入 | 单篇文档导入 | 1 篇 | .md 文件，支持 Front Matter |
| Markdown 目录批量导入 | 已有文档库迁移 | 几十~几百篇 | 目录 + .md 文件 |
| JSON 批量导入 | 结构化数据导入 | 几百~几千条 | JSON 数组，每个元素为一条知识 |
| 手动录入（Web/CLI） | 日常维护 | 逐条 | 表单填写 |

### 10.2 Markdown Front Matter 规范

知识型 Markdown 文件统一使用 YAML Front Matter 存储元数据：

```markdown
---
title: 应用级防护系统 v2.1 部署手册
type: deploy_manual
product: app-guard-v2
version: 2.1.0
tags: [部署, 安装, 配置]
author: 技术部
status: draft
difficulty: medium
estimated_duration: 2h
---

# 应用级防护系统 v2.1 部署手册

## 1 环境准备

...
```

### 10.3 批量导入流程

```
批量导入流程：
  1. 读取源文件（目录 / JSON）
  2. 逐条解析 + 校验（必填字段检查、格式校验）
  3. 预生成报告（成功/失败/警告统计）
  4. 用户确认后执行导入
  5. 事务内批量写入数据库
  6. 批量生成 embedding
  7. 批量写入 FTS5
  8. 生成导入结果报告（成功数 / 失败数 / 错误详情）
```

### 10.4 导入校验规则

| 校验项 | 规则 | 不通过处理 |
|---|---|---|
| 必填字段 | title, content, type 不能为空 | 跳过，记录错误 |
| 类型合法性 | type 必须在 7 种类型内 | 跳过，记录错误 |
| 标题长度 | ≤ 200 字 | 截断，记录警告 |
| 内容长度 | ≤ 100KB | 跳过，记录错误 |
| 重复检测 | 同类型 + 同产品 + 同标题 视为重复 | 可选跳过或覆盖 |
| 产品编码 | 存在于 master_data 产品字典 | 警告（可能是新产品） |

---

## 11 与业务模块的集成

### 11.1 项目管理模块集成（project_management）

**集成点**：

| 场景 | 知识类型 | 集成方式 |
|---|---|---|
| 项目启动 | deploy_manual（部署实施手册） | 项目启动时，根据产品类型自动推荐相关部署手册 |
| 项目实施 | deploy_manual / product_spec | 实施工程师可从知识库快速检索操作指南 |
| 项目验收 | acceptance_std（验收标准） | 验收阶段关联验收标准，对照检查 |

**接口示例**：

```python
# 项目启动时推荐相关知识
def get_recommended_knowledge_for_project(project_id: str) -> Dict:
    """
    根据项目类型和关联产品，推荐相关知识。
    """
    project = project_service.get_project(project_id)
    product_code = project.get("product_code")
    project_type = project.get("project_type")

    recommendations = {
        "deploy_manuals": [],
        "product_specs": [],
        "acceptance_stds": [],
    }

    if product_code:
        # 部署手册
        kb = KnowledgeBaseService()
        recommendations["deploy_manuals"] = kb.search(
            query="部署手册",
            knowledge_type="deploy_manual",
            product_code=product_code,
            top_k=3,
        )[0]
        # 产品规格书
        recommendations["product_specs"] = kb.search(
            query="产品规格",
            knowledge_type="product_spec",
            product_code=product_code,
            top_k=2,
        )[0]
        # 验收标准
        recommendations["acceptance_stds"] = kb.search(
            query="验收标准",
            knowledge_type="acceptance_std",
            product_code=product_code,
            top_k=2,
        )[0]

    return recommendations
```

### 11.2 售后管理模块集成（after_sales）

**集成点**：

| 场景 | 知识类型 | 集成方式 |
|---|---|---|
| 工单创建 | trouble_faq（故障排查 FAQ） | 提交工单时，根据标题/描述自动匹配相关 FAQ，推荐给提交者 |
| 工单处理 | trouble_faq / product_spec | 工程师处理工单时，智能推荐相关解决方案 |
| SLA 计算 | service_sla（服务 SLA） | 工单创建时根据服务等级自动计算 SLA 时效 |

**FAQ 自动匹配示例**：

```python
def auto_match_faqs(ticket_title: str, ticket_desc: str, product_code: str = None) -> List[Dict]:
    """
    工单创建时自动匹配 FAQ。

    策略：
    1. 组合标题 + 描述前 200 字作为查询文本
    2. 仅检索 trouble_faq 类型
    3. 相似度阈值设为 0.7（较高，确保推荐质量）
    4. 返回 Top-5 结果
    5. 如果有高置信度匹配（≥0.85），标记为 "推荐解决方案"
    """
    kb = KnowledgeBaseService()
    query = f"{ticket_title} {ticket_desc[:200]}"

    faqs, _ = kb.get_troubleshooting_faq(
        query=query,
        product_code=product_code,
        top_k=5,
    )

    # 标记高置信度
    for faq in faqs:
        if faq.get("semantic_score", 0) >= 0.85:
            faq["confidence"] = "high"
        elif faq.get("semantic_score", 0) >= 0.7:
            faq["confidence"] = "medium"
        else:
            faq["confidence"] = "low"

    return faqs
```

### 11.3 合同管理模块集成（contract_management）

**集成点**：

| 场景 | 知识类型 | 集成方式 |
|---|---|---|
| 合同起草 | contract_clause（合同条款模板） | 起草合同时，根据合同类型推荐相关条款模板 |
| 报价 | pricing_ref（定价参考） | 报价时查询产品指导价和折扣权限 |
| SLA 条款 | service_sla（服务 SLA） | 合同中 SLA 条款从知识库引用，确保一致性 |

**合同条款推荐示例**：

```python
def recommend_contract_clauses(contract_type: str, product_code: str = None) -> List[Dict]:
    """
    根据合同类型推荐条款模板。
    """
    kb = KnowledgeBaseService()
    clauses, _ = kb.search(
        query=contract_type,
        knowledge_type="contract_clause",
        top_k=10,
    )
    return clauses
```

### 11.4 集成架构

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  Project Management │  │   After Sales       │  │ Contract Management │
│     (project_mgmt)  │  │    (after_sales)    │  │  (contract_mgmt)    │
└──────────┬──────────┘  └──────────┬──────────┘  └──────────┬──────────┘
           │                        │                        │
           │    知识查询 / 推荐      │                        │
           └──────────────┬─────────┴───────────┬────────────┘
                          ▼                     ▼
              ┌──────────────────────────────────────────┐
              │         KnowledgeBaseService             │
              │  (统一入口：search / get / recommend)    │
              └──────────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        ┌─────────┐            ┌──────────┐
        │ kb_item │            │ kb_fts   │
        │ + 版本  │            │ + 向量   │
        └─────────┘            └──────────┘
```

---

## 12 CLI 命令设计

### 12.1 主命令

```bash
bdms knowledge <subcommand> [options]
# 简写：bdms kb <subcommand> [options]
```

### 12.2 知识 CRUD 命令

```bash
# 创建
bdms kb create --type product_spec --title "..." --content-file spec.md
bdms kb create --type trouble_faq --title "..." --content "..." --product app-guard-v2
bdms kb create --type deploy_manual --title "..." --tags "部署,安装" --product app-guard-v2

# 查询
bdms kb list [--type product_spec] [--product app-guard-v2] [--status published] [--page 1]
bdms kb show <kb_id> [--version 2]          # 查看详情（含内容）
bdms kb show <kb_id> --versions             # 查看版本历史
bdms kb search <query> [--type ...] [--product ...] [--mode hybrid] [--top 20]

# 更新
bdms kb update <kb_id> --title "新标题"
bdms kb update <kb_id> --content-file new_content.md
bdms kb update <kb_id> --tags "标签1,标签2" --replace-tags

# 删除
bdms kb delete <kb_id>                       # 软删除
bdms kb delete <kb_id> --permanent           # 物理删除（需确认）
```

### 12.3 生命周期命令

```bash
# 审核流程
bdms kb submit <kb_id>                       # 提交审核
bdms kb review <kb_id> --approve --comment "同意发布"
bdms kb review <kb_id> --reject --comment "内容需补充..."
bdms kb publish <kb_id> --change-note "更新版本说明"    # 直接发布（管理员）

# 版本
bdms kb versions <kb_id>                     # 版本列表
bdms kb diff <kb_id> --from 1 --to 3         # 版本对比
bdms kb rollback <kb_id> --to-version 2      # 回滚到指定版本

# 归档 / 恢复
bdms kb archive <kb_id> --reason "产品已下线"
bdms kb restore <kb_id>
```

### 12.4 导入导出命令

```bash
# 导入
bdms kb import file <path/to/doc.md> --type deploy_manual --product app-guard-v2
bdms kb import dir <path/to/docs/> --type product_spec --recursive
bdms kb import json <path/to/data.json> --type trouble_faq
bdms kb import batch <manifest.yaml>         # 按清单批量导入
bdms kb import --dry-run                     # 预演，不实际写入

# 导出
bdms kb export <kb_id> --format md --output ./export/
bdms kb export --type product_spec --format json --output all_specs.json
```

### 12.5 管理命令

```bash
# 标签管理
bdms kb tags list
bdms kb tags add <tag_name> [--category product]
bdms kb tags delete <tag_name>
bdms kb tags merge <from_tag> <to_tag>      # 合并标签

# 索引管理
bdms kb index rebuild                       # 重建 FTS5 + 向量索引
bdms kb index rebuild --fts-only           # 仅重建 FTS5
bdms kb index rebuild --embedding-only     # 仅重建向量索引
bdms kb index status                        # 索引状态

# 统计
bdms kb stats                               # 知识库统计（总数/类型分布/状态分布）
bdms kb stats --top-views                   # 浏览量 Top 10
bdms kb stats --top-helpful                 # 最有用 Top 10
```

---

## 13 Web API 设计

### 13.1 REST API 概览

| Method | Path | 说明 | 权限 |
|---|---|---|---|
| GET | `/api/v1/knowledge` | 知识列表（支持搜索/过滤/分页） | viewer+ |
| GET | `/api/v1/knowledge/{id}` | 知识详情 | viewer+ |
| POST | `/api/v1/knowledge` | 创建知识 | editor+ |
| PUT | `/api/v1/knowledge/{id}` | 更新知识 | editor+ |
| DELETE | `/api/v1/knowledge/{id}` | 删除知识 | editor+ |
| POST | `/api/v1/knowledge/{id}/submit` | 提交审核 | editor+ |
| POST | `/api/v1/knowledge/{id}/review` | 审核 | admin |
| POST | `/api/v1/knowledge/{id}/publish` | 直接发布 | admin |
| POST | `/api/v1/knowledge/{id}/archive` | 归档 | admin |
| POST | `/api/v1/knowledge/{id}/restore` | 恢复 | admin |
| GET | `/api/v1/knowledge/{id}/versions` | 版本历史 | viewer+ |
| GET | `/api/v1/knowledge/{id}/versions/{v}` | 指定版本详情 | viewer+ |
| POST | `/api/v1/knowledge/search` | 高级搜索 | viewer+ |
| POST | `/api/v1/knowledge/import` | 批量导入 | editor+ |
| GET | `/api/v1/knowledge/tags` | 标签列表 | viewer+ |
| POST | `/api/v1/knowledge/tags` | 新增标签 | admin |
| GET | `/api/v1/knowledge/stats` | 统计信息 | viewer+ |

### 13.2 搜索 API 示例

**请求**：
```http
POST /api/v1/knowledge/search
Content-Type: application/json

{
  "query": "等保三级测评流程",
  "knowledge_type": null,
  "product_code": null,
  "tags": ["等保"],
  "search_mode": "hybrid",
  "top_k": 20,
  "page": 1,
  "page_size": 10,
  "include_archived": false
}
```

**响应**：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "total": 42,
    "page": 1,
    "page_size": 10,
    "results": [
      {
        "kb_id": "kb_abc123",
        "title": "等保三级测评实施流程指南",
        "knowledge_type": "deploy_manual",
        "product_code": "mlps-3",
        "tags": ["等保", "三级", "测评流程"],
        "summary": "本文档详细描述等保三级测评的完整实施流程...",
        "snippet": "等保三级测评流程包括：定级、备案、建设整改、...<mark>测评</mark>...",
        "score": 0.876,
        "bm25_score": 12.34,
        "semantic_score": 0.82,
        "view_count": 156,
        "helpful_count": 42,
        "published_at": "2026-08-15T10:30:00"
      }
    ]
  }
}
```

### 13.3 知识详情 API 示例

**请求**：
```http
GET /api/v1/knowledge/kb_abc123
```

**响应**：
```json
{
  "code": 0,
  "data": {
    "kb_id": "kb_abc123",
    "title": "等保三级测评实施流程指南",
    "knowledge_type": "deploy_manual",
    "content": "# 等保三级测评实施流程指南\n\n## 1 定级\n...",
    "content_html": "<h1>等保三级测评实施流程指南</h1>...",
    "summary": "本文档详细描述...",
    "product_code": "mlps-3",
    "tags": ["等保", "三级", "测评流程"],
    "status": "published",
    "current_version": 3,
    "published_version": 3,
    "author": "测评部",
    "view_count": 156,
    "helpful_count": 42,
    "reference_count": 8,
    "metadata": {
      "difficulty": "medium",
      "estimated_duration": "2 天"
    },
    "published_at": "2026-08-15T10:30:00",
    "updated_at": "2026-09-01T14:20:00",
    "related_items": [
      {"kb_id": "kb_def456", "title": "等保二级测评指南", "type": "deploy_manual"}
    ]
  }
}
```

---

## 14 权限模型

### 14.1 角色定义

| 角色 | 编码 | 说明 |
|---|---|---|
| 知识库管理员 | `kb_admin` | 完全权限，包括审核、发布、归档、删除、标签管理 |
| 知识编辑者 | `kb_editor` | 创建、编辑、提交审核、查看所有知识 |
| 知识浏览者 | `kb_viewer` | 查看已发布知识、搜索 |
| 审核员 | `kb_reviewer` | 审核知识、发布/驳回（可由管理员兼任） |

### 14.2 权限矩阵

| 操作 | viewer | editor | reviewer | admin |
|---|:---:|:---:|:---:|:---:|
| 搜索已发布知识 | ✅ | ✅ | ✅ | ✅ |
| 查看知识详情（已发布） | ✅ | ✅ | ✅ | ✅ |
| 查看草稿/待审核知识 | ❌ | ✅（自己的） | ✅ | ✅ |
| 创建知识 | ❌ | ✅ | ✅ | ✅ |
| 编辑知识（草稿/驳回） | ❌ | ✅（自己的） | ✅ | ✅ |
| 提交审核 | ❌ | ✅ | ✅ | ✅ |
| 撤回审核 | ❌ | ✅（自己的） | ✅ | ✅ |
| 审核（通过/驳回） | ❌ | ❌ | ✅ | ✅ |
| 直接发布（跳过审核） | ❌ | ❌ | ❌ | ✅ |
| 归档 / 恢复 | ❌ | ❌ | ❌ | ✅ |
| 删除知识（软删） | ❌ | ✅（自己的草稿） | ❌ | ✅ |
| 物理删除 | ❌ | ❌ | ❌ | ✅ |
| 标签管理（增删改） | ❌ | ❌ | ❌ | ✅ |
| 索引重建 | ❌ | ❌ | ❌ | ✅ |
| 查看统计 | ❌ | ✅（部分） | ✅ | ✅ |
| 批量导入 | ❌ | ✅ | ✅ | ✅ |

### 14.3 数据范围

- **viewer**：仅能看到 `status = published` 的知识
- **editor**：能看到自己创建的所有状态知识 + 所有已发布知识
- **reviewer / admin**：能看到所有状态的所有知识

### 14.4 与全局权限的关系

知识库权限是 BDMS 全局权限体系的子集：
- 系统管理员（`sys_admin`）自动拥有 `kb_admin` 权限
- 各业务模块的成员默认拥有 `kb_viewer` 权限
- 权限分配通过 BDMS 统一权限管理模块配置

---

## 15 验证方案

### 15.1 语义检索准确率验证

**测试集构建**：
- 人工标注 100 个查询 → 正确知识条目的映射
- 覆盖 7 种知识类型
- 包含精确查询、模糊查询、错误表述查询

**评估指标**：

| 指标 | 定义 | 目标值 |
|---|---|---|
| Top-1 Accuracy | 第一个结果是正确答案的比例 | ≥ 70% |
| Top-3 Accuracy | 前 3 个结果包含正确答案的比例 | ≥ 85% |
| Top-5 Accuracy | 前 5 个结果包含正确答案的比例 | ≥ 90% |
| MRR (Mean Reciprocal Rank) | 正确结果排名倒数的平均值 | ≥ 0.75 |
| NDCG@10 | 归一化折损累计增益 | ≥ 0.80 |

**测试方法**：

```python
def evaluate_semantic_search(test_set: List[Dict]) -> Dict:
    """
    评估语义检索效果。

    test_set 格式：
    [
        {"query": "等保三级多久测一次", "expected_kb_id": "kb_001", "type": "faq"},
        ...
    ]
    """
    top1_correct = 0
    top3_correct = 0
    top5_correct = 0
    mrr_sum = 0.0
    ndcg_sum = 0.0

    for item in test_set:
        query = item["query"]
        expected = item["expected_kb_id"]

        # 执行语义检索
        results = kb_service.search(query, search_mode="semantic", top_k=10)
        result_ids = [r["kb_id"] for r in results]

        # 计算排名
        rank = None
        if expected in result_ids:
            rank = result_ids.index(expected) + 1

        # Top-k 准确率
        if rank == 1:
            top1_correct += 1
        if rank and rank <= 3:
            top3_correct += 1
        if rank and rank <= 5:
            top5_correct += 1

        # MRR
        if rank:
            mrr_sum += 1.0 / rank

        # NDCG@10
        dcg = 0.0
        idcg = 1.0  # 只有一个相关结果，IDCG = 1
        if rank and rank <= 10:
            dcg = 1.0 / np.log2(rank + 1)
        ndcg_sum += dcg / idcg

    n = len(test_set)
    return {
        "total_queries": n,
        "top1_accuracy": top1_correct / n,
        "top3_accuracy": top3_correct / n,
        "top5_accuracy": top5_correct / n,
        "mrr": mrr_sum / n,
        "ndcg@10": ndcg_sum / n,
    }
```

### 15.2 全文检索召回率验证

**评估指标**：

| 指标 | 定义 | 目标值 |
|---|---|---|
| Precision@10 | 前 10 个结果中相关结果比例 | ≥ 70% |
| Recall@20 | 前 20 个结果覆盖的相关结果比例 | ≥ 85% |
| F1@20 | P 和 R 的调和平均 | ≥ 0.75 |

**测试方法**：
- 人工构建 20 个查询，每个查询标注 5-10 个相关知识
- 计算 Precision / Recall / F1

### 15.3 混合检索对比实验

对比三种检索模式的效果：

| 模式 | Top-1 Acc | Top-3 Acc | MRR | NDCG@10 |
|---|---|---|---|---|
| 仅全文检索 (FTS5) | - | - | - | - |
| 仅语义检索 (embedding) | - | - | - | - |
| 混合检索 (RRF 融合) | - | - | - | - |

预期：混合检索在所有指标上优于单一模式。

### 15.4 性能测试

| 测试项 | 数据规模 | 目标性能 |
|---|---|---|
| 单条 embedding 生成 | - | < 50ms |
| 批量 embedding (32 条) | - | < 300ms |
| 全文检索（单条查询） | 10,000 条知识 | < 50ms |
| 语义检索（单条查询） | 10,000 条知识 | < 100ms |
| 混合检索（单条查询） | 10,000 条知识 | < 200ms |
| 知识创建（含 embedding + FTS5） | - | < 500ms |
| 批量导入（100 条） | - | < 30s |
| 重建 FTS5 索引 | 10,000 条 | < 60s |
| 重建向量索引 | 10,000 条 | < 10min |

### 15.5 功能验证清单

| 功能点 | 验证项 | 通过标准 |
|---|---|---|
| 知识 CRUD | 创建/查询/更新/删除 | 操作成功，数据正确 |
| 版本管理 | 版本递增、版本对比、回滚 | 版本号正确，内容一致 |
| 审核流程 | 提交→通过/驳回 | 状态转换正确，日志完整 |
| 标签系统 | 增删改查、标签云 | 标签关联正确，计数准确 |
| 全文检索 | 关键词搜索、高亮 | 能搜到，结果相关 |
| 语义检索 | 相似语义匹配 | 同义词/相关词能搜到 |
| 混合检索 | 两种结果融合 | 效果优于单一模式 |
| 权限控制 | 不同角色不同权限 | 越权操作被拒绝 |
| 导入导出 | Markdown / JSON 导入 | 导入正确，导出完整 |
| 统计指标 | 浏览量/好评率/引用数 | 计数准确 |

---

## 16 落地路径

### Phase 1：结构化 + 全文检索（基础可用，约 5 天）

目标：知识库核心功能可用，支持结构化管理和全文检索。

- [ ] **Day 1：数据模型 + CRUD**
  - 创建 kb_item / kb_version / kb_tag / kb_item_tag / kb_review_log 表
  - 实现 KnowledgeBaseService 的 CRUD 方法
  - 实现知识状态机（draft/pending/published/rejected/archived/deleted）
  - 实现版本管理（快照、版本列表、版本对比）

- [ ] **Day 2：全文检索 (FTS5)**
  - 创建 kb_fts FTS5 虚拟表
  - 集成 jieba 中文分词
  - 实现 FTS5 同步机制（写入/更新/删除）
  - 实现全文检索 API（含高亮、排序、过滤）

- [ ] **Day 3：审核 + 标签 + 导入**
  - 实现审核流程（提交/通过/驳回）
  - 实现标签管理
  - 实现 Markdown 文件导入（支持 Front Matter）
  - 实现 JSON 批量导入

- [ ] **Day 4：CLI + Web API**
  - 实现 `bdms knowledge` 命令族（约 30 个子命令）
  - 实现 REST API（约 15 个 endpoint）
  - 实现权限控制（3 个角色）

- [ ] **Day 5：测试 + 文档**
  - 单元测试覆盖核心功能
  - 全文检索召回率测试
  - 编写模块 README + 使用文档
  - 数据初始化（种子数据）

**Phase 1 交付物**：
- 完整的知识库模块（CRUD + 版本 + 审核 + 标签 + 全文检索 + 导入导出）
- CLI + Web API
- 权限控制
- 单元测试（覆盖率 ≥ 70%）

### Phase 2：语义检索接入（智能化升级，约 3 天）

目标：接入本地 GGUF embedding，支持语义检索和混合检索。

- [ ] **Day 1：Embedding 集成**
  - 创建 kb_item_embedding 表
  - 封装 EmbeddingProvider（调用 L2 Memory-009 本地服务）
  - 实现向量生成 + 存储
  - 实现语义检索（内存计算 + 余弦相似度）

- [ ] **Day 2：混合检索 + Rerank**
  - 实现 RRF 融合算法
  - 实现多层过滤流水线（类型/产品/标签/状态）
  - 实现业务重排（引用量/好评率/时效性）
  - 统一 SearchEngine 接口

- [ ] **Day 3：优化 + 验证**
  - 分段 embedding 优化（长文档处理）
  - 性能优化（批量计算、缓存）
  - 语义检索准确率测试（构建测试集 + 评估）
  - 混合检索对比实验

**Phase 2 交付物**：
- 语义检索功能
- 混合检索（RRF 融合）
- 检索质量评估报告
- 性能达标

### Phase 3：智能问答 + 推荐（高级特性，约 5 天）

目标：从"找知识"升级到"给答案"，支持智能问答和主动推荐。

- [ ] **智能问答（RAG）**
  - 基于知识库的问答系统（检索 + LLM 生成答案）
  - 答案溯源（引用来源知识条目）
  - 多轮对话上下文

- [ ] **主动推荐**
  - 项目启动时推荐相关知识
  - 工单创建时匹配 FAQ
  - 合同起草时推荐条款模板
  - 基于用户行为的个性化推荐

- [ ] **知识质量分析**
  - 知识质量评分（完整度/时效性/使用率）
  - 知识缺口识别（哪些主题缺少文档）
  - 自动提示更新（过期知识提醒）

- [ ] **向量索引升级**
  - 数据量超过 1 万条 → 引入 Faiss
  - 增量索引维护

**Phase 3 交付物**：
- 智能问答（RAG）
- 跨模块知识推荐
- 知识质量分析
- 向量索引升级（按需）

---

## 17 复用资产映射

| 资产 | 来源 | 复用方式 |
|---|---|---|
| BaseEngine / BaseService / BaseImporter | BDMS Base 模块 | KnowledgeBaseService / KnowledgeImporter 继承 |
| 状态机框架 | BDMS Base 模块 | 知识生命周期状态机 |
| 审计日志框架 | BDMS Base 模块 | 审核日志 + 操作日志 |
| 权限框架 | BDMS Base 模块 | 3 级角色权限控制 |
| L2 Memory-009 本地 GGUF embedding | L2 基础设施 | 语义检索的向量生成，768 维 |
| L2 Persistence-006 SQLite + FTS5 | L2 基础设施 | 数据存储 + 全文检索引擎 |
| 标签系统 | BDMS 通用组件 | kb_tag + kb_item_tag |
| 分页 / 排序 / 过滤 | BDMS Base 模块 | 列表查询统一规范 |
| 全局 WeCom 通知 | 全局集成 | 审核通知 / 知识更新通知 |

---

## 18 技术方案

### 18.1 技术选型

| 维度 | 选型 | 依据 |
| ---|---|---|
| 语言 | Python 3.10+ | 与 BDMS 全栈一致 |
| 持久化 | SQLite（通过 core.db） | 与所有模块共享连接 |
| 语义检索 | L2 Memory-009（本地 GGUF embedding） | 已验证可用，768 维 |
| 全文检索 | SQLite FTS5 + jieba 分词 | 零依赖 + BM25 排序 |
| 混合检索 | RRF 融合（Reciprocal Rank Fusion） | 鲁棒、无需调参 |
| 向量存储 | SQLite BLOB（float32 小端序） | < 10000 条规模无需向量数据库 |
| 长文本分段 | chunk_size=300 字，overlap=50 字 | 适配 512 token 限制 |

### 18.2 依赖的 L2/L3/L4 资产

| 资产 | 层级 | 复用方式 |
| ---|---|---|
| L2 Memory-009 | L2 | 本地 GGUF embedding（768 维） |
| L2 Persistence-006 | L2 | SQLite + Repository + FTS5 |
| BaseService / BaseImporter | L4 BDMS Base | 继承基类 |
| bdms.core.db | L4 Core | 统一 DB 连接 |
| bdms.core.schemas | L4 Core | KB_SCHEMA |

### 18.3 与现有代码的复用/重构关系

- 现有 `modules/knowledge_base/` 在 v1.0 中未实现，v2.1 从零构建
- EmbeddingProvider 封装 L2 Memory-009 HTTP 调用，隔离外部依赖
- SearchEngine 封装混合检索逻辑，对外提供统一 search() 接口

---

## 19 非功能设计

### 19.1 性能

| 场景 | 目标 | 手段 |
| ---|---|---|
| 语义检索（万级） | < 200ms | 内存 numpy 计算 + 向量索引 |
| 全文检索 | < 100ms | FTS5 倒排索引 + BM25 |
| 混合检索 | < 300ms | 并行检索 + RRF 融合 |
| 知识创建（含 embedding） | < 2s | 异步 embedding 生成 |
| 批量导入（1000 条） | < 30s | 分批 embedding + 事务写入 |

### 19.2 可靠性

- **embedding 服务降级**：L2 Memory-009 不可用时，降级为纯全文检索
- **向量索引一致性**：知识更新时同步更新 embedding + FTS5 + 版本表
- **事务保证**：知识 CRUD + 向量写入 + FTS5 同步同事务
- **幂等保障**：kb_id + version 唯一约束

### 19.3 安全

- **内容安全**：知识内容 Markdown 渲染时 XSS 过滤
- **权限控制**：知识创建/审核/发布需对应角色权限
- **审计日志**：知识全生命周期操作留痕（who/when/what）
- **软删除**：删除操作仅标记 status=deleted，30 天后物理清理

### 19.4 可用性

- **检索降级**：语义检索不可用时自动降级为全文检索
- **模型升级**：embedding 模型升级时，后台批量重新生成向量
- **数据备份**：知识数据随 BDMS 整体备份策略执行

---

## 20 风险与权衡

| 风险 | 影响 | 缓解措施 |
| ---|---|---|
| embedding 模型不可用 | 语义检索失效 | 降级为全文检索 + 本地模型健康监控 |
| 向量数据量增长 | 内存计算变慢 | 引入 Faiss 索引 + 向量数据库演进 |
| 中文分词不准确 | 全文检索召回率低 | jieba 自定义词典 + 分词效果持续调优 |
| 知识内容过时 | 决策参考失误 | 定期审核机制 + 版本迭代 + 过期标记 |
| 混合检索权重不合理 | 搜索结果不精准 | A/B 测试 + 用户反馈 + 权重可配置 |
| 长文本分段语义断裂 | 检索精度下降 | 智能分段（按章节）+ overlap 机制 |
| 知识库规模超预期 | 性能下降 | 分库分表 + 向量数据库迁移路径 |

---

## 21 业界最佳实践对比与优化

### 21.1 对标标准

| 业界实践 | 核心思想 | BDMS 当前做法 | 差距 | 优化建议 |
|---|---|---|---|---|
| **企业知识管理（KM）** | 知识全生命周期管理 + 组织协同 | 有生命周期管理，缺协同编辑 | 缺实时协作 | 增加协同编辑和评论功能（类似 Confluence） |
| **知识图谱（Knowledge Graph）** | 实体-关系-属性图模型，语义关联 | 关系型模型 + 标签 | 缺图结构 | 引入知识图谱，建立知识条目间的语义关联（如：产品→手册→FAQ 的关联链） |
| **RAG（检索增强生成）** | 检索 + LLM 生成答案 | Phase 3 规划 | 未实现 | 加速 RAG 落地，支持基于知识库的智能问答 |
| **向量数据库（Milvus/Qdrant）** | 专用向量索引，ANN 检索 | SQLite BLOB + 内存计算 | 大数据量性能不足 | 超 1 万条迁移到专用向量数据库 |
| **AI 自动分类** | LLM 自动识别知识类型和标签 | 手动分类 | 缺自动化 | 增加 AI 辅助分类（OPTIONAL_TOKEN） |
| **内容管理系统（CMS）** | 富文本编辑 + 版本控制 + 工作流 | Markdown + 版本 + 审核 | 基本覆盖 | 增加富文本编辑器，降低使用门槛 |
| **文档管理系统（DMS）** | 全文检索 + 权限 + 审计 | FTS5 + 权限 + 审计 | 基本覆盖 | 增加文档预览和在线查看功能 |
| **协同知识库（Wiki）** | 多人协作 + 评论 + 通知 | 单人创建 + 审核 | 缺协作 | 增加评论、@提及、变更通知等协作功能 |

### 21.2 建议的优化项

**P0（v2.1 必须做）**：

1. **知识图谱关联**
   - 问题：知识条目之间缺乏语义关联，难以发现相关知识
   - 方案：建立知识关联表（`kb_relation`），记录条目间的关联关系（相关/依赖/引用）
   - 成本：低（+1 表 + 关联推荐接口）
   - 收益：高（提升知识发现效率）

2. **INTEGRATION 导入通道**
   - 问题：外部知识源无法自动同步到知识库
   - 方案：通过 INTEGRATION 模块连接器，自动导入外部知识文档
   - 成本：中（+4 个连接器 + 类型映射）
   - 收益：高（打通知识孤岛）

**P1（v2.2 可做）**：

3. **RAG 智能问答**
   - 问题：用户需要精确构造查询词才能找到知识
   - 方案：基于知识库的 RAG，支持自然语言问答
   - 成本：中（+ RAG 服务 + LLM 调用）
   - 收益：中（OPTIONAL_TOKEN，提升用户体验）

4. **AI 辅助分类**
   - 问题：手动分类效率低，容易出错
   - 方案：LLM 自动识别知识类型、提取标签、生成摘要
   - 成本：中（+ AI 分类服务）
   - 收益：中（OPTIONAL_TOKEN）

**P2（远期）**：

5. **协同编辑**
   - 问题：多人协作编辑知识库效率低
   - 方案：支持实时协同编辑（类似 Google Docs）
   - 成本高 | 收益：低（当前用户量不大）

6. **富文本编辑器**
   - 问题：Markdown 门槛较高
   - 方案：在线富文本编辑器，自动生成 Markdown
   - 成本：中 | 收益：低（技术用户 Markdown 够用）

---

## 22 知识导入（INTEGRATION 关联扩展）

### 22.1 INTEGRATION 模块导入通道

知识库与 INTEGRATION 模块协同，支持从外部知识源自动同步知识文档。

**关联架构**：

```
外部知识源（SharePoint / Confluence / 文件共享 / OA 文档）
    │
    ▼
INTEGRATION 模块（连接器：sharepoint / confluence / file_share / oa_doc）
    │ 标准化为统一中间格式
    ▼
KnowledgeImporter.receive_from_integration(connector_name, batch_id)
    │ 知识类型映射 + 产品关联
    ▼
kb_item / kb_version / kb_fts / kb_item_embedding
```

**INTEGRATION 连接器扩展**：

| 连接器 | 数据源 | 知识类型 | 同步方式 |
|---|---|---|---|
| `sharepoint` | SharePoint 文档库 | product_spec / deploy_manual / trouble_faq | API + Webhook |
| `confluence` | Confluence Wiki | 全部 7 种类型 | API + 增量同步 |
| `file_share` | 本地/网络文件共享 | 全部 7 种类型 | 文件监听 + 定时扫描 |
| `oa_doc` | OA 知识库 | acceptance_std / contract_clause | API |

**知识类型自动映射**：

```python
KNOWLEDGE_TYPE_MAPPING = {
    "product_spec": ["产品规格", "技术文档", "产品手册", "product specification"],
    "service_sla": ["SLA", "服务标准", "服务等级", "service level"],
    "deploy_manual": ["部署手册", "安装指南", "实施手册", "deployment"],
    "acceptance_std": ["验收标准", "验收规范", "acceptance criteria"],
    "contract_clause": ["合同条款", "条款模板", "clause template"],
    "pricing_ref": ["定价", "报价", "价格参考", "pricing"],
    "trouble_faq": ["FAQ", "故障排查", "常见问题", "troubleshooting"],
}
```

**同步触发方式**：

| 方式 | 说明 |
|---|---|
| 定时同步 | APScheduler 定时从外部源拉取更新 |
| Webhook 推送 | 外部源变更时主动推送（SharePoint/Confluence 支持） |
| 手动触发 | CLI 命令 `bdms kb import integration <connector>` |
| 文件监听 | 文件共享目录变更自动触发导入 |

### 22.2 导入校验规则补充

针对 INTEGRATION 同步导入，增加以下校验规则：

| 校验项 | 规则 | 不通过处理 |
|---|---|---|---|
| 知识类型映射 | 外部元数据能映射到 7 种类型 | 跳过，记录警告（待人工分类） |
| 产品关联 | 产品编码存在于 master_data | 警告（可能是新产品） |
| 内容去重 | 同标题 + 同产品 + 同类型 | 更新而非插入（覆盖旧版本） |
| 格式校验 | Markdown 格式合法 | 跳过，记录错误 |

---

## 23 变更历史

| 版本 | 日期 | 作者 | 变更内容 |
|---|---|---|---|
| v2.1 | 2026-09-19 | BDMS Architecture | 初始版本：知识库模块详细设计 |
| v2.1 | 2026-09-19 | BDMS Architecture | 新增：业界最佳实践对比 + INTEGRATION 导入通道 + 知识图谱关联 |

