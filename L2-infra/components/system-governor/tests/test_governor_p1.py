"""system-governor P1 测试：policy / ledger / orchestrator / lane_d。

黄金基准见 DESIGN-DETAIL-system-governor-v1.0.md §6。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import ledger, orchestrator, policy  # noqa: E402
from src.models import Finding, LaneResult  # noqa: E402
from src.lanes import lane_d_tasks  # noqa: E402


# ── policy ───────────────────────────────────────────────────────────────

def test_policy_tier_lookup():
    f_auto = Finding(lane="A", item="llm_timeout", severity="critical", status="open",
                     evidence="tier=auto\nxxx")
    f_file = Finding(lane="C", item="temp_clean", severity="warning", status="open",
                     evidence="xxx")
    f_confirm = Finding(lane="B", item="provider_key_format", severity="critical",
                        status="open", evidence="xxx")
    assert policy.tier_for(f_auto) == policy.AUTO
    assert policy.tier_for(f_file) == policy.FILE
    assert policy.tier_for(f_confirm) == policy.CONFIRM


def test_policy_default_confirm():
    f = Finding(lane="X", item="unknown_item", severity="info", status="open",
                evidence="")
    assert policy.tier_for(f) == policy.CONFIRM  # 未知项默认需人工


def test_policy_dry_run_no_write():
    f_auto = Finding(lane="A", item="llm_timeout", severity="critical", status="open",
                     evidence="tier=auto")
    f_file = Finding(lane="C", item="temp_clean", severity="warning", status="open",
                     evidence="")
    # dry-run：即使 L0/L1 也绝不写
    assert not policy.will_write(f_auto, apply=False)
    assert not policy.will_write(f_file, apply=False)
    assert policy.resolve_status(f_auto, apply=False) == "planned"
    assert policy.resolve_status(f_file, apply=False) == "planned"


def test_policy_apply_respects_tiers():
    f_auto = Finding(lane="A", item="llm_timeout", severity="critical", status="open",
                     evidence="tier=auto")
    f_confirm = Finding(lane="B", item="provider_key_format", severity="critical",
                        status="open", evidence="")
    f_forbidden = Finding(lane="A", item="x", severity="critical", status="open",
                          evidence="tier=forbidden")
    assert policy.will_write(f_auto, apply=True)
    assert not policy.will_write(f_confirm, apply=True)   # L2 永不自动
    assert not policy.will_write(f_forbidden, apply=True)  # L3 永不执行
    assert policy.resolve_status(f_confirm, apply=True) == "needs-human"


# ── ledger ───────────────────────────────────────────────────────────────

def test_dedupe_same_key_keeps_most_severe():
    a = Finding(lane="A", item="x", severity="warning", status="open",
                evidence="same evidence", idempotency_key="k1")
    b = Finding(lane="B", item="x", severity="critical", status="open",
                evidence="same evidence", idempotency_key="k1")
    out = ledger.dedupe([a, b])
    assert len(out) == 1
    assert out[0].severity == "critical"


def test_ledger_report_summary():
    r1 = LaneResult(lane="A")
    r1.add(Finding(lane="A", item="a1", severity="warning", status="open",
                   evidence="e1", idempotency_key="k1"))
    r1.add(Finding(lane="A", item="a2", severity="info", status="auto-fixed",
                   evidence="e2", idempotency_key="k2"))
    r2 = LaneResult(lane="B")
    r2.add(Finding(lane="B", item="b1", severity="critical", status="needs-human",
                   evidence="e1", idempotency_key="k1"))  # 与 a1 同 key → 去重留 critical
    report = ledger.build_report({"A": r1, "B": r2}, apply=True)
    assert report.summary["total_unique"] == 2
    assert report.summary["total_raw"] == 3
    assert report.summary["auto_fixed"] == 1
    assert report.summary["needs_human"] == 1


def test_ledger_save_roundtrip(tmp_path):
    r1 = LaneResult(lane="A")
    r1.add(Finding(lane="A", item="a1", severity="warning", status="open",
                   evidence="evidence 中文", idempotency_key="k1"))
    report = ledger.build_report({"A": r1})
    path = ledger.save_report(report, tmp_path / "ledger.json")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["lanes"]["A"]["findings"][0]["evidence"] == "evidence 中文"


# ── orchestrator ─────────────────────────────────────────────────────────

def test_orchestrate_runs_all_lanes():
    def runner_a():
        return [Finding(lane="A", item="a", severity="info", status="ok",
                        evidence="", idempotency_key="ka")]
    def runner_b():
        return [Finding(lane="B", item="b", severity="info", status="ok",
                        evidence="", idempotency_key="kb")]
    results = orchestrator.orchestrate({"A": runner_a, "B": runner_b})
    assert sorted(results) == ["A", "B"]
    assert results["A"].findings[0].item == "a"


def test_orchestrate_lane_error_isolated():
    def bad_runner():
        raise RuntimeError("boom")
    def good_runner():
        return [Finding(lane="B", item="b", severity="info", status="ok",
                        evidence="", idempotency_key="kb")]
    results = orchestrator.orchestrate({"A": bad_runner, "B": good_runner})
    assert results["A"].findings[0].item == "lane_error"
    assert results["B"].findings[0].item == "b"


def test_orchestrate_timeout_isolated():
    def slow_runner():
        import time
        time.sleep(10)
        return []
    results = orchestrator.orchestrate({"A": slow_runner}, max_workers=1)
    # 预算默认 120s，这里手动用短预算验证超时路径
    from src.orchestrator import run_lane_with_budget
    r = run_lane_with_budget("A", slow_runner, budget=1)
    assert r.findings[0].item == "lane_timeout"


# ── lane_d ───────────────────────────────────────────────────────────────

def _seed_tasks_db(db_path):
    """造一个含 active 任务的临时 tasks.db，隔离测试不碰生产库。"""
    import sqlite3
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS tasks ("
                 "task_id TEXT PRIMARY KEY, name TEXT NOT NULL, "
                 "session_key TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', "
                 "phase TEXT NOT NULL DEFAULT '', step_index INTEGER NOT NULL DEFAULT 0, "
                 "total_steps INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, "
                 "status TEXT NOT NULL DEFAULT 'active', result TEXT NOT NULL DEFAULT '', "
                 "entries_json TEXT NOT NULL DEFAULT '[]', started_at TEXT NOT NULL, "
                 "last_updated TEXT NOT NULL)")
    conn.execute("INSERT OR REPLACE INTO tasks VALUES("
                 "'task-gov-test','测试任务','agent:main:dashboard:gov','',"
                 "'实现',1,3,0,'active','','[]','2026-11-10T10:00:00','2026-11-10T10:00:00')")
    conn.commit()
    conn.close()


def test_lane_d_returns_findings(tmp_path, monkeypatch):
    db = tmp_path / "memory" / "tasks.db"
    _seed_tasks_db(db)
    monkeypatch.setenv("TASK_TRACKER_DB", str(db))
    findings = lane_d_tasks.run()
    # v1.2：从 SQLite 读 active 任务 → 至少一条 current_task
    assert any(f.item == "current_task" for f in findings)


def test_lane_d_no_write(tmp_path, monkeypatch):
    """Lane D 纯只读：不产生任何写动作档位。"""
    db = tmp_path / "memory" / "tasks.db"
    _seed_tasks_db(db)
    monkeypatch.setenv("TASK_TRACKER_DB", str(db))
    findings = lane_d_tasks.run()
    for f in findings:
        assert policy.tier_for(f) in (policy.CONFIRM, policy.FORBIDDEN)
