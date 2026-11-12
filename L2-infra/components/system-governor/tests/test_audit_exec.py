"""system-governor v1.1 — audit_exec L1 执行器测试。

黄金基准见 DESIGN-DETAIL-system-governor-v1.1.md §5。
在 tmp_path 内建独立 git 仓库验证 git mv；不碰真实工作区。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import audit_exec  # noqa: E402
from src.models import AuditItem  # noqa: E402


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
    return tmp_path


def _mkitem(tier: str, paths: list[str] | None = None) -> AuditItem:
    return AuditItem(
        id="P6-test", category="重复", evidence="e", suggestion="s",
        tier=tier, status="pending",
        detail={"probe": "P6", "paths": paths} if paths else {"probe": "P6"},
    )


def test_l1_apply_executes_git_mv(tmp_path):
    root = _git_repo(tmp_path)
    src = tmp_path / "L2-infra" / "components" / "a" / "dup.txt"
    src.parent.mkdir(parents=True)
    src.write_text("x" * 2048)
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(root), check=True)

    item = _mkitem("L1", paths=["L2-infra/components/b/keep.txt", "L2-infra/components/a/dup.txt"])
    dest = tmp_path / "L2-infra" / "components" / "b" / "keep.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text("x" * 2048)  # canonical 存在
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add canonical"], cwd=str(root), check=True)

    items, actions = audit_exec.run([item], apply=True, root=root)
    assert items[0].status == "done"
    assert len(actions) == 1 and actions[0]["result"] == "done"
    assert not src.exists()  # 原文件已移走
    assert (dest.parent / "a__dup.txt").exists()  # 归位后文件名


def test_l2_apply_never_executes(tmp_path):
    root = _git_repo(tmp_path)
    item = _mkitem("L2")
    items, actions = audit_exec.run([item], apply=True, root=root)
    assert items[0].status == "needs-human"
    assert actions == []


def test_no_apply_zero_write(tmp_path):
    root = _git_repo(tmp_path)
    src = tmp_path / "L2-infra" / "components" / "a" / "dup.txt"
    src.parent.mkdir(parents=True)
    src.write_text("x" * 2048)
    item = _mkitem("L1", paths=["L2-infra/components/b/keep.txt", "L2-infra/components/a/dup.txt"])

    items, actions = audit_exec.run([item], apply=False, root=root)
    assert items[0].status == "pending"
    assert actions == []
    assert src.exists()  # 零写


def test_dest_exists_refuses_override(tmp_path):
    root = _git_repo(tmp_path)
    src = tmp_path / "L2-infra" / "components" / "a" / "dup.txt"
    src.parent.mkdir(parents=True)
    src.write_text("x" * 2048)
    dest = tmp_path / "L2-infra" / "components" / "b" / "keep.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text("y" * 2048)

    # 两个文件都在 paths 中但同内容 → 归位目标是 keep.txt 同目录 a__dup.txt，仍冲突需手动
    item = _mkitem("L1", paths=["L2-infra/components/b/keep.txt", "L2-infra/components/a/dup.txt"])
    dest_dup = dest.parent / "a__dup.txt"
    dest_dup.write_text("z" * 2048)  # 目标已存在
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "setup"], cwd=str(root), check=True)

    items, actions = audit_exec.run([item], apply=True, root=root)
    assert items[0].status == "needs-human"  # 拒绝覆盖 → 转人工
    assert actions[0]["result"] == "failed"
    assert src.exists()  # 原文件保留
