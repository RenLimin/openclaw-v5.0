#!/usr/bin/env python3
"""scan_llm_timeouts / scan_compaction_failures 纯函数测试（增量行驱动）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scan_errors import scan_llm_timeouts, scan_compaction_failures  # noqa: E402


class ScanLlmTimeoutsTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(scan_llm_timeouts([]), [])

    def test_detects_lane_task_error(self):
        line = ('2026-11-03T23:10:26.328+08:00 [diagnostic] lane task error: '
                'lane=main durationMs=376920 error="LLM request timed out." '
                'errorName=FailoverError sessionKey=agent:main:dashboard:x')
        out = scan_llm_timeouts([line])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["type"], "llm_timeout")
        self.assertIn("LLM request timed out", out[0]["detail"])

    def test_detects_failed_before_reply(self):
        line = ("2026-11-03T23:10:26.352+08:00 Embedded agent failed before "
                "reply: LLM request timed out.")
        out = scan_llm_timeouts([line])
        self.assertEqual(len(out), 1)

    def test_minute_bucket_dedup(self):
        # 同一分钟内的多行（embedded end / lane error / failed before reply）
        lines = [
            '2026-11-03T23:10:26.328+08:00 [diagnostic] lane task error: '
            'error="LLM request timed out." x=1',
            "2026-11-03T23:10:26.352+08:00 Embedded agent failed before reply: "
            "LLM request timed out.",
        ]
        out = scan_llm_timeouts(lines)
        self.assertEqual(len(out), 1, "同一分钟多行必须合并为一个事件")

    def test_different_minutes_counted_separately(self):
        lines = [
            '2026-11-03T23:10:26.000+08:00 [diagnostic] lane task error: '
            'error="LLM request timed out."',
            '2026-11-03T23:47:55.000+08:00 [diagnostic] lane task error: '
            'error="LLM request timed out."',
        ]
        out = scan_llm_timeouts(lines)
        self.assertEqual(len(out), 2)

    def test_compaction_lines_excluded(self):
        line = ('2026-11-03T23:10:26.000+08:00 [diagnostic] lane task error: '
                'error="LLM request timed out." note=compaction')
        self.assertEqual(scan_llm_timeouts([line]), [])

    def test_unrelated_lines_ignored(self):
        self.assertEqual(scan_llm_timeouts(["2026-11-03T23:10:26 some info"]), [])


class ScanCompactionFailuresTest(unittest.TestCase):
    DIAG = (
        "2026-11-03T15:21:00.000+08:00 [compaction-diag] end "
        "diagId=D1 sessionKey=agent:main:dashboard:x outcome=failed "
        "reason=timeout durationMs=300000 provider=ark"
    )

    def test_empty(self):
        self.assertEqual(scan_compaction_failures([]), [])

    def test_timeout_classified(self):
        out = scan_compaction_failures([self.DIAG])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["type"], "compaction_timeout")
        self.assertEqual(out[0]["session_key"], "agent:main:dashboard:x")
        self.assertEqual(out[0]["duration_ms"], 300000)

    def test_non_timeout_reason_is_compaction_failed(self):
        line = self.DIAG.replace("reason=timeout", "reason=rate_limit")
        out = scan_compaction_failures([line])
        self.assertEqual(out[0]["type"], "compaction_failed")

    def test_diag_id_dedup(self):
        out = scan_compaction_failures([self.DIAG, self.DIAG])
        self.assertEqual(len(out), 1)

    def test_success_outcome_ignored(self):
        line = self.DIAG.replace("outcome=failed", "outcome=ok")
        self.assertEqual(scan_compaction_failures([line]), [])


if __name__ == "__main__":
    unittest.main()
