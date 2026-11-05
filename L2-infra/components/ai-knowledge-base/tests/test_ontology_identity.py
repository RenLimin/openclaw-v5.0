"""Unit tests for P1 IdentityService (operational ontology §2.1 / §3.1)."""
import os
import sqlite3
import tempfile

import pytest

from ai_kb.db import AIKB
from ai_kb.ontology import IdentityService, is_operational_object_type


@pytest.fixture()
def kb():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db = AIKB(db_path)
    db.init_db()
    db.init_ontology_identity_tables()
    db.get_or_create_domain("Test Domain", "test-domain", "Test")
    yield db
    db.close()
    os.unlink(db_path)


@pytest.fixture()
def svc(kb):
    return IdentityService(kb)


# --- migration / DDL ---

def test_migration_v8_registered(kb):
    assert kb.get_current_migration_version() == 8
    cursor = kb.execute("SELECT name FROM kb_migration WHERE version = 8")
    assert cursor.fetchone()[0] == "operational_ontology_identity"


def test_identity_tables_idempotent(kb):
    # 二次调用不报错、不重复登记
    kb.init_ontology_identity_tables()
    assert kb.get_current_migration_version() == 8


# --- register ---

def test_register_identity(svc):
    ident_id = svc.register_identity("test-domain", "contract", "HT-001", "oa",
                                     display_name="合同001")
    assert ident_id > 0
    rows = svc.list_identities("test-domain", "contract")
    assert len(rows) == 1
    assert rows[0]["canonical_key"] == "HT-001"
    assert rows[0]["status"] == "active"
    assert rows[0]["merged_into"] is None


def test_register_duplicate_canonical_key_conflict(svc):
    svc.register_identity("test-domain", "contract", "HT-001", "oa")
    with pytest.raises(sqlite3.IntegrityError):
        svc.register_identity("test-domain", "contract", "HT-001", "erp")


# --- alias / resolve (CWA) ---

def test_add_alias_and_resolve(svc):
    ident_id = svc.register_identity("test-domain", "contract", "HT-001", "oa")
    alias_id = svc.add_alias(ident_id, "erp", "ERP-777", confidence=0.9)
    assert alias_id > 0
    # SoR 自身键
    assert svc.resolve("oa", "HT-001") is None  # canonical_key 不是 alias
    # 别名命中
    assert svc.resolve("erp", "ERP-777") == ident_id


def test_resolve_miss_returns_none_cwa(svc):
    # 封闭世界：未注册的源键 = 不存在
    assert svc.resolve("oa", "NO-SUCH-KEY") is None


def test_duplicate_source_key_conflict(svc):
    a = svc.register_identity("test-domain", "contract", "HT-001", "oa")
    b = svc.register_identity("test-domain", "contract", "HT-002", "oa")
    svc.add_alias(a, "erp", "ERP-1")
    with pytest.raises(sqlite3.IntegrityError):
        svc.add_alias(b, "erp", "ERP-1")


# --- merge ---

def test_merge_soft_and_alias_transfer(svc):
    a = svc.register_identity("test-domain", "contract", "HT-001", "oa", "A")
    b = svc.register_identity("test-domain", "contract", "HT-002", "oa", "B")
    svc.add_alias(a, "erp", "ERP-1")
    svc.add_alias(b, "oa", "OA-DUP")

    record = svc.merge(a, b, actor="rex")
    assert record["from_id"] == a
    assert record["into_id"] == b

    # alias 转移到吸收方
    assert svc.resolve("erp", "ERP-1") == b
    assert svc.resolve("oa", "OA-DUP") == b

    src = svc.list_identities("test-domain", "contract", status="merged")
    assert len(src) == 1
    assert src[0]["id"] == a and src[0]["merged_into"] == b

    actives = svc.list_identities("test-domain", "contract", status="active")
    assert [r["id"] for r in actives] == [b]


def test_merge_self_rejected(svc):
    a = svc.register_identity("test-domain", "contract", "HT-001", "oa")
    with pytest.raises(ValueError):
        svc.merge(a, a, actor="rex")


def test_merge_twice_rejected(svc):
    a = svc.register_identity("test-domain", "contract", "HT-001", "oa")
    b = svc.register_identity("test-domain", "contract", "HT-002", "oa")
    svc.merge(a, b, actor="rex")
    with pytest.raises(ValueError):
        svc.merge(a, b, actor="rex")


# --- object_type 白名单 / CWA 边界 ---

def test_object_type_whitelist():
    whitelist = {"test-domain": {"contract"}}
    assert is_operational_object_type("test-domain", "contract", whitelist)
    assert not is_operational_object_type("test-domain", "document", whitelist)
    # domain 未声明 → 放行
    assert is_operational_object_type("other", "anything", whitelist)
    # 未配置白名单 → 不限制
    assert is_operational_object_type("test-domain", "chunk", None)


def test_register_non_whitelisted_type_rejected(kb):
    whitelist = {"test-domain": {"contract"}}
    svc = IdentityService(kb, object_type_whitelist=whitelist)
    with pytest.raises(ValueError):
        svc.register_identity("test-domain", "document", "DOC-1", "oa")
