"""测试：文本分块器"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from knowledge_base.chunker import CharacterChunker, TokenChunker, SemanticChunker
from knowledge_base.document import Document


def _make_doc(text: str, doc_type: str = "markdown") -> Document:
    return Document(content=text, doc_id="test-doc", title="测试", doc_type=doc_type)


def test_character_chunker_basic():
    text = "测试文本。" * 50  # 250 字
    doc = _make_doc(text, doc_type="plaintext")
    chunker = CharacterChunker(chunk_size=100, chunk_overlap=10)
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 2
    assert all(len(c.content) > 0 for c in chunks)
    # 第一块 doc_id 正确
    assert chunks[0].doc_id == "test-doc"


def test_character_chunker_short_text():
    text = "很短的文本"
    doc = _make_doc(text, doc_type="plaintext")
    chunker = CharacterChunker(chunk_size=500, chunk_overlap=50)
    chunks = chunker.chunk(doc)
    assert len(chunks) == 1
    assert chunks[0].content == "很短的文本"


def test_character_chunker_empty():
    doc = _make_doc("", doc_type="plaintext")
    chunker = CharacterChunker()
    chunks = chunker.chunk(doc)
    assert len(chunks) == 0


def test_token_chunker_basic():
    text = "这是一段中文测试文本。" * 20
    doc = _make_doc(text, doc_type="plaintext")
    chunker = TokenChunker(chunk_size=50, chunk_overlap=5)
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 2
    assert all(c.content for c in chunks)


def test_semantic_chunker_markdown():
    text = """# 第一章

这是第一章的内容，讲了很多事情。

## 1.1 小节

小节内容一。

# 第二章

这是第二章的内容。

## 2.1 小节

小节内容二。
"""
    doc = _make_doc(text, doc_type="markdown")
    chunker = SemanticChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 2
    # 检查块的 metadata 里有 section 信息
    has_sections = any("section" in c.metadata for c in chunks)
    assert has_sections


def test_semantic_chunker_plain_fallback():
    text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
    doc = _make_doc(text, doc_type="plaintext")
    chunker = SemanticChunker(chunk_size=50, chunk_overlap=5)
    chunks = chunker.chunk(doc)
    assert len(chunks) >= 1
