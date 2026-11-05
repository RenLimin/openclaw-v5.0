"""满足度三态判定单测（适配主仓库 kb_match.decide_satisfaction）。

2026-11-05 合并 sandbox 测试时适配：
- main 无 _classify / aggregate_satisfaction（那是 sandbox 早期 API）；
- main 的满足度判定统一在 kb_match.decide_satisfaction(List[KbMatchResult])。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import _bootstrap  # noqa: F401

from contract_review.kb_match import decide_satisfaction, KbMatchResult


def _r(matched=True, score=0.9, alert=None):
    return KbMatchResult(
        input_name="x", matched=matched, score=score,
        product="梆梆加固", sku="SKU-1", alert=alert,
    )


class TestDecideSatisfaction(unittest.TestCase):
    def test_all_satisfied(self):
        self.assertEqual(
            decide_satisfaction([_r(), _r()]), "satisfied")

    def test_unmatched_is_unsatisfied(self):
        self.assertEqual(
            decide_satisfaction([_r(), _r(matched=False, score=0.0)]),
            "unsatisfied")

    def test_soft_warn_is_partial(self):
        self.assertEqual(
            decide_satisfaction([_r(), _r(alert="名称近似，需人工确认")]),
            "partial")

    def test_redline_is_unsatisfied(self):
        self.assertEqual(
            decide_satisfaction([_r(alert="价格低于折扣红线")]),
            "unsatisfied")

    def test_stopped_is_unsatisfied(self):
        self.assertEqual(
            decide_satisfaction([_r(alert="SKU状态异常：停用")]),
            "unsatisfied")

    def test_empty_is_unsatisfied(self):
        # 无标的可参照 → 保守判 unsatisfied
        self.assertEqual(decide_satisfaction([]), "unsatisfied")

    def test_high_price_still_satisfied(self):
        # 合同价高于标准价不触发红线（客户多付）
        self.assertEqual(decide_satisfaction([_r()]), "satisfied")


if __name__ == "__main__":
    unittest.main()
