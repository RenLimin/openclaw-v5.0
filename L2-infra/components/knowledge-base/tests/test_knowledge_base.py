"""测试：KnowledgeBase 主类集成测试"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from knowledge_base.core import KnowledgeBase
from knowledge_base.document import Document
from knowledge_base.embedder import MockEmbedder


def test_kb_add_and_search():
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=128))

    kb.add_document(Document(
        doc_id="doc-python",
        title="Python 编程入门",
        content="Python 是一种简单易学的编程语言。Python 语法简洁，适合初学者入门学习。\n\nPython 可以用于 web 开发、数据分析、人工智能等多种领域。",
        category="tech",
        tags=["python", "编程", "入门"],
    ))
    kb.add_document(Document(
        doc_id="doc-ml",
        title="机器学习基础",
        content="机器学习是人工智能的一个分支。机器学习算法包括监督学习、无监督学习、强化学习。\n\n深度学习是机器学习的一个子领域，使用神经网络模型。",
        category="tech",
        tags=["机器学习", "AI", "深度学习"],
    ))
    kb.add_document(Document(
        doc_id="doc-food",
        title="家常菜做法",
        content="今天教大家做红烧肉。食材需要五花肉、冰糖、酱油、料酒。\n\n先把肉切块焯水，然后炒糖色，加入调料小火慢炖。",
        category="food",
        tags=["美食", "烹饪", "菜谱"],
    ))

    assert kb.count == 3
    assert kb.chunk_count >= 3

    # 搜索
    results = kb.search("机器学习 深度学习", limit=3, mode="semantic")
    assert len(results) > 0
    assert results[0].score > 0  # 至少第一个结果有正分
    # 排序正确
    for i in range(len(results) - 1):
        assert results[i].score >= results[i + 1].score


def test_kb_crud():
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=64))

    # Add
    doc_id = kb.add_document(Document(
        title="测试文档",
        content="这是一篇测试文档的内容。",
        category="test",
        tags=["test"],
    ))
    assert doc_id
    assert kb.count == 1

    # Get
    doc = kb.get_document(doc_id)
    assert doc is not None
    assert doc.title == "测试文档"

    # List with category
    docs = kb.list_documents(category="test")
    assert len(docs) == 1
    docs = kb.list_documents(category="nonexistent")
    assert len(docs) == 0

    # Delete
    ok = kb.delete_document(doc_id)
    assert ok is True
    assert kb.count == 0
    assert kb.get_document(doc_id) is None

    # Delete again
    ok = kb.delete_document(doc_id)
    assert ok is False


def test_kb_hybrid_mode():
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=64))

    kb.add_document(Document(
        doc_id="d1",
        title="Python 教程",
        content="Python 编程 Python 代码 Python 开发",
        category="tech",
        tags=["python"],
    ))
    kb.add_document(Document(
        doc_id="d2",
        title="美食教程",
        content="红烧肉 炒菜 菜谱 烹饪",
        category="food",
        tags=["美食"],
    ))

    results = kb.search("Python 编程", limit=5, mode="hybrid")
    assert len(results) > 0
    assert results[0].match_type == "hybrid"
    assert results[0].score > 0


def test_kb_keyword_mode():
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=64))

    kb.add_document(Document(
        doc_id="d1",
        title="Python 教程",
        content="Python 编程 Python 代码 开发入门",
        category="tech",
    ))

    results = kb.search("Python", limit=5, mode="keyword")
    assert len(results) > 0
    assert results[0].match_type == "keyword"


def test_kb_rebuild_index():
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=64))

    kb.add_document(Document(
        doc_id="d1", title="文档一", content="第一篇文档的内容", category="test",
    ))
    kb.add_document(Document(
        doc_id="d2", title="文档二", content="第二篇文档的内容", category="test",
    ))

    old_count = kb.chunk_count
    ok = kb.rebuild_index()
    assert ok is True
    assert kb.chunk_count == old_count
    assert kb.count == 2

    # 重建后仍可搜索
    results = kb.search("文档", limit=3)
    assert len(results) > 0


def test_kb_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Path(tmpdir) / "kb_store"

        # 创建并保存
        kb = KnowledgeBase(embedder=MockEmbedder(dimension=64), storage_dir=store)
        kb.add_document(Document(
            doc_id="persist-1",
            title="持久化测试文档",
            content="这是用于测试持久化的文档内容。",
            category="test",
            tags=["persist", "test"],
        ))
        kb.save()

        # 验证文件生成
        assert (store / "documents.json").exists()
        assert (store / "vector_index.json").exists()
        assert (store / "vector_index.vec.bin").exists()
        assert (store / "config.json").exists()

        # 加载
        kb2 = KnowledgeBase.load(store, embedder=MockEmbedder(dimension=64))
        assert kb2.count == 1
        doc = kb2.get_document("persist-1")
        assert doc is not None
        assert doc.title == "持久化测试文档"
        assert doc.category == "test"

        # 加载后可搜索
        results = kb2.search("持久化", limit=3)
        assert len(results) > 0


def test_kb_stats():
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=32))
    kb.add_document(Document(title="A", content="内容 A", doc_id="a", category="t1"))
    kb.add_document(Document(title="B", content="内容 B", doc_id="b", category="t1", tags=["x"]))

    info = kb.stats()
    assert info["total_documents"] == 2
    assert info["chunk_count"] >= 2
    assert info["vector_dimension"] == 32
    assert info["retrieval_mode"] == "hybrid"


def test_kb_add_string():
    """测试直接传字符串添加文档。"""
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=32))
    doc_id = kb.add_document("# 直接传字符串\n\n这是正文内容。", doc_type="markdown")
    assert doc_id
    assert kb.count == 1
    doc = kb.get_document(doc_id)
    assert doc.title == "直接传字符串"


def test_kb_retrieval_mode_switch():
    """测试切换检索模式。"""
    kb = KnowledgeBase(embedder=MockEmbedder(dimension=32))
    kb.add_document(Document(title="T", content="test content", doc_id="d1"))

    assert kb.retrieval_mode == "hybrid"
    kb.retrieval_mode = "keyword"
    assert kb.retrieval_mode == "keyword"

    results = kb.search("test", limit=3)
    assert len(results) > 0
    assert results[0].match_type == "keyword"

    # 非法模式应该报错
    try:
        kb.retrieval_mode = "invalid"
        assert False, "应该抛出 ValueError"
    except ValueError:
        pass
