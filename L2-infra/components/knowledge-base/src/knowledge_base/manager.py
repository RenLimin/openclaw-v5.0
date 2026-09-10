"""知识管理 — 文档 CRUD + 分类 + 标签 + 持久化。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .document import Document


class KnowledgeManager:
    """知识库管理器 — 负责文档元数据管理、分类、标签、持久化。

    不涉及向量和检索，那是 index/retriever 的事。
    """

    def __init__(self, storage_path: str | Path | None = None):
        self._docs: dict[str, Document] = {}
        # 分类索引
        self._by_category: dict[str, set[str]] = defaultdict(set)
        # 标签索引
        self._by_tag: dict[str, set[str]] = defaultdict(set)
        # 存储路径（JSON 文件）
        self._storage_path = Path(storage_path) if storage_path else None

    @property
    def count(self) -> int:
        return len(self._docs)

    def add(self, doc: Document) -> str:
        """添加文档，返回 doc_id。"""
        if doc.doc_id in self._docs:
            # 更新
            self._remove_from_indexes(doc.doc_id)
        self._docs[doc.doc_id] = doc
        self._add_to_indexes(doc)
        return doc.doc_id

    def add_batch(self, docs: list[Document]) -> list[str]:
        return [self.add(d) for d in docs]

    def get(self, doc_id: str) -> Document | None:
        return self._docs.get(doc_id)

    def delete(self, doc_id: str) -> bool:
        if doc_id not in self._docs:
            return False
        self._remove_from_indexes(doc_id)
        del self._docs[doc_id]
        return True

    def update(self, doc_id: str, **fields: Any) -> bool:
        """更新文档的指定字段。"""
        doc = self._docs.get(doc_id)
        if doc is None:
            return False

        self._remove_from_indexes(doc_id)

        for key, value in fields.items():
            if hasattr(doc, key):
                setattr(doc, key, value)

        doc.updated_at = datetime.utcnow().isoformat() + "Z"
        self._add_to_indexes(doc)
        return True

    def list(self, category: str | None = None, tag: str | None = None,
             limit: int | None = None) -> list[Document]:
        """列出文档，可按分类/标签过滤。"""
        doc_ids: set[str] | None = None

        if category:
            doc_ids = set(self._by_category.get(category, set()))
        if tag:
            tag_docs = set(self._by_tag.get(tag, set()))
            doc_ids = tag_docs if doc_ids is None else doc_ids & tag_docs

        if doc_ids is None:
            result = list(self._docs.values())
        else:
            result = [self._docs[did] for did in doc_ids if did in self._docs]

        # 按更新时间倒序
        result.sort(key=lambda d: d.updated_at or d.created_at, reverse=True)

        if limit:
            result = result[:limit]
        return result

    def categories(self) -> list[tuple[str, int]]:
        """所有分类及其文档数，按数量倒序。"""
        result = [(cat, len(docs)) for cat, docs in self._by_category.items()]
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def tags(self, min_count: int = 1) -> list[tuple[str, int]]:
        """所有标签及其文档数。"""
        result = [(tag, len(docs)) for tag, docs in self._by_tag.items()
                  if len(docs) >= min_count]
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def search_metadata(self, keyword: str) -> list[Document]:
        """按标题/标签/分类搜索（元数据级别的搜索，非语义检索）。"""
        kw = keyword.lower()
        results: list[Document] = []
        for doc in self._docs.values():
            if (
                kw in doc.title.lower()
                or any(kw in t.lower() for t in doc.tags)
                or kw in doc.category.lower()
            ):
                results.append(doc)
        results.sort(key=lambda d: d.updated_at or d.created_at, reverse=True)
        return results

    def stats(self) -> dict[str, Any]:
        """统计信息。"""
        return {
            "total_documents": len(self._docs),
            "categories": {cat: len(docs) for cat, docs in self._by_category.items()},
            "tags_count": len(self._by_tag),
            "total_chars": sum(d.char_count for d in self._docs.values()),
            "total_words": sum(d.word_count for d in self._docs.values()),
        }

    # ---- 持久化 ----

    def save(self, path: str | Path | None = None) -> None:
        """保存到 JSON 文件。"""
        p = Path(path) if path else self._storage_path
        if p is None:
            raise ValueError("未指定存储路径")

        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "documents": [self._doc_to_dict(d) for d in self._docs.values()],
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._storage_path = p

    @classmethod
    def load(cls, path: str | Path) -> "KnowledgeManager":
        """从 JSON 文件加载。"""
        p = Path(path)
        if not p.exists():
            # 不存在就返回空的 manager
            mgr = cls(storage_path=p)
            return mgr

        data = json.loads(p.read_text(encoding="utf-8"))
        mgr = cls(storage_path=p)
        for item in data.get("documents", []):
            doc = cls._dict_to_doc(item)
            mgr.add(doc)
        return mgr

    # ---- 内部方法 ----

    def _add_to_indexes(self, doc: Document) -> None:
        if doc.category:
            self._by_category[doc.category].add(doc.doc_id)
        for tag in doc.tags:
            if tag:
                self._by_tag[tag].add(doc.doc_id)

    def _remove_from_indexes(self, doc_id: str) -> None:
        doc = self._docs.get(doc_id)
        if doc is None:
            return
        if doc.category and doc_id in self._by_category.get(doc.category, set()):
            self._by_category[doc.category].discard(doc_id)
            if not self._by_category[doc.category]:
                del self._by_category[doc.category]
        for tag in doc.tags:
            if tag and doc_id in self._by_tag.get(tag, set()):
                self._by_tag[tag].discard(doc_id)
                if not self._by_tag[tag]:
                    del self._by_tag[tag]

    @staticmethod
    def _doc_to_dict(doc: Document) -> dict[str, Any]:
        return {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "content": doc.content,
            "source": doc.source,
            "doc_type": doc.doc_type,
            "category": doc.category,
            "tags": list(doc.tags),
            "metadata": doc.metadata,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }

    @staticmethod
    def _dict_to_doc(data: dict[str, Any]) -> Document:
        return Document(
            doc_id=data.get("doc_id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            source=data.get("source", ""),
            doc_type=data.get("doc_type", "markdown"),
            category=data.get("category", ""),
            tags=list(data.get("tags", [])),
            metadata=dict(data.get("metadata", {})),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
