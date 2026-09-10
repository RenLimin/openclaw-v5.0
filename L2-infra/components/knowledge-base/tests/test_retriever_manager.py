"""测试：检索器 + 知识管理器"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from knowledge_base.embedder import MockEmbedder
from knowledge_base.index import SimpleIndex
from knowledge_base.retriever import SemanticRetriever, KeywordRetriever, HybridRetriever
from knowledge_base.manager import KnowledgeManager
from knowledge_base.document import Document, Chunk


def test_keyword_retriever_basic():
    chunks = [
        Chunk(chunk_id="c1", doc_id="d1", content="python 编程入门教程 基础语法"),
        Chunk(chunk_id="c2", doc_id="d2", content="机器学习算法 神经网络 深度学习"),
        Chunk(chunk_id="c3", doc_id="d3", content="美食烹饪 菜谱大全 家常菜做法"),
    ]
    retriever = KeywordRetriever(chunks)
    results = retriever.search("python 教程", top_k=3)
    assert len(results) > 0
    assert results[0].chunk.chunk_id == "c1"
    assert 0 < results[0].score <= 1.0


def test_keyword_retriever_no_match():
    chunks = [Chunk(chunk_id="c1", doc_id="d1", content="完全无关的内容")]
    retriever = KeywordRetriever(chunks)
    results = retriever.search("量子物理", top_k=5)
    assert len(results) == 0


def test_semantic_retriever_basic():
    emb = MockEmbedder(dimension=128)
    idx = SimpleIndex(dimension=128)

    texts = [
        "python 编程 代码 开发",
        "人工智能 机器学习 深度学习 神经网络",
        "美食 烹饪 食谱 厨房",
    ]
    for i, text in enumerate(texts):
        chunk = Chunk(
            chunk_id=f"c{i}", doc_id=f"d{i}", content=text,
            index=i, embedding=emb.embed(text),
        )
        idx.add(chunk)

    retriever = SemanticRetriever(idx, emb)
    results = retriever.search("机器学习 深度学习", top_k=3)
    assert len(results) == 3
    # 分数应该降序排列
    for i in range(len(results) - 1):
        assert results[i].score >= results[i + 1].score
    assert results[0].score > 0
    assert results[0].match_type == "semantic"
    # 所有结果都是 SearchResult 且 chunk 非空
    assert all(r.chunk.content for r in results)


def test_hybrid_retriever():
    emb = MockEmbedder(dimension=128)
    idx = SimpleIndex(dimension=128)

    texts = [
        "python 编程 代码 开发 入门",
        "机器学习 深度学习 神经网络 算法",
        "美食 烹饪 食谱 厨房 菜谱",
    ]
    chunks_list = []
    for i, text in enumerate(texts):
        chunk = Chunk(
            chunk_id=f"c{i}", doc_id=f"d{i}", content=text,
            index=i, embedding=emb.embed(text),
        )
        idx.add(chunk)
        chunks_list.append(chunk)

    sem = SemanticRetriever(idx, emb)
    kw = KeywordRetriever(chunks_list)
    hybrid = HybridRetriever(sem, kw, semantic_weight=0.5, keyword_weight=0.5)

    results = hybrid.search("算法 机器学习", top_k=3)
    assert len(results) > 0
    assert results[0].match_type == "hybrid"
    assert results[0].score > 0


def test_hybrid_weight_change():
    emb = MockEmbedder(dimension=64)
    idx = SimpleIndex(dimension=64)
    chunks_list = []
    for i, text in enumerate(["python 编程", "机器学习 算法", "美食 烹饪"]):
        chunk = Chunk(
            chunk_id=f"c{i}", doc_id=f"d{i}", content=text,
            index=i, embedding=emb.embed(text),
        )
        idx.add(chunk)
        chunks_list.append(chunk)

    sem = SemanticRetriever(idx, emb)
    kw = KeywordRetriever(chunks_list)
    hybrid = HybridRetriever(sem, kw)
    hybrid.set_weights(0.9, 0.1)
    assert abs(hybrid.semantic_weight - 0.9) < 0.01


def test_manager_crud():
    mgr = KnowledgeManager()
    doc = Document(title="测试文档", content="内容", doc_id="d1", category="tech", tags=["python", "code"])

    # Create
    doc_id = mgr.add(doc)
    assert doc_id == "d1"
    assert mgr.count == 1

    # Read
    got = mgr.get("d1")
    assert got is not None
    assert got.title == "测试文档"
    assert mgr.get("nonexistent") is None

    # Update
    ok = mgr.update("d1", title="更新后的标题")
    assert ok is True
    assert mgr.get("d1").title == "更新后的标题"

    # Delete
    ok = mgr.delete("d1")
    assert ok is True
    assert mgr.count == 0
    assert mgr.delete("d1") is False


def test_manager_categories_and_tags():
    mgr = KnowledgeManager()
    docs = [
        Document(title="A", content="a", doc_id="d1", category="tech", tags=["python", "code"]),
        Document(title="B", content="b", doc_id="d2", category="tech", tags=["python", "ai"]),
        Document(title="C", content="c", doc_id="d3", category="food", tags=["cooking"]),
    ]
    for d in docs:
        mgr.add(d)

    # 分类
    cats = mgr.categories()
    assert ("tech", 2) in cats
    assert ("food", 1) in cats

    # 标签
    tags = mgr.tags()
    tag_dict = dict(tags)
    assert tag_dict["python"] == 2
    assert tag_dict["code"] == 1

    # 按分类过滤
    tech_docs = mgr.list(category="tech")
    assert len(tech_docs) == 2

    # 按标签过滤
    py_docs = mgr.list(tag="python")
    assert len(py_docs) == 2

    # 联合过滤
    combined = mgr.list(category="tech", tag="ai")
    assert len(combined) == 1
    assert combined[0].doc_id == "d2"


def test_manager_persistence():
    mgr = KnowledgeManager()
    doc = Document(title="持久化测试", content="测试内容", doc_id="p1",
                   category="test", tags=["persist"])
    mgr.add(doc)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "kb.json"
        mgr.save(path)
        assert path.exists()

        # 加载
        mgr2 = KnowledgeManager.load(path)
        assert mgr2.count == 1
        got = mgr2.get("p1")
        assert got is not None
        assert got.title == "持久化测试"
        assert got.category == "test"
        assert "persist" in got.tags


def test_manager_stats():
    mgr = KnowledgeManager()
    mgr.add(Document(title="a", content="hello world", doc_id="d1", category="t1"))
    mgr.add(Document(title="b", content="foo bar baz", doc_id="d2", category="t2", tags=["x"]))

    stats = mgr.stats()
    assert stats["total_documents"] == 2
    assert "t1" in stats["categories"]
    assert stats["tags_count"] == 1
    assert stats["total_chars"] > 0


def test_manager_search_metadata():
    mgr = KnowledgeManager()
    mgr.add(Document(title="Python 教程", content="...", doc_id="d1",
                     category="tech", tags=["python", "入门"]))
    mgr.add(Document(title="烹饪指南", content="...", doc_id="d2",
                     category="food", tags=["美食"]))

    results = mgr.search_metadata("python")
    assert len(results) == 1
    assert results[0].doc_id == "d1"

    results = mgr.search_metadata("美食")
    assert len(results) == 1
