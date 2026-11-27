#!/usr/bin/env python3
"""评分公式与门槛测试（含反两极化断言）。"""
import promote as pg


def _entry(days=2, occ=2, conf=0.58):
    return {"days_seen": days, "occurrences": occ, "avg_confidence": conf,
            "snippet": "命名规范：统一 kebab-case", "evidence": ["memory/x.md:1-1"],
            "fingerprint": pg.fingerprint("命名规范：统一 kebab-case"), "phases": ["light"]}


def test_recalls_increase_score():
    low = pg.score_candidate(_entry(), recalls=0)
    high = pg.score_candidate(_entry(), recalls=6)
    assert high["score"] > low["score"]


def test_score_not_constant_for_same_confidence():
    """同样 0.58 置信度，不同 recalls/days 必须产生不同分数（反两极化）。"""
    scores = {
        pg.score_candidate(_entry(days=d, occ=o), recalls=r)["score"]
        for d, o, r in [(1, 1, 0), (2, 1, 1), (3, 2, 2), (5, 4, 6)]
    }
    assert len(scores) >= 3


def test_days_seen_weight():
    one = pg.score_candidate(_entry(days=1, occ=1), recalls=0)
    seven = pg.score_candidate(_entry(days=7, occ=1), recalls=0)
    assert seven["score"] > one["score"]


def test_threshold_gate_min_days():
    ws = None
    promotable, blocked, pending = pg.build_plan(
        ws, [pg.score_candidate(_entry(days=1, occ=10), recalls=9)], min_score=0.0, min_days=2)
    assert promotable == []
    assert len(blocked) == 1


def test_weights_sum_to_one():
    assert abs(sum(pg.WEIGHTS.values()) - 1.0) < 1e-9
