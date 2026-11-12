"""system-governor v1.1 — Lane B §12 接入测试。

黄金基准见 DESIGN-DETAIL-system-governor-v1.1.md §5。
不触网、不跑 full_audit（monkeypatch _run_audit_json）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lanes import lane_b_assets as lb  # noqa: E402


def _audit_with_consistency(items: list[dict]) -> dict:
    return {"sections": {"3. 自研资产状态检测": [], "4. 模型与 Provider 健康检测": [], lb.SECTION_CONSISTENCY: items}}


def test_lane_b_aggregates_consistency_ok(monkeypatch):
    """✅ 探针 → info/ok finding。"""
    audit = _audit_with_consistency([
        {"name": "P1 计数漂移", "status": "✅", "detail": "发现 41 / 登记 41，一致"},
        {"name": "P2 路径断链", "status": "✅", "detail": "抽查 69 条路径引用，全部存在"},
    ])
    monkeypatch.setattr(lb, "_run_audit_json", lambda: audit)
    monkeypatch.setattr(lb, "_load_guardian", lambda: {"services": [], "gateway": True})
    findings = lb.run()
    ok_findings = [f for f in findings if f.item in ("P1 计数漂移", "P2 路径断链")]
    assert len(ok_findings) == 2
    assert all(f.status == "ok" and f.severity == "info" for f in ok_findings)


def test_lane_b_consistency_warning_points_to_audit(monkeypatch):
    """⚠️ 探针 → warning/open finding，action 指向 audit 工作流。"""
    audit = _audit_with_consistency([
        {"name": "P6 重复资产", "status": "⚠️", "detail": "同内容重复 17 组: a ↔ b"},
    ])
    monkeypatch.setattr(lb, "_run_audit_json", lambda: audit)
    monkeypatch.setattr(lb, "_load_guardian", lambda: {"services": [], "gateway": True})
    findings = lb.run()
    warn = [f for f in findings if f.item == "P6 重复资产"]
    assert len(warn) == 1
    assert warn[0].status == "open" and warn[0].severity == "warning"
    assert "governor.py audit" in warn[0].action


def test_lane_b_without_consistency_section_no_error(monkeypatch):
    """无 §12 章节（full_audit 旧版本）→ 不报错、无该节 findings。"""
    monkeypatch.setattr(lb, "_run_audit_json", lambda: {"sections": {"3. 自研资产状态检测": []}})
    monkeypatch.setattr(lb, "_load_guardian", lambda: {"services": [], "gateway": True})
    findings = lb.run()
    assert not any(f.evidence.startswith("12.") for f in findings)
