#!/usr/bin/env python3
"""stall_detect 跨轮状态机测试（update_stall_state / stalled_sessions）。"""
import os
import sys
import unittest
from datetime import datetime

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import stall_detect as sd  # noqa: E402

KEY = "agent:main:dashboard:4bd7e100"


def timeout_line(ts):
    return (f"{ts} [diagnostic] lane task error: error=\"LLM request timed out.\" "
            f"errorName=FailoverError sessionKey={KEY} runId=r")


def success_line(ts):
    return (f"{ts} embedded run agent end: runId=r2 isError=false sessionKey={KEY}")


class StallStateMachineTest(unittest.TestCase):
    def test_timeout_recorded(self):
        st = sd.update_stall_state({}, [timeout_line("2026-11-03T23:47:55.000+08:00")])
        self.assertIn(KEY, st)
        self.assertEqual(st[KEY]["last_timeout_ts"], "2026-11-03T23:47:55")

    def test_success_clears_timeout(self):
        st = sd.update_stall_state({}, [
            timeout_line("2026-11-03T23:47:55.000+08:00"),
            success_line("2026-11-03T23:50:00.000+08:00"),
        ])
        self.assertNotIn(KEY, st, "成功 run 结束应清除未恢复超时")

    def test_cross_turn_persistence_then_stall(self):
        # 第 1 轮：超时发生，立即扫描（静默不足）
        st = sd.update_stall_state({}, [timeout_line("2026-11-03T23:47:55.000+08:00")])
        now1 = datetime.fromisoformat("2026-11-03T23:48:00")
        self.assertEqual(sd.stalled_sessions(st, now1, silent_min=10), [])
        # 第 2 轮无新日志（游标投递为空），但状态持久化 → 静默足够后判卡住
        st2 = sd.update_stall_state(st, [])
        now2 = datetime.fromisoformat("2026-11-04T00:05:00")
        stalled = sd.stalled_sessions(st2, now2, silent_min=10)
        self.assertEqual(len(stalled), 1)
        self.assertEqual(stalled[0][0], KEY)

    def test_new_timeout_overwrites(self):
        st = sd.update_stall_state({}, [timeout_line("2026-11-03T23:47:55.000+08:00")])
        st = sd.update_stall_state(st, [timeout_line("2026-11-04T00:05:00.000+08:00")])
        self.assertEqual(st[KEY]["last_timeout_ts"], "2026-11-04T00:05:00")

    def test_does_not_mutate_input(self):
        st0 = {}
        sd.update_stall_state(st0, [timeout_line("2026-11-03T23:47:55.000+08:00")])
        self.assertEqual(st0, {})


if __name__ == "__main__":
    unittest.main()
