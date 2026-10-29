"""P8 §4：product-kb 满足度验收（连真实 DB，不用 mock）。

用 ProductKBDB 建确定性临时库，覆盖：
  KB-01 satisfied（命中在售 + 价≥红线）
  KB-03 unsatisfied（虚构产品，无候选）
  KB-04 红线（命中但报价低于折红线 → alert）
  KB-05 停售（SKU sale_status != 启用 → alert 含 SKU 状态）
  KB-06 db 不可达（run_kb_match referenced=False，不中断）

KB-02（FTS 近似候选 score≈0.5 → partial）：
  当前 product-kb 的 fts_search_products 把输入整体包成 phrase，
  unicode61 对中文按整串一个 token，只有整名命中才有候选，
  故"低相似度候选"路径在不改共享搜索行为的前提下不可达。
  见 test_kb02_structural_note 留证。
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


def test_kb02_structural_note(kb_db):
    """留证：phrase-FTS 下'近似候选 score≈0.5'不产生（KB-02 partial 不可达）。

    共享 product-kb 搜索改为 OR-token 才能产出低相似候选；属跨组件行为变更，
    需 Rex 拍板。本测试锁定当前事实，避免后续误以为 partial 已生效。
    """
    r = _review(kb_db, "梆梆安全测评")  # 部分名
    # phrase 匹配无候选 → 直接 unmatched（而非 partial）
    assert r.matched is False
    assert decide_satisfaction([r]) == "unsatisfied"
