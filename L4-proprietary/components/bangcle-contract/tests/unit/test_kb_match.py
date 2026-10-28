"""KB 满足度测试 — VERIFICATION §4 KB-01~06（连真实 product_kb.db）。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from contract_review import kb_match
from contract_review.kb_match import (
    ContractItem, KbMatchResult, decide_satisfaction,
    run_kb_match, load_matcher, items_from_text,
)

PRODUCT_KB_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "product-kb", "data", "product_kb.db",
)

pytestmark = pytest.mark.skipif(
    not os.path.isfile(PRODUCT_KB_DB),
    reason="product_kb.db 缺失，无法联真实库",
)


@pytest.fixture(scope="module")
def matcher():
    return load_matcher()


def test_kb_01_real_matcher_returns_list(matcher):
    r = kb_match.match_items(matcher, [ContractItem(name="鸿蒙NEXT安全键盘")])
    assert isinstance(r, list)


def test_kb_02_low_score_partial():
    results = [KbMatchResult(input_name="近似名", matched=True, score=0.52,
                             alert="低匹配度，需人工确认")]
    assert decide_satisfaction(results) == "partial"


def test_kb_03_fake_product():
    results = [KbMatchResult(input_name="不存在产品XYZ", matched=False)]
    assert decide_satisfaction(results) == "unsatisfied"


def test_kb_04_below_redline():
    results = [KbMatchResult(input_name="x", matched=True,
                             alert="价格低于折扣红线（红线: 100.00, 输入: 50.00）")]
    assert decide_satisfaction(results) == "unsatisfied"


def test_kb_05_discontinued():
    results = [KbMatchResult(input_name="x", matched=True, alert="SKU状态: 停售")]
    assert decide_satisfaction(results) == "unsatisfied"


def test_kb_06_db_unreachable(monkeypatch):
    def boom(*a, **k):
        raise kb_match.KbMatchError("db 缺失")
    monkeypatch.setattr(kb_match, "load_matcher", boom)
    review = run_kb_match("无标的文本")
    assert review.referenced is False
    assert review.satisfaction == "unsatisfied"


def test_items_from_text():
    text = "1. 安全测评服务\n2. 合规评估服务\n"
    items = items_from_text(text)
    assert len(items) >= 2


def test_no_items_unsatisfied():
    assert decide_satisfaction([]) == "unsatisfied"


def test_all_clean_satisfied():
    results = [KbMatchResult(input_name="a", matched=True, alert=None),
               KbMatchResult(input_name="b", matched=True, alert=None)]
    assert decide_satisfaction(results) == "satisfied"
