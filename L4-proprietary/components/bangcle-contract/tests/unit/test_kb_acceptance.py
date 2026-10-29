"""P8 §4：product-kb 满足度验收（连真实 DB，不用 mock）。

用 ProductKBDB 建确定性临时库，覆盖：
  KB-01 satisfied（命中在售 + 价≥红线）
  KB-03 unsatisfied（虚构产品，无候选）
  KB-04 红线（命中但报价低于折红线 → alert）
  KB-05 停售（SKU sale_status != 启用 → alert 含 SKU 状态）
  KB-06 db 不可达（run_kb_match referenced=False，不中断）

KB-02（近似名召回 score∈[0.5,0.85) → partial，软告警需人工确认）：
  product-kb fts_search_products 已改 prefix 召回同系列近似名，
  ContractMatcher 新增名称确认带 [0.5,0.85)：matched=True + 「名称近似，需人工确认」，
  L4 decide_satisfaction 据此判 partial；score≥0.85 才 satisfied。
"""
import os
import sys

import pytest

COMPONENT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCT_KB_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(COMPONENT_ROOT)), "product-kb")
for p in (COMPONENT_ROOT, PRODUCT_KB_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from product_kb.db import ProductKBDB
from product_kb.contract import ContractMatcher

from contract_review.kb_match import (
    ContractItem, match_items, decide_satisfaction, run_kb_match,
)


@pytest.fixture
def kb_db(tmp_path):
    db = ProductKBDB(str(tmp_path / "kb.db"))
    db.connect()
    db.init_db()
    line = db.get_or_create_product_line("测试线", "L1")
    cat = db.get_or_create_category(line, "安全类")
    # 在售：单价 1000，8 折红线
    pid = db.create_product(
        line, cat, "梆梆安全测评服务", None, "P001", None,
        "服务", "启用", None)
    db.create_or_update_sku(
        pid, "SKU001", "MODEL-A", 1000.0, "含税", "8折红线",
        "买断", "启用", None, None)
    # 停售
    pid2 = db.create_product(
        line, cat, "梆梆旧版加固", None, "P002", None,
        "软件", "停用", None)
    db.create_or_update_sku(
        pid2, "SKU002", "MODEL-OLD", 500.0, "含税", "9折",
        "买断", "停用", None, None)
    yield db
    db.close()


def _matcher(kb_db):
    return ContractMatcher(kb_db)


def _review(kb_db, name, price=None):
    return match_items(_matcher(kb_db), [ContractItem(name=name, price=price)])[0]


def test_kb01_satisfied(kb_db):
    r = _review(kb_db, "梆梆安全测评服务", price=1000.0)
    assert r.matched is True
    assert r.alert is None
    assert decide_satisfaction([r]) == "satisfied"


def test_kb03_fictional_unsatisfied(kb_db):
    r = _review(kb_db, "天马行空不存在的量子冰箱服务")
    assert r.matched is False
    assert r.product is None
    assert decide_satisfaction([r]) == "unsatisfied"


def test_kb04_below_redline(kb_db):
    r = _review(kb_db, "梆梆安全测评服务", price=500.0)
    assert r.matched is True
    assert r.alert and "红线" in r.alert
    assert decide_satisfaction([r]) == "unsatisfied"
    # 价格恰在红线之上 → 不告警
    r_ok = _review(kb_db, "梆梆安全测评服务", price=800.0)
    assert r_ok.alert is None


def test_kb05_stopped_sku(kb_db):
    r = _review(kb_db, "梆梆旧版加固", price=500.0)
    assert r.matched is True
    assert r.alert and ("停售" in r.alert or "SKU状态" in r.alert)
    assert decide_satisfaction([r]) == "unsatisfied"


def test_kb06_db_unreachable_no_crash(tmp_path):
    # 指向不存在的 db 路径 → referenced=False，satisfaction=unsatisfied，不抛异常
    review = run_kb_match(
        "梆梆安全测评服务",
        product_kb_root=PRODUCT_KB_ROOT,
        db_path=str(tmp_path / "missing.db"),
    )
    assert review.referenced is False
    assert review.satisfaction == "unsatisfied"


def test_kb02_approx_name_partial(kb_db):
    """KB-02：近似（前缀）名召回成功但相似度未达高置信 → partial，需人工确认。

    不直接认领 SKU / 不做价格红线判定；避免近似名被误当完全满足。
    """
    r = _review(kb_db, "梆梆安全测评")  # 部分前缀名
    assert r.matched is True
    assert 0.5 <= r.score < 0.85
    assert r.alert and "名称近似" in r.alert and "人工确认" in r.alert
    assert r.sku is None                       # 确认带不下发 SKU
    assert decide_satisfaction([r]) == "partial"


def test_kb02_longer_unknown_prefix_not_recalled(kb_db):
    """前缀型查询不会让'更长但不存在'的名字误召回真实短名产品。"""
    r = _review(kb_db, "梆梆安全测评服务量子冰箱增强包")
    # 文档名需以整个查询开头 → 无此产品 → unmatched
    assert r.matched is False
    assert decide_satisfaction([r]) == "unsatisfied"
