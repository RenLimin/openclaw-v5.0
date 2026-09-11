"""
Unit tests for check_and_retry.py — failure detection logic,
retry thresholds, and dry-run behavior.

We mock _run() and get_current_task() to avoid depending on
openclaw CLI or real workspace state.
"""
import json
import time
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import check_and_retry


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

class TestConstants:
    def test_max_retries(self):
        """MAX_RETRIES should be 2 per AGENTS.md spec."""
        assert check_and_retry.MAX_RETRIES == 2

    def test_min_retry_interval(self):
        """MIN_RETRY_INTERVAL_MIN should be 5."""
        assert check_and_retry.MIN_RETRY_INTERVAL_MIN == 5


# ──────────────────────────────────────────────
# get_current_task
# ──────────────────────────────────────────────

class TestGetCurrentTask:
    def test_no_task(self):
        """When _run returns failure, get_current_task returns None."""
        with patch.object(check_and_retry, "_run", return_value=("", 1)):
            assert check_and_retry.get_current_task() is None

    def test_inactive_task(self):
        """When JSON says active=False, returns None."""
        with patch.object(check_and_retry, "_run", return_value=('{"active": false}', 0)):
            assert check_and_retry.get_current_task() is None

    def test_active_task(self):
        """Returns parsed dict when active."""
        data = {"active": True, "task_id": "t1", "failure_count": 0}
        with patch.object(check_and_retry, "_run", return_value=(json.dumps(data), 0)):
            result = check_and_retry.get_current_task()
            assert result is not None
            assert result["task_id"] == "t1"

    def test_invalid_json(self):
        """Invalid JSON → returns None."""
        with patch.object(check_and_retry, "_run", return_value=("not json", 0)):
            assert check_and_retry.get_current_task() is None

    def test_empty_output(self):
        """Empty output → returns None."""
        with patch.object(check_and_retry, "_run", return_value=("", 0)):
            assert check_and_retry.get_current_task() is None


# ──────────────────────────────────────────────
# check_session_failed
# ──────────────────────────────────────────────

class TestCheckSessionFailed:
    def test_no_output(self):
        """No CLI output → not failed."""
        with patch.object(check_and_retry, "_run", return_value=("", 1)):
            is_failed, error, ts = check_and_retry.check_session_failed("agent:main:main")
            assert is_failed is False
            assert error is None

    def test_session_list_with_failed_status(self):
        """sessions --json shows status=failed → is_failed=True."""
        data = {
            "sessions": [
                {"key": "agent:main:main", "status": "failed", "updatedAt": 1700000000000}
            ]
        }
        with patch.object(check_and_retry, "_run", side_effect=[
            ("", 1),  # sessions history fails
            (json.dumps(data), 0),  # sessions list succeeds
        ]):
            is_failed, error, ts = check_and_retry.check_session_failed("agent:main:main")
            assert is_failed is True

    def test_session_list_with_ok_status(self):
        """sessions --json shows status=ok → not failed."""
        data = {
            "sessions": [
                {"key": "agent:main:main", "status": "ok", "updatedAt": 1700000000000}
            ]
        }
        with patch.object(check_and_retry, "_run", side_effect=[
            ("", 1),
            (json.dumps(data), 0),
        ]):
            is_failed, error, ts = check_and_retry.check_session_failed("agent:main:main")
            assert is_failed is False

    def test_session_history_with_error_message(self):
        """History contains 'The agent run failed' → is_failed=True."""
        recent_ts = int(time.time() * 1000)  # current time in ms
        data = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "The agent run failed with error"}],
                    "timestamp": recent_ts,
                }
            ]
        }
        with patch.object(check_and_retry, "_run", return_value=(json.dumps(data), 0)):
            is_failed, error, ts = check_and_retry.check_session_failed("agent:main:main")
            assert is_failed is True
            assert "agent run failed" in error

    def test_session_history_stop_reason_error(self):
        """History has stopReason=error → is_failed=True."""
        recent_ts = int(time.time() * 1000)
        data = {
            "messages": [
                {
                    "role": "assistant",
                    "stopReason": "error",
                    "timestamp": recent_ts,
                }
            ]
        }
        with patch.object(check_and_retry, "_run", return_value=(json.dumps(data), 0)):
            is_failed, error, ts = check_and_retry.check_session_failed("agent:main:main")
            assert is_failed is True

    def test_session_not_found(self):
        """Session key not in list → not failed."""
        data = {
            "sessions": [
                {"key": "other:session", "status": "ok"}
            ]
        }
        with patch.object(check_and_retry, "_run", side_effect=[
            ("", 1),
            (json.dumps(data), 0),
        ]):
            is_failed, error, ts = check_and_retry.check_session_failed("agent:main:main")
            assert is_failed is False


# ──────────────────────────────────────────────
# find_failed_sessions
# ──────────────────────────────────────────────

class TestFindFailedSessions:
    def test_no_failures(self):
        data = {"sessions": [{"key": "s1", "status": "ok"}]}
        with patch.object(check_and_retry, "_run", return_value=(json.dumps(data), 0)):
            result = check_and_retry.find_failed_sessions()
            assert result == []

    def test_one_failure(self):
        data = {
            "sessions": [
                {"key": "s1", "status": "ok"},
                {"key": "s2", "status": "failed", "displayName": "Subagent", "updatedAt": 1700000000000},
            ]
        }
        with patch.object(check_and_retry, "_run", return_value=(json.dumps(data), 0)):
            result = check_and_retry.find_failed_sessions()
            assert len(result) == 1
            assert result[0]["key"] == "s2"
            assert result[0]["status"] == "failed"

    def test_multiple_failures(self):
        data = {
            "sessions": [
                {"key": "s1", "status": "failed", "updatedAt": 1700000000000},
                {"key": "s2", "status": "error", "updatedAt": 1700000001000},
                {"key": "s3", "status": "ok"},
            ]
        }
        with patch.object(check_and_retry, "_run", return_value=(json.dumps(data), 0)):
            result = check_and_retry.find_failed_sessions()
            assert len(result) == 2

    def test_cli_failure(self):
        with patch.object(check_and_retry, "_run", return_value=("", 1)):
            result = check_and_retry.find_failed_sessions()
            assert result == []


# ──────────────────────────────────────────────
# check_and_retry — main logic
# ──────────────────────────────────────────────

class TestCheckAndRetry:
    def test_no_task_returns_true(self):
        """No current task → returns True (nothing to do)."""
        with patch.object(check_and_retry, "get_current_task", return_value=None):
            result = check_and_retry.check_and_retry(apply=False)
            assert result is True

    def test_failure_count_at_max_stops(self):
        """failure_count >= MAX_RETRIES → returns False, no retry."""
        task = {"active": True, "task_id": "t1", "failure_count": 2, "name": "Test"}
        with patch.object(check_and_retry, "get_current_task", return_value=task):
            result = check_and_retry.check_and_retry(apply=True)
            assert result is False

    def test_failure_count_exceeds_max(self):
        """failure_count > MAX_RETRIES → returns False."""
        task = {"active": True, "task_id": "t1", "failure_count": 5, "name": "Test"}
        with patch.object(check_and_retry, "get_current_task", return_value=task):
            result = check_and_retry.check_and_retry(apply=True)
            assert result is False

    def test_session_ok_returns_true(self):
        """Session not failed → returns True."""
        task = {"active": True, "task_id": "t1", "failure_count": 0, "name": "Test"}
        with patch.object(check_and_retry, "get_current_task", return_value=task), \
             patch.object(check_and_retry, "check_session_failed", return_value=(False, None, None)):
            result = check_and_retry.check_and_retry(apply=True)
            assert result is True

    def test_session_failed_dry_run(self):
        """Session failed + dry-run → returns True without incrementing."""
        task = {
            "active": True, "task_id": "t1", "failure_count": 0, "name": "Test",
            "phase": "实现", "step_index": 1, "total_steps": 3,
            "progress_entries_recent": [],
        }
        with patch.object(check_and_retry, "get_current_task", return_value=task), \
             patch.object(check_and_retry, "check_session_failed", return_value=(True, "error", 0)), \
             patch.object(check_and_retry, "increment_fail") as mock_inc, \
             patch.object(check_and_retry, "wake_session") as mock_wake:
            result = check_and_retry.check_and_retry(apply=False)
            assert result is True
            mock_inc.assert_not_called()
            mock_wake.assert_not_called()

    def test_session_failed_apply(self):
        """Session failed + apply → increments fail + wakes session."""
        task = {
            "active": True, "task_id": "t1", "failure_count": 0, "name": "Test",
            "phase": "实现", "step_index": 1, "total_steps": 3,
            "progress_entries_recent": [{"text": "step1 done"}],
        }
        with patch.object(check_and_retry, "get_current_task", return_value=task), \
             patch.object(check_and_retry, "check_session_failed", return_value=(True, "timeout", 0)):
            with patch.object(check_and_retry, "increment_fail") as mock_inc:
                with patch.object(check_and_retry, "wake_session", return_value=True) as mock_wake:
                    result = check_and_retry.check_and_retry(apply=True)
                    assert result is True
                    mock_inc.assert_called_once()
                    mock_wake.assert_called_once()

    def test_retry_count_boundary_1(self):
        """failure_count=1 (below MAX_RETRIES=2) → should retry."""
        task = {
            "active": True, "task_id": "t1", "failure_count": 1, "name": "Test",
            "phase": "实现", "step_index": 0, "total_steps": 3,
            "progress_entries_recent": [],
        }
        with patch.object(check_and_retry, "get_current_task", return_value=task), \
             patch.object(check_and_retry, "check_session_failed", return_value=(True, "err", 0)), \
             patch.object(check_and_retry, "increment_fail"), \
             patch.object(check_and_retry, "wake_session", return_value=True):
            result = check_and_retry.check_and_retry(apply=True)
            assert result is True

    def test_retry_count_boundary_2(self):
        """failure_count=2 (== MAX_RETRIES) → should NOT retry."""
        task = {"active": True, "task_id": "t1", "failure_count": 2, "name": "Test"}
        with patch.object(check_and_retry, "get_current_task", return_value=task):
            result = check_and_retry.check_and_retry(apply=True)
            assert result is False

    def test_min_retry_interval_not_elapsed(self):
        """Failure too recent → skip retry."""
        task = {
            "active": True, "task_id": "t1", "failure_count": 0, "name": "Test",
            "phase": "实现", "step_index": 0, "total_steps": 3,
            "progress_entries_recent": [],
        }
        # last_run is 1 minute ago, MIN_RETRY_INTERVAL_MIN=5
        recent_ts = time.time() - 60
        with patch.object(check_and_retry, "get_current_task", return_value=task), \
             patch.object(check_and_retry, "check_session_failed", return_value=(True, "err", recent_ts)):
            result = check_and_retry.check_and_retry(apply=True)
            assert result is True  # skipped due to interval

    def test_min_retry_interval_elapsed(self):
        """Failure old enough → proceed with retry."""
        task = {
            "active": True, "task_id": "t1", "failure_count": 0, "name": "Test",
            "phase": "实现", "step_index": 0, "total_steps": 3,
            "progress_entries_recent": [],
        }
        old_ts = time.time() - 600  # 10 minutes ago
        with patch.object(check_and_retry, "get_current_task", return_value=task), \
             patch.object(check_and_retry, "check_session_failed", return_value=(True, "err", old_ts)), \
             patch.object(check_and_retry, "increment_fail"), \
             patch.object(check_and_retry, "wake_session", return_value=True):
            result = check_and_retry.check_and_retry(apply=True)
            assert result is True


# ──────────────────────────────────────────────
# wake_session
# ──────────────────────────────────────────────

class TestWakeSession:
    def test_wake_success(self):
        task_info = {
            "name": "Test Task",
            "task_id": "t1",
            "phase": "实现",
            "step_index": 1,
            "total_steps": 3,
            "progress_entries_recent": [{"text": "step0 done"}],
        }
        with patch.object(check_and_retry, "_run", return_value=("", 0)) as mock_run:
            result = check_and_retry.wake_session("agent:main:main", task_info, 1, "timeout")
            assert result is True
            mock_run.assert_called_once()

    def test_wake_failure(self):
        task_info = {
            "name": "Test Task",
            "task_id": "t1",
            "phase": "实现",
            "step_index": 1,
            "total_steps": 3,
            "progress_entries_recent": [],
        }
        with patch.object(check_and_retry, "_run", return_value=("error", 1)):
            result = check_and_retry.wake_session("agent:main:main", task_info, 1, "timeout")
            assert result is False

    def test_wake_message_content(self):
        """Verify the wake message contains task info."""
        task_info = {
            "name": "My Task",
            "task_id": "task-123",
            "phase": "测试",
            "step_index": 2,
            "total_steps": 5,
            "progress_entries_recent": [{"text": "已完成步骤1"}],
        }
        with patch.object(check_and_retry, "_run", return_value=("", 0)) as mock_run:
            check_and_retry.wake_session("agent:main:main", task_info, 2, "LLM timeout")
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            # The message is json.dumps'd (producing \\uXXXX escapes) and shell-quoted
            import shlex
            parts = shlex.split(cmd)
            msg_arg = parts[parts.index("--message") + 1]
            msg = msg_arg.encode().decode("unicode_escape")
            assert "My Task" in msg
            assert "task-123" in msg
            assert "LLM timeout" in msg
            assert "第 2 次" in msg


# ──────────────────────────────────────────────
# _log
# ──────────────────────────────────────────────

class TestLog:
    def test_log_writes_file(self, tmp_path):
        """_log should append to LOG_FILE."""
        import check_and_retry
        old_log = check_and_retry.LOG_FILE
        log_file = tmp_path / "test.log"
        check_and_retry.LOG_FILE = log_file
        try:
            check_and_retry._log("test message")
            check_and_retry._log("second message")
            assert log_file.exists()
            content = log_file.read_text()
            assert "test message" in content
            assert "second message" in content
        finally:
            check_and_retry.LOG_FILE = old_log


# ──────────────────────────────────────────────
# _run
# ──────────────────────────────────────────────

class TestRun:
    def test_success(self):
        out, rc = check_and_retry._run("echo hello")
        assert out == "hello"
        assert rc == 0

    def test_failure(self):
        out, rc = check_and_retry._run("false")
        assert rc != 0

    def test_timeout(self):
        out, rc = check_and_retry._run("sleep 10", timeout=1)
        assert out == "TIMEOUT"
        assert rc == -1
