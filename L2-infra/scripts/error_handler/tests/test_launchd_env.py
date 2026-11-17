#!/usr/bin/env python3
"""launchd 环境回归测试：PATH/CWD 注入 + cron JSON 解析 + disabled 过滤。

背景（2026-11-17）：launchd 启动 ai.openclaw.error-scan 时
  PATH = /usr/gnu/bin:/usr/local/bin:/bin:/usr/bin   （无 /opt/homebrew/bin）
  CWD  = .../error_handler/                            （非 workspace 根）
于是 `openclaw` 找不到、`python3 L2-infra/...` 相对路径全部落空，
报告里出现 7 条纯环境性假异常（asset_missing / provider_error / context_scan_failed）。
本文件锁死修复后的行为，防止回退。
"""
import json
import os
import sys
import unittest
import unittest.mock  # noqa: F401  (Python 3.14 需显式导入)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scan_errors  # noqa: E402


class RunCmdEnvTest(unittest.TestCase):
    def test_injects_homebrew_path_and_workspace_cwd(self):
        captured = {}

        class FakeResult:
            stdout = "ok"
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return FakeResult()

        with unittest.mock.patch("scan_errors.subprocess.run", fake_run):
            out, rc = scan_errors.run_cmd("echo hi")

        self.assertEqual((out, rc), ("ok", 0))
        self.assertEqual(captured["kwargs"]["cwd"], scan_errors.WORKSPACE)
        self.assertIn("/opt/homebrew/bin", captured["kwargs"]["env"]["PATH"])

    def test_preserves_existing_path_entries(self):
        captured = {}

        class FakeResult:
            stdout = ""
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured["kwargs"] = kwargs
            return FakeResult()

        with unittest.mock.patch("scan_errors.subprocess.run", fake_run):
            with unittest.mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}):
                scan_errors.run_cmd("true")

        path = captured["kwargs"]["env"]["PATH"]
        self.assertIn("/usr/bin", path)
        self.assertIn("/bin", path)
        self.assertLess(path.index("/opt/homebrew/bin"), path.index("/usr/bin"),
                        "homebrew 路径应置于最前，避免被系统旧命令遮蔽")

    def test_timeout_returns_marker(self):
        def fake_run(cmd, **kwargs):
            raise scan_errors.subprocess.TimeoutExpired(cmd, 15)

        with unittest.mock.patch("scan_errors.subprocess.run", fake_run):
            out, rc = scan_errors.run_cmd("sleep 999")
        self.assertEqual(out, "TIMEOUT")
        self.assertEqual(rc, -1)


class ParseCronListTest(unittest.TestCase):
    def test_parses_cjk_name_and_disabled_flag(self):
        payload = {"jobs": [{
            "id": "512aa9eb-5ddd-462c-9553-0082276e5ab2",
            "name": "系统错误扫描（含上下文溢出自动恢复）",
            "enabled": False,
            "status": "disabled",
            "state": {"lastRunStatus": "error", "consecutiveErrors": 10,
                      "lastError": "command timed out"},
        }]}
        rows = scan_errors._parse_cron_list(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "512aa9eb-5ddd-462c-9553-0082276e5ab2")
        self.assertEqual(rows[0]["name"], "系统错误扫描（含上下文溢出自动恢复）")
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["consecutive_errors"], 10)
        self.assertEqual(rows[0]["last_error"], "command timed out")

    def test_invalid_json_returns_empty(self):
        self.assertEqual(scan_errors._parse_cron_list("not json"), [])


class ScanCronErrorsTest(unittest.TestCase):
    def _patch_list(self, payload):
        return unittest.mock.patch(
            "scan_errors.run_cmd",
            return_value=(json.dumps(payload, ensure_ascii=False), 0))

    def test_disabled_job_ignored(self):
        payload = {"jobs": [{
            "id": "512aa9eb-5ddd-462c-9553-0082276e5ab2",
            "name": "系统错误扫描（含上下文溢出自动恢复）",
            "enabled": False, "status": "disabled",
            "state": {"lastRunStatus": "error", "consecutiveErrors": 10,
                      "lastError": "command timed out"},
        }]}
        with self._patch_list(payload):
            self.assertEqual(scan_errors.scan_cron_errors(), [])

    def test_active_job_with_consecutive_errors_reported(self):
        payload = {"jobs": [{
            "id": "aaaaaaaa-1111-2222-3333-444455556666",
            "name": "daily-x",
            "enabled": True, "status": "error",
            "state": {"lastRunStatus": "error", "consecutiveErrors": 3,
                      "lastError": "boom"},
        }]}
        with self._patch_list(payload):
            errs = scan_errors.scan_cron_errors()
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["type"], "cron_error")
        self.assertEqual(errs[0]["consecutive_failures"], 3)
        self.assertIn("boom", errs[0]["detail"])

    def test_single_failure_is_warning(self):
        payload = {"jobs": [{
            "id": "bbbbbbbb-1111-2222-3333-444455556666",
            "name": "daily-y",
            "enabled": True, "status": "ok",
            "state": {"lastRunStatus": "error", "consecutiveErrors": 1,
                      "lastError": "transient"},
        }]}
        with self._patch_list(payload):
            errs = scan_errors.scan_cron_errors()
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["type"], "cron_warning")


class AssetConsistencyTest(unittest.TestCase):
    def test_independent_of_cwd(self):
        """相对资产路径必须以 WORKSPACE 为基准，而非调用者 CWD。"""
        orig = os.getcwd()
        os.chdir("/tmp")
        try:
            errs = scan_errors.scan_asset_consistency()
        finally:
            os.chdir(orig)
        self.assertNotIn("asset_missing", [e["type"] for e in errs])


if __name__ == "__main__":
    unittest.main()
