"""文档模型 — Document / Chunk / SearchResult。"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Document:
    """一篇完整的文档。

    Attributes:
        doc_id: 唯一标识，不填则自动生成
        title: 文档标题
        content: 原始内容（纯文本或 Markdown）
        source: 来源标识（文件路径 / URL / 手动录入等）
        doc_type: 文档类型（markdown / plaintext / code / ...）
        category: 分类
        tags: 标签列表
        metadata: 附加元数据（frontmatter 等）
        created_at: 创建时间
        updated_at: 更新时间
    """
    content: str
    doc_id: str = ""
    title: str = ""
    source: str = ""
    doc_type: str = "markdown"
    category: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.doc_id:
            self.doc_id = self._generate_id()
        now = datetime.utcnow().isoformat() + "Z"
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.title:
            # 从内容首行推导标题
            first_line = self.content.strip().splitlines()[0] if self.content.strip() else ""
            self.title = first_line.lstrip("# ").strip()[:120] or "(untitled)"

    def _generate_id(self) -> str:
        """基于内容 + source 生成稳定 ID。"""
        base = self.source or self.content[:200]
        return "doc-" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]

    @property
    def word_count(self) -> int:
        return len(self.content.split())

    @property
    def char_count(self) -> int:
        return len(self.content)


@dataclass
class Chunk:
    """文档的一个分块（用于向量化和检索）。

    Attributes:
        chunk_id: 块唯一 ID
        doc_id: 所属文档 ID
        content: 块文本内容
        index: 在文档中的序号（0-based）
        embedding: 向量（可能为 None，尚未向量化时）
        metadata: 块级元数据
    """
    content: str
    doc_id: str
    chunk_id: str = ""
    index: int = 0
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id:
            self.chunk_id = f"{self.doc_id}_chunk{self.index}"


@dataclass
class SearchResult:
    """检索结果条目。

    Attributes:
        chunk: 命中的块
        score: 相关性分数（0~1，越大越相关）
        document: 关联的完整文档（可能为 None，取决于检索模式）
        match_type: 匹配类型（semantic / keyword / hybrid）
    """
    chunk: Chunk
    score: float
    document: Document | None = None
    match_type: str = "semantic"

    @property
    def title(self) -> str:
        return self.document.title if self.document else self.chunk.doc_id

    @property
    def snippet(self) -> str:
        """返回前 200 字符的摘要。"""
        text = self.chunk.content.strip()
        return text if len(text) <= 200 else text[:200] + "…"
