#!/usr/bin/env python3
"""run_scan_item / run_scan_items 分项超时与异常隔离测试（P1-d）。"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scan_errors import (  # noqa: E402
    run_scan_item, run_scan_items,
    SCAN_ITEM_TIMEOUT, SCAN_ITEM_ERROR,
)


class RunScanItemTest(unittest.TestCase):
    def test_normal_result(self):
        errs, item_errs = run_scan_item("ok", lambda: [{"type": "x"}], budget=5)
        self.assertEqual(errs, [{"type": "x"}])
        self.assertEqual(item_errs, [])

    def test_empty_result(self):
        errs, item_errs = run_scan_item("empty", lambda: [], budget=5)
        self.assertEqual(errs, [])
        self.assertEqual(item_errs, [])

    def test_timeout_flagged_not_raised(self):
        t0 = time.monotonic()
        errs, item_errs = run_scan_item("slow", lambda: time.sleep(30), budget=1)
        elapsed = time.monotonic() - t0
        self.assertEqual(errs, [])
        self.assertEqual(len(item_errs), 1)
        self.assertEqual(item_errs[0]["type"], SCAN_ITEM_TIMEOUT)
        self.assertEqual(item_errs[0]["name"], "slow")
        # 预算必须真正生效，而不是等满 30s
        self.assertLess(elapsed, 5, f"超时未在预算附近返回，耗时 {elapsed:.1f}s")

    def test_exception_isolated(self):
        def boom():
            raise ValueError("kaboom")
        errs, item_errs = run_scan_item("boom", boom, budget=5)
        self.assertEqual(errs, [])
        self.assertEqual(len(item_errs), 1)
        self.assertEqual(item_errs[0]["type"], SCAN_ITEM_ERROR)
        self.assertIn("ValueError", item_errs[0]["detail"])
        self.assertIn("kaboom", item_errs[0]["detail"])


class RunScanItemsTest(unittest.TestCase):
    def test_mixed_outcomes_order_independent_merge(self):
        items = [
            ("good", lambda: [{"type": "g1"}]),
            ("slow", lambda: time.sleep(30)),
            ("boom", lambda: (_ for _ in ()).throw(RuntimeError("x"))),
        ]
        t0 = time.monotonic()
        errs, item_errs = run_scan_items(items, budget=1, max_workers=3)
        elapsed = time.monotonic() - t0
        # 好的项结果保留
        self.assertIn({"type": "g1"}, errs)
        kinds = sorted(e["type"] for e in item_errs)
        self.assertEqual(kinds, [SCAN_ITEM_ERROR, SCAN_ITEM_TIMEOUT])
        # 并发：整批应≈预算，而非串行 30s
        self.assertLess(elapsed, 5, f"并发预算未生效，耗时 {elapsed:.1f}s")

    def test_all_normal(self):
        items = [("a", lambda: [{"type": "a"}]), ("b", lambda: [{"type": "b"}])]
        errs, item_errs = run_scan_items(items, budget=5, max_workers=2)
        self.assertEqual(sorted(e["type"] for e in errs), ["a", "b"])
        self.assertEqual(item_errs, [])


if __name__ == "__main__":
    unittest.main()
