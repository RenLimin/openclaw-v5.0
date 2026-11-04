#!/usr/bin/env python3
"""auto_fix 对 llm_timeout 的对症处置决策表测试（P1-c）。

进程不健康 → guarded 重启；
进程健康 + 端点连续全挂 → 仅建议 fallback（不重启）；
进程健康 + 瞬时 → 只观察（不重启）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scan_errors as se  # noqa: E402


class TimeoutRemedyTest(unittest.TestCase):
    def setUp(self):
        # 隔离外部副作用：不真重启、不真探活、不写 streak 文件
        self.restart_calls = []
        se.guarded_restart = lambda reason: self.restart_calls.append(reason) or 0
        self._streak = 0
        se._update_endpoint_fail_streak = lambda allu: self._streak

    def tearDown(self):
        # 还原，避免污染同进程其它测试
        del se.guarded_restart
        del se._update_endpoint_fail_streak

    def _actions(self, fixes):
        return [f["action"] for f in fixes]

    def def_streak(self, n):
        self._streak = n

    def def_probe(self, all_unreach):
        se.probe_model_endpoints = lambda timeout=8: (
            {"p": {"reachable": not all_unreach}}, all_unreach, all_unreach)

    def def_healthy(self, ok):
        se.gateway_process_healthy = lambda: ok

    def test_unhealthy_process_triggers_guarded_restart(self):
        self.def_healthy(False)
        fixes = se.auto_fix([{"type": "llm_timeout"}])
        self.assertIn("gateway_restart_guarded", self._actions(fixes))
        self.assertEqual(len(self.restart_calls), 1)

    def test_healthy_all_endpoints_down_persistent_no_restart(self):
        self.def_healthy(True)
        self.def_probe(all_unreach=True)
        self.def_streak(2)
        fixes = se.auto_fix([{"type": "llm_timeout"}])
        actions = self._actions(fixes)
        self.assertIn("model_fallback_suggested", actions)
        self.assertNotIn("gateway_restart_guarded", actions, "进程健康不得重启")
        self.assertEqual(self.restart_calls, [])
        fb = next(f for f in fixes if f["action"] == "model_fallback_suggested")
        self.assertTrue(fb["gateway_healthy"])
        self.assertTrue(fb["endpoints_all_unreachable"])

    def test_healthy_transient_single_round_observe_only(self):
        self.def_healthy(True)
        self.def_probe(all_unreach=True)
        self.def_streak(1)  # 未达连续 2 轮阈值
        fixes = se.auto_fix([{"type": "llm_timeout"}])
        actions = self._actions(fixes)
        self.assertIn("llm_timeout_observed_no_action", actions)
        self.assertNotIn("gateway_restart_guarded", actions)
        self.assertNotIn("model_fallback_suggested", actions)
        self.assertEqual(self.restart_calls, [])

    def test_healthy_some_endpoints_reachable_observe_only(self):
        self.def_healthy(True)
        self.def_probe(all_unreach=False)  # 至少一个端点活着
        self.def_streak(5)                  # 即使多轮，也不是"全挂"
        fixes = se.auto_fix([{"type": "llm_timeout"}])
        actions = self._actions(fixes)
        self.assertIn("llm_timeout_observed_no_action", actions)
        self.assertNotIn("gateway_restart_guarded", actions)
        self.assertEqual(self.restart_calls, [])


if __name__ == "__main__":
    unittest.main()
