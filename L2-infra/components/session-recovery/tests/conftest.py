"""
Shared fixtures for session-recovery tests (v1.2 SQLite).

We patch task_tracker module constants (WORKSPACE / CURRENT_TASK_FILE /
HISTORY_DIR / DB_FILE) to a tmpdir so tests don't pollute the real workspace.
"""
import sys
import pytest
from pathlib import Path

# Make the scripts importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def _restore(task_tracker, saved):
    (task_tracker.WORKSPACE, task_tracker.CURRENT_TASK_FILE,
     task_tracker.HISTORY_DIR, task_tracker.DB_FILE) = saved


@pytest.fixture
def tmp_workspace(tmp_path):
    """Isolate task_tracker state (SQLite + legacy md) into tmp dir."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    import task_tracker
    saved = (task_tracker.WORKSPACE, task_tracker.CURRENT_TASK_FILE,
             task_tracker.HISTORY_DIR, task_tracker.DB_FILE)
    task_tracker.WORKSPACE = tmp_path
    task_tracker.CURRENT_TASK_FILE = memory_dir / "current-task.md"
    task_tracker.HISTORY_DIR = memory_dir / "task-history"
    task_tracker.DB_FILE = memory_dir / "tasks.db"
    yield tmp_path
    _restore(task_tracker, saved)


@pytest.fixture
def clean_workspace(tmp_workspace):
    """Ensure no DB/legacy md/history exists at start, clean up at end."""
    tt = __import__("task_tracker")
    for path in (tt.DB_FILE, tt.CURRENT_TASK_FILE):
        if path.exists():
            path.unlink()
    if tt.HISTORY_DIR.exists():
        for f in tt.HISTORY_DIR.iterdir():
            f.unlink()
    yield tmp_workspace
    for path in (tt.DB_FILE, tt.CURRENT_TASK_FILE):
        if path.exists():
            path.unlink()
    if tt.HISTORY_DIR.exists():
        for f in tt.HISTORY_DIR.iterdir():
            f.unlink()
