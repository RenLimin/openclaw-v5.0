"""system-governor v1.1 — audit_classify 分类/建议/稳定 ID 测试。

黄金基准见 DESIGN-DETAIL-system-governor-v1.1.md §5。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import audit_classify as ac  # noqa: E402
from src.models import AuditItem  # noqa: E402


def _audit(probe_name: str, status: str, detail: str) -> dict:
    return {"sections": {ac.SECTION_CONSISTENCY: [{"name": probe_name, "status": status, "detail": detail}]}}


# ── 六类探针 → 正确 category/tier ─────────────────────────────────────

def test_classify_p1_drift():
    items = ac.classify(_audit("P1 计数漂移", "⚠️", "发现 41 / 登记 42，漂移"))
    assert len(items) == 1
    assert items[0].category == "口径漂移"
    assert items[0].tier == "L1"
    assert "gen_asset_inventory" in items[0].suggestion


def test_classify_p2_broken():
    items = ac.classify(_audit("P2 路径断链", "⚠️", "2 条断链: L2-infra/components/mcp-server（00-arch.md）; L2-infra/components/session-orchestrator"))
    assert len(items) == 2
    assert all(i.category == "断链" and i.tier == "L2" for i in items)
    assert items[0].detail["path"] == "L2-infra/components/mcp-server"
    assert items[1].detail["path"] == "L2-infra/components/session-orchestrator"


def test_classify_p3_skeleton():
    items = ac.classify(_audit("P3 空壳组件", "⚠️", "1 个: health-engine（README.md: 0 py）"))
    assert len(items) == 1
    assert items[0].category == "空壳"
    assert items[0].tier == "L2"
    assert items[0].detail["component"] == "health-engine"


def test_classify_p4_untracked():
    items = ac.classify(_audit("P4 未跟踪/未提交", "⚠️", "未跟踪 12 / 未提交 2 超阈值: ?? a.py"))
    assert len(items) == 1
    assert items[0].category == "口径漂移"
    assert items[0].tier == "L2"


def test_classify_p5_hardcoded():
    items = ac.classify(_audit("P5 硬编码根路径", "⚠️", "1 处: L2-infra/x.py:5"))
    assert len(items) == 1
    assert items[0].category == "残留"
    assert items[0].tier == "L2"
    assert items[0].detail["file"] == "L2-infra/x.py"
    assert items[0].detail["line"] == 5


def test_classify_p6_duplicate():
    items = ac.classify(_audit("P6 重复资产", "⚠️", "同内容重复 1 组: a/1.txt ↔ b/1.txt"))
    assert len(items) == 1
    assert items[0].category == "重复"
    assert items[0].tier == "L1"
    assert items[0].detail["paths"] == ["a/1.txt", "b/1.txt"]


# ── 稳定 ID 幂等 ──────────────────────────────────────────────────────

def test_stable_id_idempotent():
    audit = _audit("P2 路径断链", "⚠️", "1 条断链: L2-infra/components/mcp-server（00-arch.md）")
    a1 = ac.classify(audit)[0]
    a2 = ac.classify(audit)[0]
    assert a1.id == a2.id, "同 evidence 多轮审计 ID 必须不变（幂等）"


def test_stable_id_distinct_items():
    audit = _audit("P2 路径断链", "⚠️", "2 条断链: L2-infra/components/mcp-server; L2-infra/components/session-orchestrator")
    items = ac.classify(audit)
    assert len(set(i.id for i in items)) == 2, "不同断链项 ID 必须不同"


# ── 过滤与状态 ────────────────────────────────────────────────────────

def test_classify_only_filter():
    audit = _audit("P1 计数漂移", "⚠️", "发现 41 / 登记 42，漂移")
    assert len(ac.classify(audit, only={"P3"})) == 0
    assert len(ac.classify(audit, only={"P1"})) == 1


def test_classify_ignores_ok_items():
    assert ac.classify(_audit("P1 计数漂移", "✅", "一致")) == []


def test_initial_status_by_tier():
    item = AuditItem(id="P6-x", category="重复", evidence="e", suggestion="s", tier="L1", status="pending")
    assert ac.initial_status(item).status == "pending"   # L1 → dry-run 清单
    item_l2 = AuditItem(id="P2-x", category="断链", evidence="e", suggestion="s", tier="L2", status="pending")
    assert ac.initial_status(item_l2).status == "needs-human"  # L2 → 停手
