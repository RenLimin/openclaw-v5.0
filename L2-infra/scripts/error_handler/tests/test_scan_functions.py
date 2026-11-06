#!/usr/bin/env python3
"""scan_llm_timeouts / scan_compaction_failures 纯函数测试（增量行驱动）。"""
import os
import sys
import unittest
import unittest.mock  # noqa: E402 (Python 3.14 需显式导入)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scan_errors import (  # noqa: E402
    scan_llm_timeouts,
    scan_compaction_failures,
    scan_zombie_processes,
    _resolve_file_ref,
)


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


class ScanFileRefTest(unittest.TestCase):
    """file 型 SecretRef 双层结构解析（2026-11-05 llama-cpp 误报根治）。

    回归基线：
      - 引用层 {source: file, provider: <alias>, id: <id>} 无 path 是**合法**形态
        （path 在定义层 secrets.providers.<alias>，OpenClaw schema 规定）；
      - 旧扫描器要求引用层自带 path → 对 llama-cpp 每 15 分钟误报一次
        api_key_format_error。
    """

    def test_ref_layer_without_path_resolves(self):
        """引用层（无 path）→ 经定义层解析出真实文件路径"""
        res = _resolve_file_ref(
            {"source": "file", "provider": "llamacpp", "id": "value"}
        )
        self.assertIn("path", res)
        self.assertTrue(os.path.exists(res["path"]))

    def test_definition_layer_with_path_ok(self):
        """定义层直带 path（兼容旧形态）"""
        res = _resolve_file_ref(
            {"source": "file",
             "path": "/Users/bangcle/.openclaw/secrets/llama.cpp.apiKey"}
        )
        self.assertEqual(
            res["path"],
            "/Users/bangcle/.openclaw/secrets/llama.cpp.apiKey",
        )

    def test_store_ref_not_flagged(self):
        """store 型 SecretRef 不应触发 file 解析"""
        self.assertEqual(
            _resolve_file_ref({"source": "store", "provider": "default",
                               "id": "SOME_KEY"}),
            {},
        )

    def test_ref_missing_provider_flagged(self):
        """file ref 缺 provider/id → 结构错误"""
        res = _resolve_file_ref({"source": "file", "id": "value"})
        self.assertIn("error", res)

    def test_unknown_alias_flagged(self):
        """引用层指向不存在的 secrets alias → 定义层缺失"""
        res = _resolve_file_ref(
            {"source": "file", "provider": "no_such_alias", "id": "value"}
        )
        self.assertIn("error", res)
        self.assertIn("no_such_alias", res["error"])


class ScanZombieProcessTest(unittest.TestCase):
    """scan_zombie_processes 身份记录（2026-11-06 改进）。

    回归基线：命中时必须记录 pid/ppid/stat/comm + 父进程命令行，
    否则只能看到数量，无法追查 zombie 来源（此前多次"抓到数量抓不到身份"）。
    """

    def _fake_run_cmd(self, parent_table):
        def fake(cmd, timeout=15):
            if "ps -eo pid,ppid,stat,comm" in cmd:
                return "1234 56 Z node\n5678 90 Z python3", 0
            if cmd.startswith("ps -p "):
                ppid = cmd.split()[2]
                return parent_table.get(ppid, ""), 0
            if "sandboxes" in cmd:
                return "0", 0
            return "", 0
        return fake

    def test_zombie_detail_contains_identity(self):
        with unittest.mock.patch(
            "scan_errors.run_cmd",
            side_effect=self._fake_run_cmd(
                {"56": "/usr/bin/node /opt/x.js", "90": "python3 worker.py"}
            ),
        ):
            errors = scan_zombie_processes()
        self.assertEqual(len(errors), 1)
        z = errors[0]
        self.assertEqual(z["type"], "zombie_processes")
        self.assertIn("pid=1234", z["detail"])
        self.assertIn("ppid=56", z["detail"])
        self.assertIn("comm=node", z["detail"])
        self.assertIn("/opt/x.js", z["detail"])  # 父进程命令行
        self.assertEqual(len(z["zombies"]), 2)
        self.assertEqual(z["zombies"][0]["pid"], "1234")
        self.assertEqual(z["zombies"][0]["parent_cmd"], "/usr/bin/node /opt/x.js")
        self.assertEqual(z["zombies"][1]["parent_cmd"], "python3 worker.py")

    def test_parent_gone_unknown(self):
        """父进程已退出（ppid=1）→ parent_cmd 标 unknown 不崩溃"""
        with unittest.mock.patch(
            "scan_errors.run_cmd",
            side_effect=self._fake_run_cmd({}),
        ):
            errors = scan_zombie_processes()
        self.assertEqual(len(errors), 1)
        z = errors[0]["zombies"][0]
        self.assertIn("unknown", z["parent_cmd"])

    def test_no_zombie_empty(self):
        with unittest.mock.patch("scan_errors.run_cmd", return_value=("", 0)):
            self.assertEqual(scan_zombie_processes(), [])


if __name__ == "__main__":
    unittest.main()
