"""向量索引 — 存储与检索向量。"""

from __future__ import annotations

import json
import math
import struct
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .document import Chunk


class VectorIndex(ABC):
    """向量索引抽象基类。"""

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...

    @property
    @abstractmethod
    def size(self) -> int:
        """索引中的向量数量。"""
        ...

    @abstractmethod
    def add(self, chunk: Chunk) -> None:
        """添加一个带向量的块。"""
        ...

    def add_batch(self, chunks: list[Chunk]) -> None:
        """批量添加。"""
        for c in chunks:
            self.add(c)

    @abstractmethod
    def search(self, query_vec: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        """查询最相似的 top_k 个块，返回 [(chunk_id, score), ...]。

        score 范围 0~1，越大越相似。
        """
        ...

    @abstractmethod
    def get(self, chunk_id: str) -> Chunk | None:
        """根据 chunk_id 获取块。"""
        ...

    @abstractmethod
    def delete(self, chunk_id: str) -> bool:
        """删除指定块。"""
        ...

    @abstractmethod
    def clear(self) -> None:
        """清空索引。"""
        ...

    @abstractmethod
    def save(self, path: str | Path) -> None:
        """保存索引到文件。"""
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> "VectorIndex":
        """从文件加载索引。"""
        ...


class SimpleIndex(VectorIndex):
    """简单余弦相似度索引 — 纯 Python 实现，无需额外依赖。

    适合中小规模（< 10000 条）知识库。规模大了再上 FAISS。
    """

    def __init__(self, dimension: int = 128):
        self._dimension = dimension
        # chunk_id -> Chunk
        self._chunks: dict[str, Chunk] = {}
        # doc_id -> [chunk_id, ...]
        self._doc_index: dict[str, list[str]] = {}

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def size(self) -> int:
        return len(self._chunks)

    def add(self, chunk: Chunk) -> None:
        if chunk.embedding is None:
            raise ValueError(f"Chunk {chunk.chunk_id} 没有 embedding")
        if len(chunk.embedding) != self._dimension:
            raise ValueError(
                f"维度不匹配: 期望 {self._dimension}, 实际 {len(chunk.embedding)}"
            )
        self._chunks[chunk.chunk_id] = chunk
        # 维护 doc 索引
        if chunk.doc_id not in self._doc_index:
            self._doc_index[chunk.doc_id] = []
        if chunk.chunk_id not in self._doc_index[chunk.doc_id]:
            self._doc_index[chunk.doc_id].append(chunk.chunk_id)

    def search(self, query_vec: list[float], top_k: int = 10,
               doc_ids: set[str] | None = None) -> list[tuple[str, float]]:
        if len(query_vec) != self._dimension:
            raise ValueError(
                f"查询向量维度不匹配: 期望 {self._dimension}, 实际 {len(query_vec)}"
            )

        # 归一化查询向量
        q_norm = self._l2_normalize(query_vec)

        results: list[tuple[str, float]] = []
        for cid, chunk in self._chunks.items():
            if doc_ids and chunk.doc_id not in doc_ids:
                continue
            if chunk.embedding is None:
                continue
            score = self._cosine_similarity(q_norm, chunk.embedding)
            results.append((cid, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def search_by_doc(self, query_vec: list[float], doc_ids: list[str],
                      top_k: int = 10) -> list[tuple[str, float]]:
        """限定在指定文档集合内搜索。"""
        return self.search(query_vec, top_k, doc_ids=set(doc_ids))

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def get_by_doc(self, doc_id: str) -> list[Chunk]:
        """获取一个文档的所有块。"""
        cids = self._doc_index.get(doc_id, [])
        return [self._chunks[cid] for cid in cids if cid in self._chunks]

    def delete(self, chunk_id: str) -> bool:
        chunk = self._chunks.pop(chunk_id, None)
        if chunk is None:
            return False
        # 从 doc 索引中移除
        if chunk.doc_id in self._doc_index:
            self._doc_index[chunk.doc_id] = [
                c for c in self._doc_index[chunk.doc_id] if c != chunk_id
            ]
            if not self._doc_index[chunk.doc_id]:
                del self._doc_index[chunk.doc_id]
        return True

    def delete_by_doc(self, doc_id: str) -> int:
        """删除一个文档的所有块，返回删除数量。"""
        cids = list(self._doc_index.get(doc_id, []))
        for cid in cids:
            self._chunks.pop(cid, None)
        if doc_id in self._doc_index:
            del self._doc_index[doc_id]
        return len(cids)

    def clear(self) -> None:
        self._chunks.clear()
        self._doc_index.clear()

    def save(self, path: str | Path) -> None:
        """保存索引：JSON 元数据 + 二进制向量文件。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        # 元数据 JSON
        meta: dict[str, Any] = {
            "version": 1,
            "dimension": self._dimension,
            "count": len(self._chunks),
            "chunks": [],
            "doc_index": self._doc_index,
        }
        for cid, chunk in self._chunks.items():
            meta["chunks"].append({
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "index": chunk.index,
                "content": chunk.content,
                "metadata": chunk.metadata,
            })

        meta_path = p.with_suffix(".json")
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 向量二进制文件（float32 紧凑存储）
        vec_path = p.with_suffix(".vec.bin")
        with open(vec_path, "wb") as f:
            # 写入头部：维度 + 数量
            f.write(struct.pack("<II", self._dimension, len(self._chunks)))
            # 按 chunk_id 排序保证顺序稳定
            for cid in sorted(self._chunks.keys()):
                chunk = self._chunks[cid]
                if chunk.embedding:
                    f.write(struct.pack(f"<{self._dimension}f", *chunk.embedding))
                else:
                    f.write(struct.pack(f"<{self._dimension}f", *([0.0] * self._dimension)))

    @classmethod
    def load(cls, path: str | Path) -> "SimpleIndex":
        p = Path(path)
        meta_path = p.with_suffix(".json")
        vec_path = p.with_suffix(".vec.bin")

        if not meta_path.exists():
            raise FileNotFoundError(f"索引元数据不存在: {meta_path}")

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        dimension = meta["dimension"]
        idx = cls(dimension=dimension)

        # 加载元数据
        chunks_map: dict[str, Chunk] = {}
        for item in meta["chunks"]:
            chunk = Chunk(
                chunk_id=item["chunk_id"],
                doc_id=item["doc_id"],
                content=item["content"],
                index=item["index"],
                metadata=item.get("metadata", {}),
            )
            chunks_map[chunk.chunk_id] = chunk

        # 加载向量
        if vec_path.exists():
            with open(vec_path, "rb") as f:
                header = f.read(8)
                dim, count = struct.unpack("<II", header)
                if dim != dimension:
                    raise ValueError(f"维度不匹配: 元数据 {dimension}, 向量文件 {dim}")
                for i in range(count):
                    raw = f.read(dim * 4)
                    if len(raw) < dim * 4:
                        break
                    vec = list(struct.unpack(f"<{dim}f", raw))
                    # 按排序后的顺序对应
                    sorted_ids = sorted(chunks_map.keys())
                    if i < len(sorted_ids):
                        chunks_map[sorted_ids[i]].embedding = vec

        idx._chunks = chunks_map
        idx._doc_index = meta.get("doc_index", {})
        return idx

    def all_chunk_ids(self) -> list[str]:
        return list(self._chunks.keys())

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """余弦相似度，假设 vec_b 已归一化。"""
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        # 归一化后的点积就是余弦相似度
        return max(0.0, min(1.0, dot))

    @staticmethod
    def _l2_normalize(vec: list[float]) -> list[float]:
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return vec
        return [x / norm for x in vec]
