"""资产审计 — L1 执行器（v1.1，DETAIL §3.3）。

安全边界：
- 仅支持 git mv（保留历史、可 git revert）。
- L2/L3 即使 apply=True 也只记 needs-human，永不执行。
- 无 apply 时全部 pending（零写）。
- 执行前校验 src 存在、dest 不存在（防覆盖）。
- 每笔操作记 actions[]。
"""
from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

from .models import AuditItem


class AuditExecError(Exception):
    pass


def _git_mv(src: Path, dest: Path, root: Path) -> tuple[bool, str]:
    """git mv src dest；返回 (ok, message)。"""
    if not src.exists():
        return False, f"src 不存在: {src}"
    if dest.exists():
        return False, f"dest 已存在（拒绝覆盖）: {dest}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    rel_src = src.relative_to(root).as_posix()
    rel_dest = dest.relative_to(root).as_posix()
    proc = subprocess.run(
        ["git", "mv", rel_src, rel_dest],
        cwd=str(root), capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        return False, f"git mv 失败: {proc.stderr.strip()[:200]}"
    return True, f"git mv {rel_src} → {rel_dest}"


def _resolve_move_paths(detail: dict, root: Path) -> tuple[Path, Path] | None:
    """从 AuditItem.detail 推导 (src, dest)。

    P6 detail.paths = [canonical, dup1, dup2...]：首个视为规范位置，其余归位
    到其同目录（文件名加来源目录前缀，防碰撞）。
    无法安全推导时返回 None（needs-human）。
    """
    paths = detail.get("paths")
    if not paths or len(paths) < 2:
        return None
    canonical = root / paths[0]
    dup = root / paths[1]
    if not canonical.exists() or not dup.exists():
        return None
    # 归位到 canonical 同目录，文件名加 dup 父目录名前缀防碰撞
    dest = canonical.parent / f"{dup.parent.name}__{dup.name}"
    return dup, dest


def run(items: list[AuditItem], apply: bool, root: Path) -> tuple[list[AuditItem], list[dict]]:
    """执行处置。返回 (更新后的 items, actions 账本)。"""
    executed: list[AuditItem] = []
    actions: list[dict] = []

    for item in items:
        # L2+：即使 apply 也不执行
        if item.tier in ("L2", "L3"):
            executed.append(replace(item, status="needs-human"))
            continue

        # L1 但无 apply：dry-run，零写
        if not apply:
            executed.append(replace(item, status="pending"))
            continue

        # L1 + apply
        resolved = _resolve_move_paths(item.detail or {}, root)
        if resolved is None:
            executed.append(replace(item, status="needs-human"))
            actions.append({
                "id": item.id, "result": "skipped",
                "message": "无法安全推导归位路径，转人工",
            })
            continue

        src, dest = resolved
        ok, msg = _git_mv(src, dest, root)
        actions.append({"id": item.id, "result": "done" if ok else "failed", "message": msg})
        executed.append(replace(item, status="done" if ok else "needs-human"))

    return executed, actions
