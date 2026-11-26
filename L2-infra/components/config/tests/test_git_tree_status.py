#!/usr/bin/env python3
"""git_tree_status 回归测试。

核心保证：共享 index 被写花时，本模块仍返回真实改动（事故 2026-11-25：
health_check/system_full_audit/governor 因共享 index 污染同报「272 未提交」假警）。
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import git_tree_status as gts


def _run(args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "t@t"], repo)
    _run(["git", "config", "user.name", "t"], repo)
    (repo / "a.txt").write_text("a\n")
    (repo / "b.txt").write_text("b\n")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-q", "-m", "init"], repo)
    return repo


# ── 基本计数 ─────────────────────────────────────────────────────

def test_clean_tree_is_zero(tmp_path):
    repo = _make_repo(tmp_path)
    c = gts.working_tree_counts(repo)
    assert c["total"] == 0, c


def test_modified_and_untracked_counted(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "a.txt").write_text("changed\n")
    (repo / "new.txt").write_text("n\n")
    c = gts.working_tree_counts(repo)
    assert c["modified"] == 1 and c["untracked"] == 1 and c["total"] == 2, c


# ── 共享 index 污染必须不影响结果（本模块存在的理由）───────────────

def test_shared_index_pollution_does_not_distort(tmp_path):
    """模拟并行会话：向共享 index 里 stage 一个已被提交、工作树完好的文件，
    使共享 index 落后于 HEAD。裸 `git status` 会误报，本模块不得受影响。"""
    repo = _make_repo(tmp_path)
    shared = repo / ".git" / "index"

    # 让共享 index 过期：构造一个「删掉某条目」的旧 index（等价于并行会话隔离提交后的状态）
    stale = tmp_path / "stale.index"
    subprocess.run(["git", "read-tree", "HEAD~0"], cwd=repo,
                   env=dict(os.environ, GIT_INDEX_FILE=str(stale)), check=True)
    # 用 plumbing 造一个缺少 b.txt 条目的 index，再放回共享路径
    subprocess.run(["git", "update-index", "--force-remove", "b.txt"], cwd=repo,
                   env=dict(os.environ, GIT_INDEX_FILE=str(stale)), check=True)
    import shutil
    shutil.copy(stale, shared)

    # 此时裸 git status 会把已提交的 b.txt 误判为删除
    raw = _run(["git", "status", "--porcelain"], repo).stdout
    polluted = "b.txt" in raw and "D" in raw

    c = gts.working_tree_counts(repo)
    assert c["total"] == 0, f"污染下误报: {c}"
    assert c["samples"] == [], c
    # 前提自检：确认真发生了污染（否则这条用例证明不了什么）
    assert polluted, f"未能复现共享 index 污染，raw={raw!r}"


def test_temp_index_never_touches_shared(tmp_path):
    repo = _make_repo(tmp_path)
    before = (repo / ".git" / "index").stat().st_mtime_ns
    gts.working_tree_counts(repo)
    after = (repo / ".git" / "index").stat().st_mtime_ns
    assert before == after, "共享 .git/index 被改写"


def test_no_temp_file_left_behind(tmp_path):
    repo = _make_repo(tmp_path)
    gts.working_tree_counts(repo)
    leftovers = [p for p in Path("/tmp").glob("treestat.*")]
    assert leftovers == [], leftovers


# ── 展示层 ───────────────────────────────────────────────────────

def test_format_summary_reports_error_truthfully(tmp_path):
    msg = gts.format_summary({"error": "boom"})
    assert "不可用" in msg and "boom" in msg, msg


def test_format_summary_counts(tmp_path):
    msg = gts.format_summary({"untracked": 1, "modified": 2, "staged": 3})
    assert "1" in msg and "2" in msg and "3" in msg, msg
