"""safe_commit 删除语义回归测试。

背景（事故 2026-11-26）：原实现第 0 步要求每个路径在磁盘上必须存在，
导致「合法删除文件」无法通过统一安全提交器提交；而 `git add` 对已删路径
实测 rc=0、正确产出 staged D。修复后：工作树存在 **或** 在 HEAD 中已跟踪即可。

本测试用临时 git 仓库隔离验证，不碰主仓共享 index。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]  # tests→config→components→L2-infra→workspace
SAFE_COMMIT = Path(__file__).resolve().parents[1] / "safe_commit.py"  # components/config/


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SAFE_COMMIT), *args],
                          cwd=cwd, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """建一个最小 git 仓库：两个文件 + 一次提交。"""
    r = tmp_path / "r"
    r.mkdir()
    g = ["git", "-C", str(r)]
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(g + ["config", "user.email", "t@example.com"], check=True)
    subprocess.run(g + ["config", "user.name", "t"], check=True)
    (r / "keep.txt").write_text("keep\n")
    (r / "gone.txt").write_text("bye\n")
    subprocess.run(g + ["add", "--", "."], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "init"], check=True)
    return r


def test_deleted_tracked_path_is_accepted(repo: Path) -> None:
    """删除已跟踪文件：应被接受并产出 staged D，而非报「路径不存在」。"""
    (repo / "gone.txt").unlink()
    r = _run(["--repo", str(repo), "--paths", "gone.txt",
              "--dry-run", "--skip-preflight", "--message", "x"], repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "❌" not in r.stdout, r.stdout
    assert "将提交 1 项" in r.stdout


def test_nonexistent_untracked_path_still_rejected(repo: Path) -> None:
    """既不在工作树、也不在 HEAD 的路径仍须拒绝（不能因放宽而漏检）。"""
    r = _run(["--repo", str(repo), "--paths", "nope.txt", "--preflight-only"], repo)
    assert r.returncode == 2
    assert "路径不存在" in r.stdout


def test_new_and_modified_paths_still_work(repo: Path) -> None:
    """新增/修改路径行为不变。"""
    (repo / "new.txt").write_text("new\n")
    (repo / "keep.txt").write_text("changed\n")
    r = _run(["--repo", str(repo), "--paths", "new.txt", "keep.txt",
              "--dry-run", "--skip-preflight", "--message", "x"], repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "将提交 2 项" in r.stdout
