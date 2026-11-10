"""
Unit tests for task_tracker.py v1.2 — SQLite 隔离存储：
frontmatter 解析（legacy 迁移）、归属强校验、失败计数、归档。
"""
import json
import sys
import pytest
from io import StringIO
from pathlib import Path

import task_tracker


def _make_args(**kwargs):
    defaults = {
        "command": None,
        "task_id": "test-001",
        "name": "Test Task",
        "description": "A test task",
        "session_key": "agent:main:dashboard:unit",
        "phase": "启动",
        "steps": '["step1","step2","step3"]',
        "step_index": None,
        "progress": None,
        "reason": "test failure",
        "result": "done",
        "json": False,
        "apply": False,
        "replace": False,
        "all": False,
    }
    defaults.update(kwargs)
    return type("Args", (), defaults)()


def _capture_stdout(func, *args):
    old = sys.stdout
    sys.stdout = buf = StringIO()
    try:
        func(*args)
    finally:
        sys.stdout = old
    return buf.getvalue()


def _db_task(task_id, session_key):
    conn = task_tracker._connect()
    try:
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return task_tracker._row_to_dict(row) if row else None
    finally:
        conn.close()


# ── frontmatter 解析（legacy 迁移用，函数保留）─────────────────────────────
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


# ── md 归档 ────────────────────────────────────────────────────────────────
class TestMdArchive:
    def test_archive_creates_file(self, clean_workspace):
        data = {
            "task_id": "arch-test", "name": "Archive Test", "description": "",
            "session_key": "s1", "phase": "完成", "step_index": 0,
            "total_steps": 3, "failure_count": 0, "status": "done",
            "result": "", "entries_json": "[]",
            "started_at": "2026-01-01T00:00:00", "last_updated": "2026-01-01T00:00:00",
        }
        path = task_tracker._write_md_archive(data, reason="completed", result="done")
        assert path.exists()
        content = path.read_text()
        assert "archive_reason: completed" in content
        assert "task_id: arch-test" in content


# ── start ──────────────────────────────────────────────────────────────────
class TestCmdStart:
    def test_start_creates_db_row(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        task = _db_task("test-001", "agent:main:dashboard:unit")
        assert task is not None
        assert task["name"] == "Test Task"
        assert task["total_steps"] == 3

    def test_start_missing_session_key_exits2(self, clean_workspace, capsys):
        args = _make_args(command="start", session_key="")
        with pytest.raises(SystemExit) as ei:
            task_tracker.cmd_start(args)
        assert ei.value.code == 2

    def test_start_second_active_rejected_exit3(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args2 = _make_args(command="start", task_id="other", name="Other")
        with pytest.raises(SystemExit) as ei:
            task_tracker.cmd_start(args2)
        assert ei.value.code == 3

    def test_start_replace_archives_old(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args2 = _make_args(command="start", task_id="other", name="Other", replace=True)
        _capture_stdout(task_tracker.cmd_start, args2)
        old = _db_task("test-001", "agent:main:dashboard:unit")
        assert old["status"] == "interrupted"
        archives = list(task_tracker.HISTORY_DIR.glob("*test-001*"))
        assert len(archives) == 1

    def test_start_same_id_idempotent(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        assert len(list(task_tracker.HISTORY_DIR.glob("*.md"))) == 0


# ── update / 归属校验 ─────────────────────────────────────────────────────
class TestCmdUpdate:
    def _started(self):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))

    def test_update_phase(self, clean_workspace):
        self._started()
        args = _make_args(command="update", phase="实现中", step_index=None, progress=None)
        _capture_stdout(task_tracker.cmd_update, args)
        assert _db_task("test-001", "x")["phase"] == "实现中"

    def test_update_step_index(self, clean_workspace):
        self._started()
        args = _make_args(command="update", phase=None, step_index=2, progress=None)
        _capture_stdout(task_tracker.cmd_update, args)
        assert _db_task("test-001", "x")["step_index"] == 2

    def test_update_progress_appends(self, clean_workspace):
        self._started()
        args = _make_args(command="update", phase=None, step_index=None, progress="完成 step1")
        _capture_stdout(task_tracker.cmd_update, args)
        task = _db_task("test-001", "x")
        assert len(task["progress_entries"]) == 2
        assert task["progress_entries"][-1]["text"] == "完成 step1"

    def test_update_cross_session_rejected(self, clean_workspace):
        self._started()
        args = _make_args(command="update", phase="HACK", session_key="agent:main:other")
        with pytest.raises(SystemExit) as ei:
            task_tracker.cmd_update(args)
        assert ei.value.code == 2
        assert _db_task("test-001", "x")["phase"] == "启动"

    def test_update_missing_scope_exits2(self, clean_workspace):
        self._started()
        args = _make_args(command="update", phase="X", session_key="")
        with pytest.raises(SystemExit) as ei:
            task_tracker.cmd_update(args)
        assert ei.value.code == 2


# ── increment-fail ────────────────────────────────────────────────────────
class TestCmdIncrementFail:
    def test_increment(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="increment-fail", reason="LLM timeout")
        _capture_stdout(task_tracker.cmd_increment_fail, args)
        task = _db_task("test-001", "x")
        assert task["failure_count"] == 1
        assert "LLM timeout" in task["progress_entries"][-1]["text"]

    def test_cross_session_rejected(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="increment-fail", session_key="agent:main:other")
        with pytest.raises(SystemExit) as ei:
            task_tracker.cmd_increment_fail(args)
        assert ei.value.code == 2


# ── complete ──────────────────────────────────────────────────────────────
class TestCmdComplete:
    def test_complete_archives_and_done(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="complete", result="all done")
        _capture_stdout(task_tracker.cmd_complete, args)
        task = _db_task("test-001", "x")
        assert task["status"] == "done"
        archives = list(task_tracker.HISTORY_DIR.glob("*test-001*"))
        assert len(archives) == 1
        assert "archive_reason: completed" in archives[0].read_text()

    def test_complete_cross_session_rejected(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="complete", session_key="agent:main:other")
        with pytest.raises(SystemExit) as ei:
            task_tracker.cmd_complete(args)
        assert ei.value.code == 2
        assert _db_task("test-001", "x")["status"] == "active"


# ── current / list ────────────────────────────────────────────────────────
class TestCmdCurrentList:
    def test_no_task_json(self, clean_workspace):
        args = _make_args(command="current", json=True)
        out = json.loads(_capture_stdout(task_tracker.cmd_current, args))
        assert out["active"] is False

    def test_with_task_json(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="current", json=True)
        out = json.loads(_capture_stdout(task_tracker.cmd_current, args))
        assert out["active"] is True
        assert out["task_id"] == "test-001"

    def test_multi_active_needs_scope(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        _capture_stdout(task_tracker.cmd_start, _make_args(
            command="start", task_id="t2", name="T2",
            session_key="agent:main:dashboard:other"))
        args = _make_args(command="current", json=True, session_key="")
        out = json.loads(_capture_stdout(task_tracker.cmd_current, args))
        assert out["active"] is False and out["scope_needed"] is True

    def test_list_json(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        args = _make_args(command="list", json=True)
        out = json.loads(_capture_stdout(task_tracker.cmd_list, args))
        assert out["count"] == 1


# ── 全生命周期 ────────────────────────────────────────────────────────────
class TestFullLifecycle:
    def test_start_update_complete(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        _capture_stdout(task_tracker.cmd_update, _make_args(
            command="update", phase="实现", step_index=1, progress="wrote code"))
        _capture_stdout(task_tracker.cmd_update, _make_args(
            command="update", phase="测试", step_index=2, progress="tests pass"))
        _capture_stdout(task_tracker.cmd_complete, _make_args(
            command="complete", result="all good"))
        assert _db_task("test-001", "x")["status"] == "done"
        assert len(list(task_tracker.HISTORY_DIR.glob("*test-001*"))) == 1

    def test_start_fail_recover_complete(self, clean_workspace):
        _capture_stdout(task_tracker.cmd_start, _make_args(command="start"))
        _capture_stdout(task_tracker.cmd_increment_fail, _make_args(
            command="increment-fail", reason="timeout"))
        _capture_stdout(task_tracker.cmd_increment_fail, _make_args(
            command="increment-fail", reason="timeout2"))
        task = _db_task("test-001", "x")
        assert task["failure_count"] == 2
        _capture_stdout(task_tracker.cmd_complete, _make_args(
            command="complete", result="recovered"))
        assert _db_task("test-001", "x")["status"] == "done"
