#!/usr/bin/env python3
"""工作树状态读取——隔离临时 index，免疫共享 `.git/index` 污染。

为什么需要它
------------
本仓 `.git/index` 是**跨会话共享**的：并行会话用 `GIT_INDEX_FILE=…` 提交后不回写
共享 index（AGENTS.md §共享 index 过期）。此时 `git status` 会把**已提交且工作树
完好**的文件显示为 staged `D`，满屏假删除；曾导致 health_check / system_full_audit /
governor 同时报「272 未提交文件」的假警。

做法
----
用 `GIT_INDEX_FILE=<临时>` + `git read-tree HEAD` 构造一份**只读快照 index**，
再对它跑 `git status --porcelain`。这份 index 只存在于临时文件，因此：
  - 结果与共享 index 的污染无关（真实反映 HEAD↔工作树）；
  - 绝不写入共享 `.git/index`（不干扰并行会话的在途暂存）。

用法
----
    from git_tree_status import working_tree_counts
    c = working_tree_counts(Path("/Users/bangcle/.openclaw/workspace"))
    # {"untracked": 3, "modified": 2, "staged": 0, "total": 5, "samples": [...]}
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(args: list[str], repo: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=str(repo), env=env,
        capture_output=True, text=True, timeout=60,
    )


def working_tree_counts(repo: Path = REPO_ROOT) -> dict:
    """返回相对 HEAD 的真实改动计数（不受共享 index 污染）。

    字段：untracked（未跟踪）、modified（已修改/删除）、staged（暂存）、total、samples。
    任何步骤失败时返回 {"error": ...}，调用方应据此降级而非编造数字。
    """
    tmpidx = tempfile.mktemp(prefix="treestat.", dir="/tmp")
    env = dict(os.environ, GIT_INDEX_FILE=tmpidx)
    try:
        r = _run(["git", "read-tree", "HEAD"], repo, env)
        if r.returncode != 0:
            return {"error": f"read-tree 失败: {r.stderr.strip()[:200]}"}

        r = _run(["git", "status", "--porcelain"], repo, env)
        if r.returncode != 0:
            return {"error": f"git status 失败: {r.stderr.strip()[:200]}"}
    finally:
        try:
            os.unlink(tmpidx)
        except OSError:
            pass

    untracked = modified = staged = 0
    samples: list[str] = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        xy = line[:2]
        if xy == "??":
            untracked += 1
        elif xy[0] != " " and xy[0] != "?":
            staged += 1
        else:
            modified += 1
        if len(samples) < 8:
            samples.append(line.rstrip())
    return {
        "untracked": untracked,
        "modified": modified,
        "staged": staged,
        "total": untracked + modified + staged,
        "samples": samples,
    }


def format_summary(c: dict) -> str:
    """给检测器用的单行摘要；含 error 时如实说明。"""
    if c.get("error"):
        return f"工作树状态不可用（{c['error']}）"
    return f"未跟踪 {c['untracked']} / 已改 {c['modified']} / 暂存 {c['staged']}"


if __name__ == "__main__":
    import json
    print(json.dumps(working_tree_counts(REPO_ROOT), indent=2, ensure_ascii=False))
