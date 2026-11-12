"""system-governor v1.1 — audit_flow 六环节工作流测试。

黄金基准见 DESIGN-DETAIL-system-governor-v1.1.md §5。
monkeypatch _collect（不跑真实 full_audit）与 _save_ledger（不落真实账本）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import audit_flow  # noqa: E402
from src.models import AuditItem  # noqa: E402

SECTION = audit_flow.audit_classify.SECTION_CONSISTENCY


def _fake_audit(detail: str) -> dict:
    return {"sections": {SECTION: [
        {"name": "P1 计数漂移", "status": "✅", "detail": "一致"},
        {"name": "P2 路径断链", "status": "⚠️", "detail": detail},
    ]}}


def test_flow_serial_and_ledger_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_flow, "_collect", lambda only, timeout: _fake_audit("1 条断链: L2-infra/components/mcp-server（a.md）"))
    monkeypatch.setattr(audit_flow.audit_exec, "_git_mv", lambda *a: (True, "ok"))
    ledger = tmp_path / "audit.json"

    payload = audit_flow.run(apply=True, root=tmp_path, ledger_path=ledger)

    # 账本 schema 合法
    assert ledger.exists()
    saved = json.loads(ledger.read_text(encoding="utf-8"))
    assert saved["apply"] is True
    assert saved["summary"]["total"] == 1
    assert saved["items"][0]["id"].startswith("P2-")
    assert saved["items"][0]["tier"] == "L2"
    assert saved["items"][0]["status"] == "needs-human"
    assert "regression" in saved and "remaining_warnings" in saved["regression"]
    # 六环节产出完整
    assert payload["timestamp"] and payload["items"] and payload["summary"]


def test_flow_dry_run_zero_write(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_flow, "_collect", lambda only, timeout: _fake_audit("1 条断链: L2-infra/components/x（a.md）"))
    ledger = tmp_path / "audit.json"

    payload = audit_flow.run(apply=False, root=tmp_path, ledger_path=ledger)
    assert payload["apply"] is False
    assert payload["summary"]["needs_human"] == 1
    assert payload["actions"] == []  # dry-run 零写


def test_flow_l1_apply_executes(tmp_path, monkeypatch):
    """L1 项 + apply → 执行 git mv；L2 项永不执行。"""
    audit = {"sections": {SECTION: [
        {"name": "P1 计数漂移", "status": "✅", "detail": "一致"},
        {"name": "P6 重复资产", "status": "⚠️", "detail": "同内容重复 1 组: b/keep.txt ↔ a/dup.txt"},
    ]}}
    monkeypatch.setattr(audit_flow, "_collect", lambda only, timeout: audit)
    moved: list[str] = []

    def fake_git_mv(src, dest, root):
        moved.append(src.name)
        return True, "ok"

    monkeypatch.setattr(audit_flow.audit_exec, "_git_mv", fake_git_mv)
    ledger = tmp_path / "audit.json"

    # 真实路径：P6 归位需要 src/dest 存在（detail paths 相对 root）
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    (a_dir / "dup.txt").write_text("x" * 2048)
    (b_dir / "keep.txt").write_text("x" * 2048)

    payload = audit_flow.run(apply=True, root=tmp_path, ledger_path=ledger)
    assert payload["summary"]["done"] == 1
    assert len(moved) == 1


def test_flow_regression_counts_remaining(tmp_path, monkeypatch):
    """回归环节：重跑 §12 后仍告警的探针计数。"""
    calls = {"n": 0}

    def fake_collect(only, timeout):
        calls["n"] += 1
        # 第二次（回归）仍告警
        if calls["n"] == 2:
            return {"sections": {SECTION: [
                {"name": "P2 路径断链", "status": "⚠️", "detail": "1 条断链: L2-infra/components/x（a.md）"},
            ]}}
        return _fake_audit("1 条断链: L2-infra/components/x（a.md）")

    monkeypatch.setattr(audit_flow, "_collect", fake_collect)
    ledger = tmp_path / "audit.json"
    payload = audit_flow.run(apply=False, root=tmp_path, ledger_path=ledger)
    assert calls["n"] == 2  # 取证 + 回归各一次
    assert payload["regression"]["remaining_count"] == 1
