"""测试：文档模型"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from knowledge_base.document import Document, Chunk


def test_document_default_id():
    doc = Document(content="hello world")
    assert doc.doc_id.startswith("doc-")
    assert len(doc.doc_id) > 10


def test_document_title_from_content():
    doc = Document(content="# 我的标题\n\n正文内容")
    assert doc.title == "我的标题"


def test_document_custom_id():
    doc = Document(content="test", doc_id="custom-id", title="测试")
    assert doc.doc_id == "custom-id"
    assert doc.title == "测试"


def test_document_counts():
    doc = Document(content="hello world foo bar")
    assert doc.word_count == 4
    assert doc.char_count == len("hello world foo bar")


def test_chunk_generation():
    chunk = Chunk(content="一段测试文本", doc_id="doc-123", index=0)
    assert chunk.chunk_id == "doc-123_chunk0"
    assert chunk.embedding is None
