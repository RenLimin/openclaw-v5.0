"""检索器 — 语义检索 / 关键词检索 / 混合检索。"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any

from .document import Chunk, Document, SearchResult
from .embedder import Embedder
from .index import VectorIndex


class Retriever(ABC):
    """检索器抽象基类。"""

    @abstractmethod
    def search(self, query: str, top_k: int = 10,
               filters: dict[str, Any] | None = None) -> list[SearchResult]:
        """检索，返回按相关度排序的结果。"""
        ...


class SemanticRetriever(Retriever):
    """语义检索 — 基于向量相似度。"""

    def __init__(self, index: VectorIndex, embedder: Embedder):
        self.index = index
        self.embedder = embedder

    def search(self, query: str, top_k: int = 10,
               filters: dict[str, Any] | None = None) -> list[SearchResult]:
        query_vec = self.embedder.embed(query)

        doc_ids = None
        if filters and "doc_ids" in filters:
            doc_ids = set(filters["doc_ids"])

        raw_results = self.index.search(query_vec, top_k=top_k, doc_ids=doc_ids) \
            if hasattr(self.index, 'search') and doc_ids \
            else self.index.search(query_vec, top_k=top_k)

        results: list[SearchResult] = []
        for chunk_id, score in raw_results:
            chunk = self.index.get(chunk_id)
            if chunk is None:
                continue
            # 过滤
            if filters and not self._match_filters(chunk, filters):
                continue
            results.append(SearchResult(
                chunk=chunk,
                score=score,
                match_type="semantic",
            ))

        return results[:top_k]

    @staticmethod
    def _match_filters(chunk: Chunk, filters: dict[str, Any]) -> bool:
        if "category" in filters and chunk.metadata.get("category") != filters["category"]:
            return False
        return True


class KeywordRetriever(Retriever):
    """关键词检索 — 基于 TF-IDF / BM25 简化版。

    轻量实现：用词频 + 逆文档频率计算相关性。
    """

    def __init__(self, chunks: list[Chunk] | None = None):
        self._chunks: dict[str, Chunk] = {}
        # doc frequency：每个词出现在多少个块里
        self._df: Counter[str] = Counter()
        self._total_docs = 0
        # chunk_id -> {word: count}
        self._tf: dict[str, Counter[str]] = {}

        if chunks:
            for c in chunks:
                self.add_chunk(c)

    def add_chunk(self, chunk: Chunk) -> None:
        if chunk.chunk_id in self._chunks:
            return  # 去重
        self._chunks[chunk.chunk_id] = chunk
        words = self._tokenize(chunk.content)
        tf = Counter(words)
        self._tf[chunk.chunk_id] = tf
        for word in set(words):
            self._df[word] += 1
        self._total_docs += 1

    def remove_chunk(self, chunk_id: str) -> None:
        if chunk_id not in self._chunks:
            return
        tf = self._tf.pop(chunk_id, Counter())
        for word in set(tf.keys()):
            self._df[word] -= 1
            if self._df[word] <= 0:
                del self._df[word]
        del self._chunks[chunk_id]
        self._total_docs -= 1

    def update_chunks(self, chunks: list[Chunk]) -> None:
        """全量更新（重建索引）。"""
        self._chunks.clear()
        self._df.clear()
        self._tf.clear()
        self._total_docs = 0
        for c in chunks:
            self.add_chunk(c)

    def search(self, query: str, top_k: int = 10,
               filters: dict[str, Any] | None = None) -> list[SearchResult]:
        query_words = self._tokenize(query)
        if not query_words:
            return []

        results: list[tuple[str, float]] = []

        for chunk_id, tf in self._tf.items():
            chunk = self._chunks[chunk_id]
            if filters and not self._match_filters(chunk, filters):
                continue

            score = self._bm25_score(query_words, tf, len(chunk.content))
            if score > 0:
                results.append((chunk_id, score))

        results.sort(key=lambda x: x[1], reverse=True)

        # 归一化分数到 0~1
        max_score = results[0][1] if results else 1.0
        if max_score == 0:
            max_score = 1.0

        output: list[SearchResult] = []
        for chunk_id, score in results[:top_k]:
            chunk = self._chunks[chunk_id]
            output.append(SearchResult(
                chunk=chunk,
                score=min(1.0, score / max_score),
                match_type="keyword",
            ))

        return output

    def _bm25_score(self, query_words: list[str], tf: Counter[str],
                    doc_len: int) -> float:
        """简化版 BM25。"""
        k1 = 1.5
        b = 0.75
        avgdl = 500.0  # 平均文档长度（字符，近似）

        score = 0.0
        dl = max(1, doc_len)
        for qw in set(query_words):
            if qw not in tf:
                continue
            f = tf[qw]
            df = self._df.get(qw, 0)
            if df == 0:
                continue
            # IDF
            idf = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)
            # BM25 term score
            numerator = f * (k1 + 1)
            denominator = f + k1 * (1 - b + b * dl / avgdl)
            score += idf * numerator / denominator

        return score

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单分词：英文小写 + 中文单字。"""
        tokens: list[str] = []
        # 英文单词
        for m in re.finditer(r'[a-zA-Z]{2,}', text):
            tokens.append(m.group().lower())
        # 中文字符
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                tokens.append(ch)
        return tokens

    @staticmethod
    def _match_filters(chunk: Chunk, filters: dict[str, Any]) -> bool:
        if "category" in filters and chunk.metadata.get("category") != filters["category"]:
            return False
        return True


class HybridRetriever(Retriever):
    """混合检索 — 语义 + 关键词，可配置权重。"""

    def __init__(
        self,
        semantic_retriever: SemanticRetriever,
        keyword_retriever: KeywordRetriever,
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4,
    ):
        self.semantic = semantic_retriever
        self.keyword = keyword_retriever
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight

    def search(self, query: str, top_k: int = 10,
               filters: dict[str, Any] | None = None) -> list[SearchResult]:
        # 两边各取 top_k * 2，合并后重排
        k = top_k * 3
        sem_results = {r.chunk.chunk_id: r for r in self.semantic.search(query, top_k=k, filters=filters)}
        kw_results = {r.chunk.chunk_id: r for r in self.keyword.search(query, top_k=k, filters=filters)}

        # 合并评分
        all_ids = set(sem_results.keys()) | set(kw_results.keys())
        merged: list[SearchResult] = []

        for cid in all_ids:
            sem_score = sem_results[cid].score if cid in sem_results else 0.0
            kw_score = kw_results[cid].score if cid in kw_results else 0.0

            combined = (
                self.semantic_weight * sem_score
                + self.keyword_weight * kw_score
            )

            chunk = sem_results[cid].chunk if cid in sem_results else kw_results[cid].chunk
            merged.append(SearchResult(
                chunk=chunk,
                score=min(1.0, combined),
                match_type="hybrid",
            ))

        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:top_k]

    def set_weights(self, semantic_weight: float, keyword_weight: float) -> None:
        total = semantic_weight + keyword_weight
        if total == 0:
            raise ValueError("权重之和不能为 0")
        self.semantic_weight = semantic_weight / total
        self.keyword_weight = keyword_weight / total
