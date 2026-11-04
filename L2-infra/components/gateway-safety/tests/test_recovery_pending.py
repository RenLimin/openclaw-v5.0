#!/usr/bin/env python3
"""recovery_pending 挂起补偿状态测试（临时状态文件，不触 ~/.openclaw）。"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import recovery_pending as rp  # noqa: E402


class RecoveryPendingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "pending.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_returns_none(self):
        self.assertIsNone(rp.load(self.path))

    def test_upsert_creates_and_dedups(self):
        rec, created = rp.upsert("llm_timeout", "ev line A", path=self.path)
        self.assertTrue(created)
        self.assertEqual(rec["compensations"], 0)
        self.assertEqual(rec["last_guard_rc"], 1)
        # 同证据再挂 → 不重复
        rec2, created2 = rp.upsert("llm_timeout", "ev line A", path=self.path)
        self.assertFalse(created2)
        self.assertEqual(rec2["evidence_hash"], rec["evidence_hash"])
        # 不同证据 → 新 hash
        rec3, created3 = rp.upsert("llm_timeout", "ev line B", path=self.path)
        self.assertTrue(created3)
        self.assertNotEqual(rec3["evidence_hash"], rec["evidence_hash"])

    def test_clear(self):
        rp.upsert("r", "e", path=self.path)
        rp.clear(self.path)
        self.assertIsNone(rp.load(self.path))
        rp.clear(self.path)  # 幂等

    def test_can_compensate_guard_gate(self):
        rec, _ = rp.upsert("r", "e", path=self.path)
        self.assertFalse(rp.can_compensate(rec, 1), "guard 仍阻断 → 不补")
        self.assertFalse(rp.can_compensate(rec, 2), "不确定 → 不补")
        self.assertTrue(rp.can_compensate(rec, 0), "guard 放行 → 可补")

    def test_compensate_only_once(self):
        rec, _ = rp.upsert("r", "e", path=self.path)
        self.assertTrue(rp.can_compensate(rec, 0))
        rp.mark_compensated(path=self.path)
        rec2 = rp.load(self.path)
        self.assertEqual(rec2["compensations"], 1)
        self.assertFalse(rp.can_compensate(rec2, 0), "补过 1 次后不再补")

    def test_ttl_expiry_blocks(self):
        rec, _ = rp.upsert("r", "e", path=self.path, ttl_min=30)
        future = datetime.now() + timedelta(minutes=31)
        self.assertFalse(rp.can_compensate(rec, 0, now=future), "超 TTL 不补")
        # 过期判定
        self.assertTrue(rp.is_expired(rec, now=future))

    def test_corrupt_file_returns_none(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertIsNone(rp.load(self.path))


if __name__ == "__main__":
    unittest.main()
