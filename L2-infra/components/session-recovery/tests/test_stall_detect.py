#!/usr/bin/env python3
"""stall_detect.detect_stall 纯函数测试（P1-b）。"""
import os
import sys
import unittest
from datetime import datetime

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import stall_detect as sd  # noqa: E402

KEY = "agent:main:dashboard:4bd7e100"
TS = "2026-11-03T23:47:55.000+08:00"


def lane_error(ts=TS):
    return (f"{ts} [diagnostic] lane task error: durationMs=1608992 "
            f'error="LLM request timed out." errorName=FailoverError '
            f"sessionKey={KEY} runId=r1")


class DetectStallTest(unittest.TestCase):
    NOW = datetime.fromisoformat("2026-11-03T23:47:55")

    def test_empty_key_no_stall(self):
        self.assertEqual(sd.detect_stall("", ["x"], self.NOW), (False, None))

    def test_no_timeout_no_stall(self):
        lines = [f"{TS} some normal log sessionKey={KEY}"]
        self.assertEqual(sd.detect_stall(KEY, lines, self.NOW), (False, None))

    def test_timeout_silent_long_enough_is_stalled(self):
        # 超时发生在 23:47:55，now 为 24:00（静默 >10min）
        now = datetime.fromisoformat("2026-11-04T00:00:00")
        stalled, ev = sd.detect_stall(KEY, [lane_error()], now, silent_min=10)
        self.assertTrue(stalled)
        self.assertIn(KEY, ev)

    def test_timeout_silent_too_short_not_stalled(self):
        # 仅静默 3 分钟 → 可能正在重试，不判
        now = datetime.fromisoformat("2026-11-03T23:51:00")
        stalled, _ = sd.detect_stall(KEY, [lane_error()], now, silent_min=10)
        self.assertFalse(stalled)

    def test_recovered_after_timeout_not_stalled(self):
        now = datetime.fromisoformat("2026-11-04T00:00:00")
        rec_ts = "2026-11-03T23:50:00.000+08:00"
        lines = [
            lane_error(),
            (f"{rec_ts} embedded run agent end: runId=r2 isError=false "
             f"sessionKey={KEY} model=auto"),
        ]
        stalled, _ = sd.detect_stall(KEY, lines, now, silent_min=10)
        self.assertFalse(stalled, "超时后已成功恢复不应判卡住")

    def test_new_timeout_resets_recovery(self):
        now = datetime.fromisoformat("2026-11-04T00:20:00")
        lines = [
            lane_error("2026-11-03T23:47:55.000+08:00"),
            ("2026-11-03T23:50:00.000+08:00 embedded run agent end: runId=r2 "
             f"isError=false sessionKey={KEY}"),
            # 又一次更晚的超时，之后静默
            lane_error("2026-11-04T00:05:00.000+08:00"),
        ]
        stalled, ev = sd.detect_stall(KEY, lines, now, silent_min=10)
        self.assertTrue(stalled)
        self.assertIn("00:05:00", ev)

    def test_other_session_timeout_ignored(self):
        now = datetime.fromisoformat("2026-11-04T00:00:00")
        other = lane_error().replace(KEY, "agent:main:dashboard:OTHER")
        stalled, _ = sd.detect_stall(KEY, [other], now, silent_min=10)
        self.assertFalse(stalled)

    def test_timeout_without_timestamp_not_stalled(self):
        line = f'lane task error: error="LLM request timed out." sessionKey={KEY}'
        stalled, _ = sd.detect_stall(KEY, [line], self.NOW, silent_min=10)
        self.assertFalse(stalled, "无时间戳无法判定静默时长，保守不判")


if __name__ == "__main__":
    unittest.main()
