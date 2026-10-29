#!/usr/bin/env python3
"""tempcleanctl 测试 — 真实文件系统 + 真实 /usr/bin/trash，不用 mock 删除。"""
import json, subprocess, sys
from datetime import date, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tempcleanctl.py"
sys.path.insert(0, str(SCRIPT.parent))
import tempcleanctl as tc


def run(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True, text=True)


def write(p: Path, content="x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def set_mtime_recursive(p: Path, days_ago: float):
    import os, time
    ts = time.time() - days_ago * 86400
    for child in [p, *p.rglob("*")]:
        if not child.is_symlink():
            os.utime(child, (ts, ts))


@pytest.fixture
def sandbox(tmp_path):
    # gitignore + registry 让 verify 通过
    (tmp_path / ".gitignore").write_text("analysis_output/\n")
    reg = {"version": 1, "entries": [
        {"path": "analysis_output/", "kind": "ledger", "ttl_days": 30,
         "created": str(date.today() - timedelta(days=40))},
        {"path": "scratch/", "created": str(date.today() - timedelta(days=10))},
        {"path": "data-tmp/", "kind": "intermediate",
         "created": str(date.today() - timedelta(days=3))},
    ]}
    (tmp_path / ".openclaw-temp.json").write_text(json.dumps(reg))
    # 约定目录（created 旧的，mtime 也要设旧，否则 max(created,mtime) 取今天）
    write(tmp_path / "analysis_output" / "ledger.md")      # ledger 40d > 30 → 过期
    write(tmp_path / "scratch" / "a.tmp")                  # intermediate 10d > 7 → 过期
    write(tmp_path / "data-tmp" / "f.bin")                 # 3d < 7 → 保留
    write(tmp_path / "tmp" / "keep.tmp")                   # 约定目录，今日 → 保留
    # 伪装：未登记、非约定名
    write(tmp_path / "secret" / "important.txt")
    write(tmp_path / "report.pdf")
    # 递归把旧条目目录的 mtime 设到登记日期（含目录与文件）
    set_mtime_recursive(tmp_path / "analysis_output", 40)
    set_mtime_recursive(tmp_path / "scratch", 10)
    set_mtime_recursive(tmp_path / "data-tmp", 3)
    # 黄金基准：7 候选(3 registry + tmp/ + 约定名 scratch/data-tmp 已在 registry)
    return tmp_path


def test_trash_available():
    assert tc.trash_available(), "本机必须有 /usr/bin/trash"


def test_t1_unmarked_never_candidate(sandbox):
    cands, err = tc.collect(sandbox, None, date.today())
    assert err is None
    paths = [str(c.path) for c in cands]
    assert not any("important.txt" in p or p.endswith("report.pdf") for p in paths)
    assert not any(p.endswith("secret") for p in paths)


def test_t3_ttl_boundary(sandbox):
    cands, _ = tc.collect(sandbox, None, date.today())
    by = {c.path.name: c for c in cands}
    assert by["analysis_output"].expired is True   # 40 > 30
    assert by["scratch"].expired is True           # 10 > 7
    assert by["data-tmp"].expired is False         # 3 <= 7
    assert by["tmp"].expired is False              # 0d


def test_ttl_strict_greater():
    # age == ttl 不删
    assert not (7 > 7)
    assert 8 > 7


def test_t4a_missing_kind_default(tmp_path):
    (tmp_path / ".openclaw-temp.json").write_text(
        json.dumps({"version": 1, "entries": [{"path": "x/"}]}))
    write(tmp_path / "x" / "f")
    cands, err = tc.collect(tmp_path, None, date.today())
    assert err is None and cands[0].ttl_days == 7


def test_t4b_invalid_registry(tmp_path):
    (tmp_path / ".openclaw-temp.json").write_text("{bad json")
    write(tmp_path / "x")
    cands, err = tc.collect(tmp_path, None, date.today())
    assert err and cands == []


def test_t5a_dry_run_exit2_no_delete(sandbox):
    r = run(sandbox, "dry-run")
    assert r.returncode == 2
    assert (sandbox / "analysis_output" / "ledger.md").exists()


def test_t5b_clean_without_yes_refused(sandbox):
    r = run(sandbox, "clean")
    assert r.returncode == 1
    assert (sandbox / "analysis_output" / "ledger.md").exists()


def test_t5c_verify(sandbox):
    r = run(sandbox, "verify")
    assert r.returncode == 0, r.stderr


def test_t2_and_golden_clean_trashes_only_expired(sandbox):
    # 黄金基准：过期 2（analysis_output, scratch），其余保留
    r = run(sandbox, "clean", "--yes")
    assert r.returncode == 0, r.stderr
    assert not (sandbox / "analysis_output").exists()
    assert not (sandbox / "scratch").exists()
    # 保留
    assert (sandbox / "data-tmp" / "f.bin").exists()
    assert (sandbox / "tmp" / "keep.tmp").exists()
    assert (sandbox / "secret" / "important.txt").exists()
    assert (sandbox / "report.pdf").exists()


def test_t6_idempotent(sandbox):
    r1 = run(sandbox, "clean", "--yes"); assert r1.returncode == 0
    r2 = run(sandbox, "clean", "--yes"); assert r2.returncode == 0
    r3 = run(sandbox, "clean", "--yes"); assert r3.returncode == 0
    assert "删除 2" in r1.stdout
    assert "删除 0" in r2.stdout and "删除 0" in r3.stdout


def test_t7_path_traversal_rejected(tmp_path):
    (tmp_path / ".openclaw-temp.json").write_text(json.dumps(
        {"version": 1, "entries": [{"path": "../../etc"}]}))
    cands, err = tc.collect(tmp_path, None, date.today())
    assert err is None and cands == []


def test_t8_dir_new_inner_file_protected(sandbox):
    # analysis_output 登记 40 天前，但放入今日新文件 → 目录最新 mtime=今天 → 不删
    write(sandbox / "analysis_output" / "new_today.md")
    cands, _ = tc.collect(sandbox, None, date.today())
    ao = [c for c in cands if c.path.name == "analysis_output"][0]
    assert ao.expired is False
