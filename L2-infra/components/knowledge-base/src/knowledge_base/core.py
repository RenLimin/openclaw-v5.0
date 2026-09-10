"""KnowledgeBase 主类 — 统一门面，整合所有子能力。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .chunker import Chunker, SemanticChunker, CharacterChunker
from .document import Document, Chunk, SearchResult
from .embedder import Embedder, MockEmbedder
from .index import VectorIndex, SimpleIndex
from .manager import KnowledgeManager
from .parser import DocumentParser, MarkdownParser, get_parser_for_type
from .retriever import (
    Retriever, SemanticRetriever, KeywordRetriever, HybridRetriever,
)


class KnowledgeBase:
    """知识库主类 — 统一入口。

    整合：文档解析 → 分块 → 向量化 → 索引 → 检索 → 管理。

    用法:
        kb = KnowledgeBase()
        kb.add_document(doc)
        results = kb.search("查询关键词")
    """

    def __init__(
        self,
        embedder: Embedder | None = None,
        chunker: Chunker | None = None,
        index: VectorIndex | None = None,
        manager: KnowledgeManager | None = None,
        retrieval_mode: str = "hybrid",
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4,
        storage_dir: str | Path | None = None,
    ):
        # 存储目录
        self._storage_dir = Path(storage_dir) if storage_dir else None

        # 嵌入器（默认 Mock，避免依赖模型下载）
        self._embedder = embedder or MockEmbedder()
        dim = self._embedder.dimension

        # 分块器（默认语义分块）
        self._chunker = chunker or SemanticChunker(chunk_size=500, chunk_overlap=50)

        # 向量索引
        self._index = index or SimpleIndex(dimension=dim)

        # 文档管理器
        self._manager = manager or KnowledgeManager()

        # 检索器
        self._semantic_retriever = SemanticRetriever(self._index, self._embedder)
        self._keyword_retriever = KeywordRetriever()
        self._hybrid_retriever = HybridRetriever(
            self._semantic_retriever,
            self._keyword_retriever,
            semantic_weight=semantic_weight,
            keyword_weight=keyword_weight,
        )
        self._retrieval_mode = retrieval_mode  # semantic / keyword / hybrid

        # 文档 → 块 映射
        self._doc_chunks: dict[str, list[str]] = {}

    # ---- 属性 ----

    @property
    def count(self) -> int:
        return self._manager.count

    @property
    def chunk_count(self) -> int:
        return self._index.size

    @property
    def retrieval_mode(self) -> str:
        return self._retrieval_mode

    @retrieval_mode.setter
    def retrieval_mode(self, mode: str) -> None:
        if mode not in ("semantic", "keyword", "hybrid"):
            raise ValueError(f"不支持的检索模式: {mode}")
        self._retrieval_mode = mode

    def set_retrieval_weights(self, semantic_weight: float, keyword_weight: float) -> None:
        """设置混合检索权重。"""
        self._hybrid_retriever.set_weights(semantic_weight, keyword_weight)

    # ---- 文档增删改查 ----

    def add_document(self, doc: Document | str, doc_type: str = "markdown") -> str:
        """添加一篇文档，返回 doc_id。

        Args:
            doc: Document 对象或原始文本字符串
            doc_type: 当 doc 是字符串时的文档类型
        """
        if isinstance(doc, str):
            parser = get_parser_for_type(doc_type)
            doc = parser.parse(doc)

        # 存入管理器
        self._manager.add(doc)

        # 分块
        chunks = self._chunker.chunk(doc)
        if not chunks:
            return doc.doc_id

        # 向量化
        texts = [c.content for c in chunks]
        vectors = self._embedder.embed_batch(texts)
        for chunk, vec in zip(chunks, vectors):
            chunk.embedding = vec
            chunk.metadata["category"] = doc.category
            chunk.metadata["title"] = doc.title

        # 加入向量索引
        self._index.add_batch(chunks)

        # 加入关键词索引
        for chunk in chunks:
            self._keyword_retriever.add_chunk(chunk)

        # 维护映射
        self._doc_chunks[doc.doc_id] = [c.chunk_id for c in chunks]

        return doc.doc_id

    def add_documents(self, docs: list[Document]) -> list[str]:
        """批量添加文档。"""
        return [self.add_document(d) for d in docs]

    def add_file(self, path: str | Path, doc_type: str | None = None) -> str:
        """从文件添加文档。"""
        from .parser import get_parser_for_file
        p = Path(path)
        parser = get_parser_for_file(p) if doc_type is None else get_parser_for_type(doc_type)
        doc = parser.parse_file(p)
        return self.add_document(doc)

    def get_document(self, doc_id: str) -> Document | None:
        """获取文档。"""
        return self._manager.get(doc_id)

    def delete_document(self, doc_id: str) -> bool:
        """删除文档及其所有块。"""
        # 从向量索引删除
        if hasattr(self._index, 'delete_by_doc'):
            self._index.delete_by_doc(doc_id)  # type: ignore
        else:
            for cid in self._doc_chunks.get(doc_id, []):
                self._index.delete(cid)

        # 从关键词索引删除
        for cid in self._doc_chunks.get(doc_id, []):
            self._keyword_retriever.remove_chunk(cid)

        # 从管理器删除
        result = self._manager.delete(doc_id)

        # 清理映射
        self._doc_chunks.pop(doc_id, None)

        return result

    def list_documents(self, category: str | None = None,
                       tag: str | None = None) -> list[Document]:
        """列出文档，可按分类/标签过滤。"""
        return self._manager.list(category=category, tag=tag)

    # ---- 检索 ----

    def search(self, query: str, limit: int = 10,
               mode: str | None = None,
               filters: dict[str, Any] | None = None) -> list[SearchResult]:
        """搜索。

        Args:
            query: 查询文本
            limit: 返回数量上限
            mode: 检索模式（semantic/keyword/hybrid），None 用默认
            filters: 过滤条件，如 {"category": "tech", "doc_ids": [...]}
        """
        mode = mode or self._retrieval_mode

        if mode == "semantic":
            retriever: Retriever = self._semantic_retriever
        elif mode == "keyword":
            retriever = self._keyword_retriever
        elif mode == "hybrid":
            retriever = self._hybrid_retriever
        else:
            raise ValueError(f"不支持的检索模式: {mode}")

        results = retriever.search(query, top_k=limit, filters=filters)

        # 填充 Document
        for r in results:
            if r.document is None:
                r.document = self._manager.get(r.chunk.doc_id)

        return results

    # ---- 索引管理 ----

    def rebuild_index(self) -> bool:
        """重建向量索引（全量重算）。"""
        try:
            all_docs = self._manager.list()
            self._index.clear()
            self._doc_chunks.clear()

            # 清空关键词索引
            self._keyword_retriever.update_chunks([])

            for doc in all_docs:
                chunks = self._chunker.chunk(doc)
                if not chunks:
                    continue

                texts = [c.content for c in chunks]
                vectors = self._embedder.embed_batch(texts)
                for chunk, vec in zip(chunks, vectors):
                    chunk.embedding = vec
                    chunk.metadata["category"] = doc.category
                    chunk.metadata["title"] = doc.title

                self._index.add_batch(chunks)
                for chunk in chunks:
                    self._keyword_retriever.add_chunk(chunk)

                self._doc_chunks[doc.doc_id] = [c.chunk_id for c in chunks]

            return True
        except Exception:
            return False

    def stats(self) -> dict[str, Any]:
        """知识库统计。"""
        info = self._manager.stats()
        info["chunk_count"] = self._index.size
        info["vector_dimension"] = self._index.dimension
        info["retrieval_mode"] = self._retrieval_mode
        return info

    # ---- 持久化 ----

    def save(self, storage_dir: str | Path | None = None) -> None:
        """保存整个知识库到目录。"""
        d = Path(storage_dir) if storage_dir else self._storage_dir
        if d is None:
            raise ValueError("未指定存储目录")

        d.mkdir(parents=True, exist_ok=True)

        # 保存文档元数据 + 内容
        self._manager.save(d / "documents.json")

        # 保存向量索引
        self._index.save(d / "vector_index")

        # 保存 doc-chunk 映射
        mapping_path = d / "chunk_mapping.json"
        mapping_path.write_text(
            json.dumps(self._doc_chunks, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 保存配置
        config = {
            "retrieval_mode": self._retrieval_mode,
            "semantic_weight": self._hybrid_retriever.semantic_weight,
            "keyword_weight": self._hybrid_retriever.keyword_weight,
            "dimension": self._index.dimension,
        }
        (d / "config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        self._storage_dir = d

    @classmethod
    def load(cls, storage_dir: str | Path,
             embedder: Embedder | None = None) -> "KnowledgeBase":
        """从目录加载知识库。"""
        d = Path(storage_dir)
        if not d.exists():
            raise FileNotFoundError(f"知识库目录不存在: {d}")

        # 加载配置
        config_path = d / "config.json"
        config = {}
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))

        dim = config.get("dimension", 128)
        emb = embedder or MockEmbedder(dimension=dim)

        # 加载文档管理器
        manager = KnowledgeManager.load(d / "documents.json")

        # 加载向量索引
        index = SimpleIndex.load(d / "vector_index")

        # 加载映射
        mapping: dict[str, list[str]] = {}
        map_path = d / "chunk_mapping.json"
        if map_path.exists():
            mapping = json.loads(map_path.read_text(encoding="utf-8"))

        # 创建实例
        kb = cls(
            embedder=emb,
            index=index,
            manager=manager,
            retrieval_mode=config.get("retrieval_mode", "hybrid"),
            semantic_weight=config.get("semantic_weight", 0.6),
            keyword_weight=config.get("keyword_weight", 0.4),
            storage_dir=d,
        )
        kb._doc_chunks = mapping

        # 重建关键词索引（从向量索引中的 chunk 数据）
        keyword_chunks = []
        for cid in index.all_chunk_ids():
            chunk = index.get(cid)
            if chunk:
                keyword_chunks.append(chunk)
        kb._keyword_retriever.update_chunks(keyword_chunks)

        return kb
