#!/usr/bin/env python3
"""archive — workspace 历史文件归档执行器。

契约见 DESIGN-DETAIL-system-governor-v1.0.md §3.3。
- 默认 dry-run，零移动；--apply 才真实移动。
- 保留相对路径到 <dest>/<subdir>/ 下，可回滚。
- manifest.json 登记每次移动（时间、源→目标、规则、大小、sha256）。
- 幂等：目标已存在且 sha256 相同 → 跳过；不同 → 加时间戳后缀。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_rules as R  # noqa: E402

MANIFEST_NAME = "manifest.json"


@dataclass
class Move:
    src: Path
    dst: Path
    rule_id: str
    reason: str
    size: int
    sha256: str
    skipped: bool = False        # 幂等：已存在相同内容
    skip_reason: str = ""


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path):
    """生成文件列表；遍历中剪枝排除目录（不进入 .git/node_modules/.archive 等）。"""
    prune = set(R.EXCLUDE_DIR_NAMES) | set(R.PROTECTED_TOP_DIRS)
    for dirpath, dirnames, filenames in os_walk_sorted(root):
        # 原地剪枝（os.walk 约定）
        dirnames[:] = [d for d in dirnames if d not in prune and not d.startswith(".trash")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.is_symlink():
                continue
            yield p


def os_walk_sorted(root: Path):
    import os
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        yield dirpath, dirnames, filenames


def plan(root: Path, dest: Path, now_epoch: float) -> list[Move]:
    """扫描并生成移动计划（不执行）。"""
    moves: list[Move] = []
    root = root.resolve()
    dest = dest.resolve()
    for f in iter_files(root):
        try:
            st = f.stat()
        except OSError:
            continue
        hit = R.classify(f, root, mtime_epoch=st.st_mtime,
                         size_bytes=st.st_size, now_epoch=now_epoch)
        if hit is None:
            continue
        rel = f.relative_to(root)
        target = dest / hit.archive_subdir / rel
        moves.append(Move(
            src=f, dst=target, rule_id=hit.rule_id, reason=hit.reason,
            size=st.st_size, sha256="",
        ))
    return moves


def _resolve_collision(move: Move) -> Move:
    """目标已存在：sha 相同 → skip；不同 → 时间戳后缀。"""
    if not move.dst.exists():
        return move
    try:
        existing_sha = sha256_file(move.dst)
    except OSError:
        existing_sha = ""
    if move.sha256 and existing_sha == move.sha256:
        move.skipped = True
        move.skip_reason = "identical file already archived"
        return move
    ts = datetime.now().strftime("%H%M%S")
    move.dst = move.dst.with_name(f"{move.dst.stem}.{ts}{move.dst.suffix}")
    return move


def execute(moves: list[Move], *, apply: bool, dest: Path) -> dict:
    """执行（apply=True）或仅汇总（dry-run）。返回结果汇总。"""
    done, skipped = [], []
    manifest_entries = []
    if apply:
        dest.mkdir(parents=True, exist_ok=True)

    for mv in moves:
        if apply:
            mv.sha256 = sha256_file(mv.src)
            mv = _resolve_collision(mv)
            if mv.skipped:
                skipped.append(mv)
                continue
            mv.dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(mv.src), str(mv.dst))
            done.append(mv)
            manifest_entries.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "rule": mv.rule_id, "reason": mv.reason,
                "src": str(mv.src), "dst": str(mv.dst),
                "size": mv.size, "sha256": mv.sha256,
            })
        else:
            done.append(mv)  # dry-run：全部作为「将移动」展示

    summary = {
        "apply": apply,
        "dest": str(dest),
        "planned": len(moves),
        "moved": len(done) if apply else 0,
        "skipped_identical": len(skipped),
        "bytes": sum(m.size for m in (done if apply else moves)),
    }

    if apply and manifest_entries:
        _append_manifest(dest, manifest_entries)
    summary["manifest"] = str(dest / MANIFEST_NAME)
    return {"summary": summary,
            "moves": [_move_dict(m, apply) for m in (done if apply else moves)],
            "skipped": [_move_dict(m, apply) for m in skipped]}


def _move_dict(mv: Move, apply: bool) -> dict:
    return {
        "rule": mv.rule_id, "reason": mv.reason,
        "src": str(mv.src), "dst": str(mv.dst), "size": mv.size,
        **({"skipped": True, "skip_reason": mv.skip_reason} if mv.skipped else {}),
    }


def _append_manifest(dest: Path, entries: list[dict]) -> None:
    path = dest / MANIFEST_NAME
    data = {"version": 1, "entries": []}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    data.setdefault("entries", []).extend(entries)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="archive", description="workspace 历史文件归档")
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="真实移动（默认 dry-run）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    dest = args.dest.resolve()

    # 安全：dest 不能在 root 内的非 .archive 位置；默认 .archive 已被规则排除
    try:
        dest.relative_to(root)
        if dest.name != ".archive":
            print("错误: --dest 若在 root 内，目录名必须为 .archive（防自移动）",
                  file=sys.stderr)
            return 2
    except ValueError:
        pass  # dest 在 root 外，允许

    moves = plan(root, dest, time.time())
    result = execute(moves, apply=args.apply, dest=dest)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        s = result["summary"]
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"=== archive {mode} → {s['dest']} ===")
        print(f"planned {s['planned']} | moved {s['moved']} | "
              f"skipped {s['skipped_identical']} | {s['bytes'] // 1024 // 1024}MB")
        for m in result["moves"][:20]:
            print(f"  [{m['rule']}] {m['src']} → {m['dst']}")
        if len(result["moves"]) > 20:
            print(f"  …其余 {len(result['moves']) - 20} 项见 --json / manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
