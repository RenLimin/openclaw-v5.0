"""
Shared fixtures for session-recovery tests.

We override WORKSPACE to a tmpdir so task_tracker.py writes don't pollute
the real workspace, and restore it after each test.
"""
import os
import sys
import json
import pytest
from pathlib import Path

# Make the scripts importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a fake workspace dir and patch WORKSPACE in task_tracker."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Patch the module-level WORKSPACE constant
    import task_tracker
    old_workspace = task_tracker.WORKSPACE
    old_current = task_tracker.CURRENT_TASK_FILE
    old_history = task_tracker.HISTORY_DIR

    task_tracker.WORKSPACE = tmp_path
    task_tracker.CURRENT_TASK_FILE = memory_dir / "current-task.md"
    task_tracker.HISTORY_DIR = memory_dir / "task-history"

    yield tmp_path

    # Restore
    task_tracker.WORKSPACE = old_workspace
    task_tracker.CURRENT_TASK_FILE = old_current
    task_tracker.HISTORY_DIR = old_history


@pytest.fixture
def clean_current_task(tmp_workspace):
    """Ensure no current-task.md exists at start, clean up at end."""
    ct = tmp_workspace / "memory" / "current-task.md"
    if ct.exists():
        ct.unlink()
    yield
    if ct.exists():
        ct.unlink()
    # Clean history
    hist = tmp_workspace / "memory" / "task-history"
    if hist.exists():
        for f in hist.iterdir():
            f.unlink()
