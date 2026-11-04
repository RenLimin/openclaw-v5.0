#!/usr/bin/env python3
"""detect_stalled_sessions 端到端编排测试（P1-b）。

用临时日志文件 + 临时 cursor/state，绝不触碰真实 gateway.log 或
~/.openclaw/state。mock get_current_task / notify / wake_session，
确保不真发企微、不真唤醒会话。
"""
import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS)
import check_and_retry as car  # noqa: E402

KEY = "***"


def timeout_line(key, minutes_ago):
    ts = (datetime.now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    return (f'{ts}.000+08:00 [diagnostic] lane task error: error="LLM request timed out." '
            f"errorName=FailoverError sessionKey={key} runId=r1\n")


class StallIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = Path(self.tmp) / "gateway.log"
        self.log.write_text("2026-11-04T00:00:00.000+08:00 boot\n")
        self.cursor = Path(self.tmp) / "cursor.json"
        self.state = Path(self.tmp) / "stall-state.json"
        self._patches = [
            patch.object(car, "STALL_LOG", str(self.log)),
            patch.object(car, "STALL_CURSOR_FILE", self.cursor),
            patch.object(car, "STALL_STATE_FILE", self.state),
            patch.object(car, "_log"),  # 根治：detect_stalled_sessions 内部 _log 写真实日志
        ]
        for p in self._patches:
            p.start()
        # 首跑 baseline：跳日志末尾、不回放、state 为空、提前 return
        car.detect_stalled_sessions()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _append(self, line):
        with open(self.log, "a") as f:
            f.write(line)

    def _task(self, key=KEY):
        return {"active": True, "task_id": "t1", "name": "T",
                "session_key": key, "failure_count": 0}

    def test_bound_task_notified_but_not_woken_by_default(self):
        self._append(timeout_line(KEY, 20))
        with patch.object(car, "get_current_task", return_value=self._task()), \
             patch.object(car, "notify") as nt, \
             patch.object(car, "wake_session") as wk:
            car.detect_stalled_sessions(auto_wake=False)
            nt.assert_called_once()
            self.assertIn(KEY, nt.call_args[0][0])
            wk.assert_not_called()  # 默认只通知

    def test_auto_wake_invokes_wake_session(self):
        self._append(timeout_line(KEY, 20))
        with patch.object(car, "get_current_task", return_value=self._task()), \
             patch.object(car, "notify"), \
             patch.object(car, "wake_session", return_value=True) as wk:
            car.detect_stalled_sessions(auto_wake=True)
            wk.assert_called_once()
            self.assertEqual(wk.call_args[0][0], KEY)

    def test_unbound_stall_only_logged(self):
        self._append(timeout_line(KEY, 20))
        with patch.object(car, "get_current_task", return_value=None), \
             patch.object(car, "notify") as nt, \
             patch.object(car, "wake_session") as wk:
            car.detect_stalled_sessions(auto_wake=True)  # 即使开了 auto-wake
            nt.assert_not_called()
            wk.assert_not_called()  # 无任务绑定绝不代跑

    def test_recent_timeout_not_yet_stalled(self):
        self._append(timeout_line(KEY, 2))  # 静默仅 2min < 10min
        with patch.object(car, "get_current_task", return_value=self._task()), \
             patch.object(car, "notify") as nt:
            car.detect_stalled_sessions()
            nt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
