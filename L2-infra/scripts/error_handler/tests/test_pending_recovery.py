#!/usr/bin/env python3
"""resolve_pending_restart 编排测试（P1-a）：stub guard/restart/health。"""
import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAFETY = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "..", "components", "gateway-safety"))
sys.path.insert(0, SAFETY)
import scan_errors as se  # noqa: E402
import recovery_pending as rp  # noqa: E402


class PendingRecoveryOrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pfile = os.path.join(self.tmp.name, "pending.json")
        self._orig = rp.PENDING_FILE
        rp.PENDING_FILE = self.pfile
        # scan_errors 通过模块函数名访问，patch 到 se 命名空间
        self.restarted = []
        se.guarded_restart = lambda reason: self.restarted.append(reason) or self._restart_rc
        self._restart_rc = 0
        self._guard_rc = 0
        se.guard_rc = lambda: self._guard_rc
        self._healthy = False
        se.gateway_process_healthy = lambda: self._healthy
        # 让 _load_recovery_pending 返回被改了 PENDING_FILE 的同一模块
        se._load_recovery_pending = lambda: rp

    def tearDown(self):
        rp.PENDING_FILE = self._orig
        for attr in ("guarded_restart", "guard_rc", "gateway_process_healthy",
                     "_load_recovery_pending"):
            delattr(se, attr)
        self.tmp.cleanup()

    def _upsert(self):
        rp.upsert("llm_timeout_unhealthy", "ev", path=self.pfile)

    def _actions(self, fixes):
        return [f["action"] for f in fixes]

    def test_no_pending_is_noop(self):
        fixes = []
        se.resolve_pending_restart(fixes)
        self.assertEqual(fixes, [])
        self.assertEqual(self.restarted, [])

    def test_guard_clear_fault_persists_compensates_once(self):
        self._upsert()
        self._guard_rc = 0
        self._healthy = False   # 故障仍在
        self._restart_rc = 0
        fixes = []
        se.resolve_pending_restart(fixes)
        self.assertIn("pending_recovery_restart", self._actions(fixes))
        self.assertEqual(len(self.restarted), 1)
        # 成功后 pending 被清除
        self.assertIsNone(rp.load(self.pfile))

    def test_guard_clear_but_healthy_cancels_without_restart(self):
        self._upsert()
        self._guard_rc = 0
        self._healthy = True    # 已自愈
        fixes = []
        se.resolve_pending_restart(fixes)
        self.assertIn("pending_recovery_canceled", self._actions(fixes))
        self.assertEqual(self.restarted, [])
        self.assertIsNone(rp.load(self.pfile))

    def test_guard_still_blocked_keeps_pending_silent(self):
        self._upsert()
        self._guard_rc = 1
        fixes = []
        se.resolve_pending_restart(fixes)
        self.assertEqual(fixes, [], "仍阻断时应静默保留，不制造 fix")
        self.assertEqual(self.restarted, [])
        self.assertIsNotNone(rp.load(self.pfile), "pending 仍保留")

    def test_expired_goes_manual_review(self):
        from datetime import datetime, timedelta
        rp.upsert("r", "e", path=self.pfile, ttl_min=1)
        rec = rp.load(self.pfile)
        rec["expires_at"] = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="seconds")
        rp.save(rec, self.pfile)
        fixes = []
        se.resolve_pending_restart(fixes)
        self.assertIn("pending_recovery_manual_review", self._actions(fixes))
        self.assertIsNone(rp.load(self.pfile))

    def test_unhealthy_branch_blocks_and_upserts(self):
        # auto_fix：进程不健康 + guard 阻断 rc=1 → 挂 pending，不重启成功
        se.gateway_process_healthy = lambda: False
        se.guarded_restart = lambda reason: 1  # guard hard block
        fixes = se.auto_fix([{"type": "llm_timeout", "detail": "ev-block"}])
        rf = [f for f in fixes if f["action"] == "gateway_restart_guarded"]
        self.assertEqual(len(rf), 1)
        self.assertIn("deferred as pending", rf[0]["result"])
        self.assertIsNotNone(rp.load(self.pfile), "rc=1 必须落 pending")


if __name__ == "__main__":
    unittest.main()
