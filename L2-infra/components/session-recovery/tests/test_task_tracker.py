"""
Unit tests for task_tracker.py — CRUD operations, frontmatter parsing,
failure counting, and archive logic.
"""
import json
import sys
import pytest
from io import StringIO
from pathlib import Path

import task_tracker


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_args(**kwargs):
    """Build a minimal argparse.Namespace with defaults, overridden by kwargs."""
    defaults = {
        "command": None,
        "task_id": "test-001",
        "name": "Test Task",
        "description": "A test task",
        "phase": "启动",
        "steps": '["step1","step2","step3"]',
        "step_index": None,
        "progress": None,
        "reason": "test failure",
        "result": "done",
        "json": False,
        "apply": False,
    }
    defaults.update(kwargs)
    return type("Args", (), defaults)()


def _capture_stdout(func, *args):
    """Run func(*args) and capture only its stdout output."""
    old = sys.stdout
    sys.stdout = buf = StringIO()
    try:
        func(*args)
    finally:
        sys.stdout = old
    return buf.getvalue()


# ──────────────────────────────────────────────
# Frontmatter parsing
# ──────────────────────────────────────────────

class TestParseFrontmatter:
    def test_empty_content(self):
        data, body = task_tracker._parse_frontmatter("")
        assert data == {}
        assert body == ""

    def test_no_frontmatter(self):
        data, body = task_tracker._parse_frontmatter("Just some text\nno frontmatter")
        assert data == {}
        assert body == "Just some text\nno frontmatter"

    def test_basic_frontmatter(self):
        content = '---\ntask_id: "abc"\nname: "My Task"\n---\nBody text'
        data, body = task_tracker._parse_frontmatter(content)
        assert data["task_id"] == "abc"
        assert data["name"] == "My Task"
        assert body == "Body text"

    def test_integer_fields_parsed(self):
        content = '---\nfailure_count: 3\nstep_index: 2\ntotal_steps: 5\n---\n'
        data, body = task_tracker._parse_frontmatter(content)
        assert data["failure_count"] == 3
        assert data["step_index"] == 2
        assert data["total_steps"] == 5

    def test_quotes_stripped(self):
        content = '---\ntask_id: "hello-world"\n---\n'
        data, _ = task_tracker._parse_frontmatter(content)
        assert data["task_id"] == "hello-world"

    def test_unquoted_value(self):
        content = '---\nphase: 启动\n---\n'
        data, _ = task_tracker._parse_frontmatter(content)
        assert data["phase"] == "启动"


# ──────────────────────────────────────────────
# _format_frontmatter / _format_body
# ──────────────────────────────────────────────

class TestFormatFrontmatter:
    def test_ordering_and_skip_none(self):
        data = {"task_id": "x", "name": "Y", "phase": None, "failure_count": 0}
        fm = task_tracker._format_frontmatter(data)
        lines = fm.strip().split("\n")
        assert lines[0] == "---"
        assert lines[-1] == "---"
        assert "task_id: x" in lines
        assert "name: Y" in lines
        # None values should be skipped
        assert "phase" not in fm

    def test_all_fields(self):
        data = {
            "task_id": "t1", "name": "N", "phase": "P",
            "step_index": 1, "total_steps": 5, "failure_count": 0,
            "started_at": "2026-01-01T00:00:00", "last_updated": "2026-01-01T00:01:00",
        }
        fm = task_tracker._format_frontmatter(data)
        assert "task_id: t1" in fm
        assert "failure_count: 0" in fm


class TestFormatBody:
    def test_description_only(self):
        data = {"description": "hello"}
        body = task_tracker._format_body(data)
        assert "hello" in body

    def test_with_progress_entries(self):
        data = {
            "description": "desc",
            "progress_entries": [
                {"time": "2026-01-01T00:00:00", "text": "started"},
                {"time": "2026-01-01T00:01:00", "text": "step1 done"},
            ],
        }
        body = task_tracker._format_body(data)
        assert "### 进度记录" in body
        assert "[2026-01-01T00:00:00] started" in body
        assert "[2026-01-01T00:01:00] step1 done" in body

    def test_no_entries(self):
        data = {"description": "desc", "progress_entries": []}
        body = task_tracker._format_body(data)
        assert "### 进度记录" not in body


# ──────────────────────────────────────────────
# _read_current / _write_current
# ──────────────────────────────────────────────

class TestReadWriteCurrent:
    def test_read_nonexistent(self, clean_current_task):
        result = task_tracker._read_current()
        assert result is None

    def test_write_and_read(self, clean_current_task):
        data = {
            "task_id": "test-001",
            "name": "Test",
            "description": "desc",
            "phase": "启动",
            "step_index": 0,
            "total_steps": 3,
            "failure_count": 0,
            "started_at": "2026-01-01T00:00:00",
            "last_updated": "2026-01-01T00:00:00",
            "progress_entries": [{"time": "2026-01-01T00:00:00", "text": "init"}],
        }
        task_tracker._write_current(data)
        result = task_tracker._read_current()
        assert result is not None
        assert result["task_id"] == "test-001"
        assert result["name"] == "Test"
        assert result["failure_count"] == 0
        assert len(result["progress_entries"]) == 1

    def test_read_invalid_no_task_id(self, clean_current_task):
        """File exists but has no task_id in frontmatter → returns None."""
        ct = task_tracker.CURRENT_TASK_FILE
        ct.write_text("---\nname: no-id\n---\n")
        result = task_tracker._read_current()
        assert result is None


# ──────────────────────────────────────────────
# cmd_start
# ──────────────────────────────────────────────

class TestCmdStart:
    def test_start_creates_file(self, clean_current_task):
        args = _make_args(command="start")
        _capture_stdout(task_tracker.cmd_start, args)
        assert task_tracker.CURRENT_TASK_FILE.exists()

    def test_start_output(self, clean_current_task, capsys):
        args = _make_args(command="start")
        task_tracker.cmd_start(args)
        captured = capsys.readouterr()
        assert "test-001" in captured.out
        assert "Test Task" in captured.out

    def test_start_archives_previous(self, clean_current_task):
        """Starting a new task should archive the existing one."""
        args1 = _make_args(command="start", task_id="old-task", name="Old")
        _capture_stdout(task_tracker.cmd_start, args1)

        args2 = _make_args(command="start")
        _capture_stdout(task_tracker.cmd_start, args2)

        hist = task_tracker.HISTORY_DIR
        archives = list(hist.glob("*old-task*"))
        assert len(archives) == 1

    def test_start_same_id_no_archive(self, clean_current_task):
        """Starting with same task_id should not archive."""
        args = _make_args(command="start")
        _capture_stdout(task_tracker.cmd_start, args)
        _capture_stdout(task_tracker.cmd_start, args)
        hist = task_tracker.HISTORY_DIR
        archives = list(hist.glob("*.md"))
        assert len(archives) == 0

    def test_start_parses_steps(self, clean_current_task):
        args = _make_args(command="start", steps='["a","b","c"]')
        _capture_stdout(task_tracker.cmd_start, args)
        result = task_tracker._read_current()
        assert result["total_steps"] == 3

    def test_start_empty_steps(self, clean_current_task):
        args = _make_args(command="start", steps="[]")
        _capture_stdout(task_tracker.cmd_start, args)
        result = task_tracker._read_current()
        assert result["total_steps"] == 0


# ──────────────────────────────────────────────
# cmd_update
# ──────────────────────────────────────────────

class TestCmdUpdate:
    def test_update_phase(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="update", phase="实现中", step_index=None, progress=None)
        _capture_stdout(task_tracker.cmd_update, args)
        result = task_tracker._read_current()
        assert result["phase"] == "实现中"

    def test_update_step_index(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="update", phase=None, step_index=2, progress=None)
        _capture_stdout(task_tracker.cmd_update, args)
        result = task_tracker._read_current()
        assert result["step_index"] == 2

    def test_update_progress_appends_entry(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="update", phase=None, step_index=None, progress="完成 step1")
        _capture_stdout(task_tracker.cmd_update, args)
        result = task_tracker._read_current()
        assert len(result["progress_entries"]) == 2
        assert result["progress_entries"][-1]["text"] == "完成 step1"

    def test_update_no_current_task(self, clean_current_task):
        args = _make_args(command="update", phase="X")
        with pytest.raises(SystemExit):
            task_tracker.cmd_update(args)

    def test_update_multiple_fields(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="update", phase="测试", step_index=1, progress="progress text")
        _capture_stdout(task_tracker.cmd_update, args)
        result = task_tracker._read_current()
        assert result["phase"] == "测试"
        assert result["step_index"] == 1
        assert result["progress_entries"][-1]["text"] == "progress text"


# ──────────────────────────────────────────────
# cmd_increment_fail
# ──────────────────────────────────────────────

class TestCmdIncrementFail:
    def test_increment_once(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="increment-fail", reason="timeout")
        _capture_stdout(task_tracker.cmd_increment_fail, args)
        result = task_tracker._read_current()
        assert result["failure_count"] == 1

    def test_increment_multiple(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="increment-fail", reason="err")
        for _ in range(5):
            _capture_stdout(task_tracker.cmd_increment_fail, args)
        result = task_tracker._read_current()
        assert result["failure_count"] == 5

    def test_reason_recorded_in_progress(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="increment-fail", reason="LLM timeout")
        _capture_stdout(task_tracker.cmd_increment_fail, args)
        result = task_tracker._read_current()
        last_entry = result["progress_entries"][-1]
        assert "LLM timeout" in last_entry["text"]
        assert "失败 #1" in last_entry["text"]

    def test_increment_no_task(self, clean_current_task):
        args = _make_args(command="increment-fail", reason="x")
        with pytest.raises(SystemExit):
            task_tracker.cmd_increment_fail(args)

    def test_default_reason(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="increment-fail", reason="未知原因")
        _capture_stdout(task_tracker.cmd_increment_fail, args)
        result = task_tracker._read_current()
        assert result["failure_count"] == 1


# ──────────────────────────────────────────────
# cmd_complete
# ──────────────────────────────────────────────

class TestCmdComplete:
    def test_complete_archives_and_removes(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="complete", result="all done")
        _capture_stdout(task_tracker.cmd_complete, args)
        assert not task_tracker.CURRENT_TASK_FILE.exists()
        hist = task_tracker.HISTORY_DIR
        archives = list(hist.glob("*test-001*"))
        assert len(archives) == 1

    def test_complete_no_task(self, clean_current_task, capsys):
        args = _make_args(command="complete", result="x")
        task_tracker.cmd_complete(args)
        captured = capsys.readouterr()
        assert "没有" in captured.out

    def test_complete_archive_content(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="complete", result="success")
        _capture_stdout(task_tracker.cmd_complete, args)
        hist = task_tracker.HISTORY_DIR
        archive_file = list(hist.glob("*test-001*"))[0]
        content = archive_file.read_text()
        assert "success" in content
        assert "archive_reason: completed" in content

    def test_complete_sets_phase(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="complete", result="done")
        _capture_stdout(task_tracker.cmd_complete, args)
        hist = task_tracker.HISTORY_DIR
        archive_file = list(hist.glob("*test-001*"))[0]
        content = archive_file.read_text()
        assert "phase: 完成" in content


# ──────────────────────────────────────────────
# cmd_current
# ──────────────────────────────────────────────

class TestCmdCurrent:
    def test_no_task_text(self, clean_current_task, capsys):
        args = _make_args(command="current", json=False)
        task_tracker.cmd_current(args)
        captured = capsys.readouterr()
        assert "没有" in captured.out

    def test_no_task_json(self, clean_current_task):
        args = _make_args(command="current", json=True)
        output = _capture_stdout(task_tracker.cmd_current, args)
        data = json.loads(output)
        assert data["active"] is False

    def test_with_task_text(self, clean_current_task, capsys):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="current", json=False)
        task_tracker.cmd_current(args)
        captured = capsys.readouterr()
        assert "Test Task" in captured.out
        assert "test-001" in captured.out

    def test_with_task_json(self, clean_current_task):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="current", json=True)
        output = _capture_stdout(task_tracker.cmd_current, args)
        data = json.loads(output)
        assert data["active"] is True
        assert data["task_id"] == "test-001"
        assert "progress_entries_total" in data
        assert "progress_entries_recent" in data

    def test_json_recent_limit(self, clean_current_task):
        """progress_entries_recent should be capped at 5."""
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        for i in range(10):
            args = _make_args(command="update", phase=None, step_index=None, progress=f"step {i}")
            _capture_stdout(task_tracker.cmd_update, args)
        args = _make_args(command="current", json=True)
        output = _capture_stdout(task_tracker.cmd_current, args)
        data = json.loads(output)
        assert data["progress_entries_total"] == 11  # 1 from start + 10
        assert len(data["progress_entries_recent"]) == 5


# ──────────────────────────────────────────────
# _archive
# ──────────────────────────────────────────────

class TestArchive:
    def test_archive_creates_file(self, clean_current_task):
        data = {
            "task_id": "arch-test",
            "name": "Archive Test",
            "description": "",
            "phase": "完成",
            "step_index": 0,
            "total_steps": 3,
            "failure_count": 0,
            "started_at": "2026-01-01T00:00:00",
            "last_updated": "2026-01-01T00:00:00",
            "progress_entries": [],
        }
        task_tracker._archive(data, reason="completed", result="done")
        hist = task_tracker.HISTORY_DIR
        files = list(hist.glob("*arch-test*"))
        assert len(files) == 1

    def test_archive_preserves_data(self, clean_current_task):
        data = {
            "task_id": "arch-test",
            "name": "Archive Test",
            "description": "desc",
            "phase": "完成",
            "step_index": 2,
            "total_steps": 5,
            "failure_count": 1,
            "started_at": "2026-01-01T00:00:00",
            "last_updated": "2026-01-01T00:00:00",
            "progress_entries": [{"time": "t1", "text": "entry1"}],
        }
        task_tracker._archive(data, reason="test", result="result text")
        hist = task_tracker.HISTORY_DIR
        archive_file = list(hist.glob("*arch-test*"))[0]
        content = archive_file.read_text()
        assert "archive_reason: test" in content
        assert "result: result text" in content
        assert "step_index: 2" in content
        assert "failure_count: 1" in content


# ──────────────────────────────────────────────
# Integration: full lifecycle
# ──────────────────────────────────────────────

class TestFullLifecycle:
    def test_start_update_complete(self, clean_current_task):
        """Start → update → complete should work end-to-end."""
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        _capture_stdout(task_tracker.cmd_update, _make_args(command="update", phase="实现", step_index=1, progress="wrote code"))
        _capture_stdout(task_tracker.cmd_update, _make_args(command="update", phase="测试", step_index=2, progress="tests pass"))
        _capture_stdout(task_tracker.cmd_complete, _make_args(command="complete", result="all good"))

        assert not task_tracker.CURRENT_TASK_FILE.exists()
        hist = task_tracker.HISTORY_DIR
        archives = list(hist.glob("*test-001*"))
        assert len(archives) == 1

    def test_start_fail_recover_complete(self, clean_current_task):
        """Start → fail → recover → complete."""
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        _capture_stdout(task_tracker.cmd_increment_fail, _make_args(command="increment-fail", reason="timeout"))
        _capture_stdout(task_tracker.cmd_increment_fail, _make_args(command="increment-fail", reason="timeout2"))
        result = task_tracker._read_current()
        assert result["failure_count"] == 2
        _capture_stdout(task_tracker.cmd_complete, _make_args(command="complete", result="recovered"))
        assert not task_tracker.CURRENT_TASK_FILE.exists()

    def test_failure_count_threshold_values(self, clean_current_task):
        """Verify failure_count reaches exactly the threshold values used in AGENTS.md."""
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        for i in range(3):
            _capture_stdout(task_tracker.cmd_increment_fail, _make_args(command="increment-fail", reason=f"err{i}"))
        result = task_tracker._read_current()
        # AGENTS.md: failure_count >= 1 and < 2 → auto-recover
        # failure_count >= 2 → stop auto-retry
        assert result["failure_count"] == 3  # exceeds both thresholds
