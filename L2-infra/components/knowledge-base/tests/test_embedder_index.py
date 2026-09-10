"""测试：向量化 + 向量索引"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from knowledge_base.embedder import MockEmbedder
from knowledge_base.index import SimpleIndex
from knowledge_base.document import Chunk


def test_mock_embedder_dimension():
    emb = MockEmbedder(dimension=64)
    assert emb.dimension == 64


def test_mock_embedder_deterministic():
    """相同文本得到相同向量。"""
    emb = MockEmbedder(dimension=128)
    v1 = emb.embed("hello world")
    v2 = emb.embed("hello world")
    assert v1 == v2
    assert len(v1) == 128


def test_mock_embedder_normalized():
    """向量应该是归一化的（L2 norm ≈ 1）。"""
    import math
    emb = MockEmbedder(dimension=128)
    v = emb.embed("测试文本")
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 0.01


def test_mock_embedder_similarity():
    """相似文本相似度高，不相似的低。"""
    emb = MockEmbedder(dimension=256)
    v_ai1 = emb.embed("人工智能机器学习深度学习")
    v_ai2 = emb.embed("机器学习神经网络人工智能")
    v_food = emb.embed("今天中午吃什么好吃的")

    sim_ai = sum(a * b for a, b in zip(v_ai1, v_ai2))
    sim_diff = sum(a * b for a, b in zip(v_ai1, v_food))
    # 相似对的相似度应该高于不相似对
    assert sim_ai > sim_diff


def test_simple_index_add_search():
    emb = MockEmbedder(dimension=128)
    idx = SimpleIndex(dimension=128)

    texts = [
        "python 编程教程 入门",
        "机器学习 人工智能 算法",
        "美食 烹饪 菜谱",
    ]
    for i, text in enumerate(texts):
        chunk = Chunk(
            chunk_id=f"chunk-{i}",
            doc_id=f"doc-{i}",
            content=text,
            index=i,
            embedding=emb.embed(text),
        )
        idx.add(chunk)

    assert idx.size == 3

    # 查询与 AI 相关的
    q = emb.embed("深度学习 神经网络")
    results = idx.search(q, top_k=2)
    assert len(results) == 2
    # 第一个应该是 AI 相关的（chunk-1）
    assert results[0][0] == "chunk-1"
    assert 0 <= results[0][1] <= 1


def test_simple_index_delete():
    emb = MockEmbedder(dimension=64)
    idx = SimpleIndex(dimension=64)

    chunk = Chunk(
        chunk_id="c1",
        doc_id="d1",
        content="test",
        embedding=emb.embed("test"),
    )
    idx.add(chunk)
    assert idx.size == 1
    assert idx.get("c1") is not None

    assert idx.delete("c1") is True
    assert idx.size == 0
    assert idx.get("c1") is None
    assert idx.delete("c1") is False


def test_simple_index_persistence():
    emb = MockEmbedder(dimension=64)
    idx = SimpleIndex(dimension=64)

    for i in range(5):
        chunk = Chunk(
            chunk_id=f"c{i}",
            doc_id=f"d{i}",
            content=f"文档内容 {i} 测试文本",
            index=i,
            embedding=emb.embed(f"文档内容 {i} 测试文本"),
        )
        idx.add(chunk)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_index"
        idx.save(path)

        # 检查文件生成
        assert (path.with_suffix(".json")).exists()
        assert (path.with_suffix(".vec.bin")).exists()

        # 加载
        idx2 = SimpleIndex.load(path)
        assert idx2.size == 5
        assert idx2.dimension == 64

        # 查询结果一致
        q = emb.embed("文档内容 1")
        r1 = idx.search(q, top_k=3)
        r2 = idx2.search(q, top_k=3)
        assert [r[0] for r in r1] == [r[0] for r in r2]


def test_simple_index_clear():
    emb = MockEmbedder(dimension=32)
    idx = SimpleIndex(dimension=32)
    chunk = Chunk(chunk_id="c1", doc_id="d1", content="test", embedding=emb.embed("test"))
    idx.add(chunk)
    assert idx.size == 1
    idx.clear()
    assert idx.size == 0
