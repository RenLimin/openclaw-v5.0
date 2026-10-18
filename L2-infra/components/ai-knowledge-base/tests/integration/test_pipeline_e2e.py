"""
Integration tests: full pipeline (ingest -> retrieve -> serve -> mcp -> audit)
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from ai_kb.db import AIKB
from ai_kb.ingestion import IngestionPipeline
from ai_kb.search import HybridSearch
from ai_kb.api import AIKBService
from ai_kb.audit import AuditLogger
from mcp.server import KBMCPHandler


@pytest.fixture()
def kb_env(tmp_path):
    """Create a KB with one ingested document"""
    db_path = str(tmp_path / "test.db")
    kb = AIKB(db_path)
    kb.init_db()
    domain_id = kb.get_or_create_domain("Demo KB", "demo", "integration test")

    doc = tmp_path / "product.md"
    doc.write_text(
        "# APP加固产品说明\n\n"
        "## 产品功能\n\n"
        "APP加固是梆梆安全的核心产品，提供以下功能：\n"
        "- 代码混淆：对应用代码进行混淆处理，防止逆向分析\n"
        "- 防调试：检测并阻止调试器附加\n"
        "- 完整性校验：检测应用是否被篡改\n"
        "- 防注入：防止注入攻击\n\n"
        "## 技术架构\n\n"
        "APP加固采用服务端加固+客户端SDK的架构模式。\n"
        "服务端负责策略配置和签名，客户端SDK负责运行时保护。\n\n"
        "## 支持平台\n\n"
        "支持Android和iOS两大平台，覆盖主流应用商店渠道。\n"
    )

    pipe = IngestionPipeline(kb)
    result = pipe.ingest_single_file(domain_id, str(doc))
    assert result.success, result.error
    assert result.doc_id is not None
    assert result.chunks_created >= 1

    yield kb, domain_id, db_path, result
    kb.close()


def test_full_pipeline_query_with_sources(kb_env):
    """Query returns answer with mandatory source references"""
    kb, domain_id, db_path, ingest_result = kb_env

    service = AIKBService(db_path, "demo")
    resp = service.query("APP加固有什么功能", top_k=3, format="markdown")

    assert resp["source_count"] >= 1
    assert resp["sources"], "must have sources"
    first = resp["sources"][0]
    assert first["entity_name"], "source must include entity name"
    assert first["file_name"], "source must include file name"
    assert first["snippet"], "source must include original snippet"
    assert resp["markdown"], "markdown answer must include source section"
    assert "来源引用" in resp["markdown"]
    service.close()


def test_hybrid_search_multichannel(kb_env):
    """HybridSearch returns results across channels"""
    kb, domain_id, db_path, ingest_result = kb_env

    search = HybridSearch(kb, domain_id)
    results = search.search("APP加固", top_k=5)
    assert len(results) >= 1
    # 返回结构: {entity, doc, chunk, similarity}
    assert "similarity" in results[0]
    assert results[0]["similarity"] > 0
    assert "entity" in results[0]
    assert "chunk" in results[0]


def test_mcp_handler_end_to_end(kb_env):
    """MCP handler exposes tools and resources"""
    kb, domain_id, db_path, ingest_result = kb_env

    handler = KBMCPHandler(db_path, "demo")
    tools = handler.list_tools()
    assert len(tools) >= 9
    names = {t["name"] for t in tools}
    assert {"kb_query", "kb_stats", "kb_list_entities", "kb_add_feedback"} <= names

    resp = handler.call_tool("kb_query", {"question": "APP加固", "format": "markdown"})
    assert resp["source_count"] >= 1

    stats = handler.call_tool("kb_stats", {})
    assert stats["entities"] >= 1 and stats["documents"] >= 1

    res = handler.read_resource(f"kb://demo/entities/{ingest_result.doc_id}")
    assert res is not None and "data" in res
    handler.close()


def test_audit_logging(kb_env):
    """Audit logger records and queries operations"""
    kb, domain_id, db_path, ingest_result = kb_env

    logger = AuditLogger(kb)
    id1 = logger.log_query(user_id="u1", query="APP加固", source_count=1)
    id2 = logger.log_ingest(user_id="u1", file_name="product.md", doc_id=ingest_result.doc_id, chunks=1, success=True)
    assert id1 > 0 and id2 > 0

    logs = logger.query_logs(operation_type="query")
    assert len(logs) >= 1
    assert logs[0]["operation_type"] == "query"

    stats = logger.count_by_operation(days=7)
    assert stats.get("query", 0) >= 1
    assert stats.get("ingest", 0) >= 1


def test_feedback_flow(kb_env):
    """Feedback submit + low-score listing"""
    kb, domain_id, db_path, ingest_result = kb_env

    service = AIKBService(db_path, "demo")
    fid = service.add_feedback(
        query_text="APP加固", feedback_type="not_useful",
        user_id="u1", entity_id=ingest_result.doc_id,
    )
    assert fid["feedback_id"] > 0

    low = service.list_low_score_knowledge(threshold=1)
    assert isinstance(low, list)
    service.close()
