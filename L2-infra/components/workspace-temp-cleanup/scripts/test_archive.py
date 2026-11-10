"""归档规则 + 执行器黄金基准测试。

契约见 DESIGN-DETAIL-system-governor-v1.0.md §6（test_archive）。
全部在 tmp_path 临时 fixture 上进行，不触碰真实 workspace。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import archive  # noqa: E402
import archive_rules as R  # noqa: E402

DAY = 86400
NOW = time.time()


def _hit(path, root, *, mtime=NOW - 100 * DAY, size=0):
    return R.classify(Path(path), Path(root), mtime_epoch=mtime,
                      size_bytes=size, now_epoch=NOW)


# ── 规则命中 ─────────────────────────────────────────────────────────────

def test_r1_large_product():
    hit = _hit("/root/big.xlsx", "/root", size=60 * 1024 * 1024, mtime=NOW - DAY)
    assert hit and hit.rule_id == "R1" and hit.archive_subdir == ""


def test_r2_old_intermediate():
    hit = _hit("/root/tmp/old.tmp", "/root", mtime=NOW - 60 * DAY)
    assert hit and hit.rule_id == "R2" and hit.archive_subdir == "intermediate"


def test_r3_old_backup():
    hit = _hit("/root/x.bak.v3", "/root", mtime=NOW - 120 * DAY)
    assert hit and hit.rule_id == "R3" and hit.archive_subdir == "backup"


def test_r4_excluded_never_archived():
    # data 目录 / memory / 数据库 / output 当前周期
    assert _hit("/root/data/bdms.db", "/root") is None
    assert _hit("/root/memory/2026-11-10.md", "/root") is None
    assert _hit("/root/output/确认.xlsx", "/root",
                size=80 * 1024 * 1024) is None
    assert _hit("/root/data/x.tmp", "/root", mtime=NOW - 120 * DAY) is None


def test_no_rule_for_fresh_small_file():
    # 新近、小体积、非中间/备份 → 不归档
    assert _hit("/root/normal.md", "/root", mtime=NOW - DAY, size=100) is None
    # 大 xlsx 但在账龄阈值内仍按 R1（体积规则不看账龄）→ 命中
    # 小 tmp 但未到 30 天 → 不归档
    assert _hit("/root/tmp/fresh.tmp", "/root", mtime=NOW - 3 * DAY) is None


# ── 执行器（真实文件 fixture）─────────────────────────────────────────────

def _make_workspace(root: Path):
    # 一个应归档的旧 .bak（R2），一个受保护文件，一个普通文件
    old = root / "tmp" / "old.tmp"
    old.parent.mkdir(parents=True)
    old.write_text("old intermediate", encoding="utf-8")
    old_mtime = NOW - 60 * DAY
    import os
    os.utime(old, (old_mtime, old_mtime))

    prot = root / "data" / "keep.db"
    prot.parent.mkdir(parents=True)
    prot.write_text("db", encoding="utf-8")

    normal = root / "readme.md"
    normal.write_text("hi", encoding="utf-8")
    return old, prot, normal


def test_dry_run_zero_moves(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    dest = root / ".archive"
    old, prot, normal = _make_workspace(root)

    moves = archive.plan(root, dest, NOW)
    result = archive.execute(moves, apply=False, dest=dest)
    assert result["summary"]["moved"] == 0
    assert result["summary"]["planned"] == 1   # 仅 old.tmp
    assert old.exists()                        # 源文件原样
    assert not dest.exists()                   # 未创建归档区


def test_apply_moves_and_manifest(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    dest = root / ".archive"
    old, prot, normal = _make_workspace(root)

    moves = archive.plan(root, dest, NOW)
    result = archive.execute(moves, apply=True, dest=dest)
    assert result["summary"]["moved"] == 1
    assert not old.exists()                    # 源已移走
    # 落到 intermediate 子目录并保留相对路径
    assert (dest / "intermediate" / "tmp" / "old.tmp").exists()
    assert prot.exists() and normal.exists()   # 受保护/普通不动
    # manifest 登记
    man = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    assert len(man["entries"]) == 1
    assert man["entries"][0]["rule"] == "R2"
    assert man["entries"][0]["sha256"]


def test_idempotent_second_apply(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    dest = root / ".archive"
    _make_workspace(root)

    moves1 = archive.plan(root, dest, NOW)
    r1 = archive.execute(moves1, apply=True, dest=dest)
    assert r1["summary"]["moved"] == 1

    # 第二轮：源已不在，plan 为空
    moves2 = archive.plan(root, dest, NOW)
    r2 = archive.execute(moves2, apply=True, dest=dest)
    assert r2["summary"]["planned"] == 0
    assert r2["summary"]["moved"] == 0
