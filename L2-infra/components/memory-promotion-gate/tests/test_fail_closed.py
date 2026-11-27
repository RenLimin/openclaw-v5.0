#!/usr/bin/env python3
"""fail-closed：无 recalls 信号时 --apply 非零退出且不写盘。"""
from pathlib import Path

import promote as pg


def _ws(tmp_path: Path) -> Path:
    (tmp_path / "memory" / "dreaming" / "light").mkdir(parents=True)
    block = ("- Candidate: 普通条目\n  - confidence: 0.62\n"
             "  - evidence: memory/2026-11-27.md:5-5\n  - recalls: 0\n  - status: staged\n")
    (tmp_path / "memory" / "dreaming" / "light" / "2026-11-27.md").write_text(
        "# Light\n\n" + block, encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("# MEMORY.md\n", encoding="utf-8")
    return tmp_path


def test_apply_fails_closed_without_recalls(tmp_path, capsys):
    ws = _ws(tmp_path)
    before = (ws / "MEMORY.md").read_text(encoding="utf-8")
    rc = pg.main(["--workspace", str(ws), "--apply", "--no-probe"])
    assert rc == 2
    assert (ws / "MEMORY.md").read_text(encoding="utf-8") == before


def test_apply_ok_with_recalls(tmp_path):
    ws = _ws(tmp_path)
    entries = list(pg.accumulate(pg.parse_candidates(ws)).values())
    scored = [pg.score_candidate(e, recalls=4) for e in entries]
    state_path = tmp_path / "state" / "scores.json"
    promotable, _, _ = pg.build_plan(ws, scored, min_score=0.0, min_days=1)
    assert pg.apply_plan(ws, promotable, state_path, pg.load_state(state_path)) == 1
    assert "dream-promoted:" in (ws / "MEMORY.md").read_text(encoding="utf-8")


def test_missing_memory_md_errors(tmp_path):
    ws = _ws(tmp_path)
    (ws / "MEMORY.md").unlink()
    entries = list(pg.accumulate(pg.parse_candidates(ws)).values())
    scored = [pg.score_candidate(e, recalls=4) for e in entries]
    promotable, _, _ = pg.build_plan(ws, scored, min_score=0.0, min_days=1)
    try:
        pg.apply_plan(ws, promotable, tmp_path / "state" / "s.json", {})
    except SystemExit:
        return
    raise AssertionError("expected SystemExit when MEMORY.md missing")
