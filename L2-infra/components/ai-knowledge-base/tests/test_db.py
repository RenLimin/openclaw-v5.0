"""
Tests for database operations
"""
import tempfile
import os
from ai_kb.db import AIKB


def test_init_db():
    """Test database initialization"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        kb = AIKB(db_path)
        kb.init_db()

        # Check tables exist
        tables = [
            "domain", "collection", "entity", "entity_attr",
            "doc_asset", "doc_chunk", "kb_relation", "kb_feedback",
            "kb_migration", "kb_audit_log", "kb_template",
            "entity_fts", "chunk_fts"
        ]

        kb.connect()
        for table in tables:
            cursor = kb.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            assert cursor.fetchone() is not None, f"Table {table} missing"

        kb.close()
        assert True
    finally:
        os.unlink(db_path)


def test_domain_operations():
    """Test domain create/get"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        kb = AIKB(db_path)
        kb.init_db()
        domain_id = kb.get_or_create_domain("Test Domain", "test-domain", "Test description")
        assert domain_id > 0

        domains = kb.get_all_domains()
        assert len(domains) == 1
        assert domains[0]['code'] == 'test-domain'

        kb.close()
    finally:
        os.unlink(db_path)


def test_add_feedback():
    """Test adding feedback"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    try:
        kb = AIKB(db_path)
        kb.init_db()
        domain_id = kb.get_or_create_domain("Test Domain", "test-domain", "Test description")
        collection_id = kb.get_or_create_collection(domain_id, "test")
        entity_id = kb.create_entity(domain_id, collection_id, "product", None, "test", None, None, "1.0", "active", "test")

        # Add feedback
        fb_id = kb.add_feedback("test query", "useful", "test answer", entity_id=entity_id)
        assert fb_id > 0

        stats = kb.get_feedback_stats_for_entity(entity_id)
        assert stats.get('useful', 0) == 1

        kb.close()
    finally:
        os.unlink(db_path)
