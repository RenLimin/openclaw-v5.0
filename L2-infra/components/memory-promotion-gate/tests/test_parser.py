#!/usr/bin/env python3
"""候选解析与跨日累积测试。"""
import promote as pg


def _report(candidates):
    lines = ["# Light Sleep", ""]
    for sn, conf, ev, rc, st in candidates:
        lines += [f"- Candidate: {sn}", f"  - confidence: {conf}", f"  - evidence: {ev}",
                  f"  - recalls: {rc}", f"  - status: {st}"]
    return "\n".join(lines) + "\n"


def test_parse_light_candidates(tmp_path):
    d = tmp_path / "memory" / "dreaming" / "light"
    d.mkdir(parents=True)
    (d / "2026-11-27.md").write_text(_report([
        ("命名规范：统一 kebab-case", 0.58, "memory/2026-11-27.md:10-10", 0, "staged"),
        ("流程：先设计后代码", 0.62, "memory/2026-11-27.md:20-20", 0, "staged"),
    ]), encoding="utf-8")
    raw = pg.parse_candidates(tmp_path)
    assert len(raw) == 2
    assert raw[0]["snippet"].startswith("命名规范")
    assert raw[0]["day"] == "2026-11-27"
    assert raw[0]["phase"] == "light"


def test_accumulate_cross_day(tmp_path):
    d = tmp_path / "memory" / "dreaming" / "light"
    d.mkdir(parents=True)
    block = ["- Candidate: 同一口径条目", "  - confidence: 0.58",
             "  - evidence: memory/2026-11-26.md:1-1", "  - recalls: 0", "  - status: staged"]
    (d / "2026-11-26.md").write_text("# Light Sleep\n\n" + "\n".join(block) + "\n", encoding="utf-8")
    (d / "2026-11-27.md").write_text("# Light Sleep\n\n" + "\n".join(block) + "\n", encoding="utf-8")
    acc = pg.accumulate(pg.parse_candidates(tmp_path))
    assert len(acc) == 1
    e = next(iter(acc.values()))
    assert e["days_seen"] == 2
    assert e["occurrences"] == 2
    assert e["avg_confidence"] == 0.58


def test_fingerprint_stable_across_whitespace():
    a = pg.fingerprint("命名  规范：A")
    b = pg.fingerprint("命名 规范：a")
    assert a == b


def test_evidence_path_split():
    d = pg.parse_candidates  # noqa
    import re
    m = pg.CANDIDATE_RE.search(
        "- Candidate: X\n  - confidence: 0.6\n  - evidence: memory/2026-11-27.md:443-462\n"
        "  - recalls: 0\n  - status: staged")
    assert m.group("evidence") == "memory/2026-11-27.md:443-462"
