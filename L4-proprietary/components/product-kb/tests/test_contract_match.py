"""product-kb 合同标的匹配：prefix 召回 + 名称确认带（KB-02 支撑）。

中文在 FTS5 unicode61 下整串为单 token：
- fts_search_products 用 prefix 召回同系列近似名
- fts_search_chunks 仍用 phrase（语义搜索行为不变）
- ContractMatcher 确认带 [0.5,0.85) → matched + 软告警（上层 partial）
"""
import os
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from product_kb.db import ProductKBDB
from product_kb.contract import ContractMatcher


@pytest.fixture
def db():
    d = tempfile.mkdtemp()
    conn = ProductKBDB(os.path.join(d, "kb.db"))
    conn.connect()
    conn.init_db()
    line = conn.get_or_create_product_line("L", "L1")
    cat = conn.get_or_create_category(line, "安全")
    pid = conn.create_product(line, cat, "梆梆安全测评服务", None, "P1", None,
                              "服务", "启用", None)
    conn.create_or_update_sku(pid, "SKU1", "M-A", 1000.0, "含税", "8折红线",
                              "买断", "启用", None, None)
    yield conn
    conn.close()


def test_products_prefix_recalls_partial_name(db):
    ids = db.fts_search_products("梆梆安全测评")  # 部分前缀
    assert ids  # prefix 能召回


def test_products_exact_name_still_recalled(db):
    assert db.fts_search_products("梆梆安全测评服务")


def test_products_unrelated_name_not_recalled(db):
    assert db.fts_search_products("天马行空量子冰箱") == []


def test_chunks_still_phrase(db):
    """chunks 搜索不被改成 prefix（保持语义 phrase 行为）。"""
    clean = ProductKBDB._sanitize_fts_query("某段文本", prefix=False)
    assert clean == '"某段文本"'
    pref = ProductKBDB._sanitize_fts_query("某段文本", prefix=True)
    assert pref == '"某段文本"*'


def test_confirm_band_returns_soft_alert(db):
    m = ContractMatcher(db)
    r = m.match_item("梆梆安全测评")          # score≈0.81 ∈ [0.5,0.85)
    assert r["matched"] is True
    assert r["sku"] is None
    assert "人工确认" in r["alert"]


def test_high_confidence_skips_band(db):
    m = ContractMatcher(db)
    r = m.match_item("梆梆安全测评服务")      # score=0.9 ≥0.85
    assert r["matched"] is True
    assert r["alert"] is None
    assert r["sku"] is not None


def test_below_threshold_unmatched(db):
    m = ContractMatcher(db)
    # 构造一个能被 prefix 召回但相似度极低的输入：与真实名共享首字
    r = m.match_item("梆梆量子冰箱云宇宙大模型平台套件")
    # prefix 需真实名以整串查询开头 → 此查询更长，无召回
    assert r["matched"] is False
