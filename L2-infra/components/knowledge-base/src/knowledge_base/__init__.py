"""Knowledge Base 组件 — 通用知识库管理与检索。

提供文档解析、分块、向量化、索引构建、语义检索、知识管理六大子能力。
嵌入能力依赖 memory-embedding 组件（本地 GGUF embedding 模型）。
"""

from .core import KnowledgeBase
from .document import Document, Chunk, SearchResult
from .parser import DocumentParser, MarkdownParser, PlainTextParser, CodeParser
from .chunker import Chunker, SemanticChunker, CharacterChunker, TokenChunker
from .embedder import Embedder, LocalEmbedder, MockEmbedder
from .index import VectorIndex, SimpleIndex
from .retriever import Retriever, SemanticRetriever, KeywordRetriever, HybridRetriever
from .manager import KnowledgeManager

__all__ = [
    "KnowledgeBase",
    "Document", "Chunk", "SearchResult",
    "DocumentParser", "MarkdownParser", "PlainTextParser", "CodeParser",
    "Chunker", "SemanticChunker", "CharacterChunker", "TokenChunker",
    "Embedder", "LocalEmbedder", "MockEmbedder",
    "VectorIndex", "SimpleIndex",
    "Retriever", "SemanticRetriever", "KeywordRetriever", "HybridRetriever",
    "KnowledgeManager",
]

__version__ = "0.1.0"
