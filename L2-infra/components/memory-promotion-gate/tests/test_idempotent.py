#!/usr/bin/env python3
"""dry-run→apply→再 apply 幂等性，真实文件副本上跑。"""
from pathlib import Path

import promote as pg


def _ws(tmp_path: Path, memory_body="# MEMORY.md\n\n## 变更历史\n") -> Path:
    (tmp_path / "memory" / "dreaming" / "light").mkdir(parents=True)
    block = ("- Candidate: 命名规范：统一 kebab-case\n  - confidence: 0.62\n"
             "  - evidence: memory/2026-11-26.md:5-5\n  - recalls: 0\n  - status: staged\n")
    (tmp_path / "memory" / "dreaming" / "light" / "2026-11-26.md").write_text(
        "# Light\n\n" + block, encoding="utf-8")
    (tmp_path / "memory" / "dreaming" / "light" / "2026-11-27.md").write_text(
        "# Light\n\n" + block, encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text(memory_body, encoding="utf-8")
    return tmp_path


def test_apply_then_idempotent(tmp_path):
    ws = _ws(tmp_path)
    entries = list(pg.accumulate(pg.parse_candidates(ws)).values())
    scored = [pg.score_candidate(e, recalls=3) for e in entries]  # 注入 recalls
    promotable, _, _ = pg.build_plan(ws, scored, min_score=0.0, min_days=1)
    assert len(promotable) == 1

    state_path = tmp_path / "state" / "scores.json"
    state = pg.load_state(state_path)
    n1 = pg.apply_plan(ws, promotable, state_path, state)
    assert n1 == 1
    body_after_first = (ws / "MEMORY.md").read_text(encoding="utf-8")
    assert "dream-promoted:" in body_after_first

    n2 = pg.apply_plan(ws, promotable, state_path, pg.load_state(state_path))
    assert n2 == 0
    assert (ws / "MEMORY.md").read_text(encoding="utf-8") == body_after_first


def test_dry_run_writes_nothing(tmp_path):
    ws = _ws(tmp_path)
    before = (ws / "MEMORY.md").read_text(encoding="utf-8")
    assert pg.main(["--workspace", str(ws), "--dry-run", "--no-probe"]) == 0
    assert (ws / "MEMORY.md").read_text(encoding="utf-8") == before
