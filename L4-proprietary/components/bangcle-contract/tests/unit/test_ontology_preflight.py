"""P5.4 单测：ProposalService.preflight（详设 §6）。

覆盖：
- preflight 在 validated 提案上执行：dry_run 演练全部写回步骤；
- OaWritebackConnector 在 preflight 下只落审计、无 HTTP（spy 断言）；
- preflight 不产生决策记录、不改变提案状态（保持 validated）、
  不应用 change_set（无业务副作用）；
- 非 validated 提案 preflight → ValueError；
- 多步 Saga preflight：全部步骤 dry-run 执行，报告含每步结果；
- 失败步骤 preflight → ok=False + 错误报告（不抛、不落 failed）。
"""
from __future__ import annotations

import json
import os
import sys

import pytest

COMPONENT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

from contract_review.ontology_bridge import (  # noqa: E402
    ContractOntologyBridge,
    assemble,
)
from contract_review.ontology_bridge.oa_connector import (  # noqa: E402
    OaWritebackConnector,
)
from ai_kb.ontology import SagaContext  # noqa: E402


@pytest.fixture()
def bridge(tmp_path):
    db = str(tmp_path / "contract.db")
    aikb = str(tmp_path / "ai_kb.db")
    assemble(db, aikb, register="HT-2026-009:300000")
    b = ContractOntologyBridge(db, aikb)
    yield b
    b.registry._ai_kb().close()


def _propose_validate(bridge, requestid="882663"):
    """直接走 L2：propose submit_to_oa → validate，返回 (ai, svc, proposal_id)。"""
    from ai_kb.db import AIKB
    from ai_kb.ontology import ActionRegistry, AssemblyGate, ProposalService
    ai = AIKB(bridge.ai_kb_path)
    ai.init_db()
    ai.init_ontology_tables()
    gate = AssemblyGate(open_by_default=False)
    reg = ActionRegistry(ai, gate=gate)
    svc = ProposalService(
        ai, reg,
        connectors={
            "oa_writeback": OaWritebackConnector(
                dry_run=True,
                target={"requestid": requestid, "action": "提交"},
            ),
        },
    )
    proposal = svc.propose_action(
        "bangcle-contract", "submit_to_oa", ["ht-2026-009"],
        {"requestid": requestid, "action": "提交", "comment": ""},
        caller_id="sales", caller_kind="human",
    )
    vr = svc.validate(proposal["id"], {
        "user_id": "sales", "role": "sales", "clearance": "internal",
    })
    assert vr["ok"] is True
    return ai, svc, proposal["id"]


# ---------- 1) preflight 全流程 dry-run ----------

def test_preflight_dry_run_ok(bridge):
    ai, svc, pid = _propose_validate(bridge)
    try:
        r = svc.preflight(pid)
        assert r["ok"] is True
        assert r["dry_run"] is True
        assert r["action"] == "submit_to_oa"
        assert r["connector"] == "oa_writeback"
        assert len(r["steps"]) == 1
        assert r["steps"][0]["step"] == "oa_writeback"
        assert r["steps"][0]["result"]["dry_run"] is True
        # 提案保持 validated（preflight 不改变状态）
        p = svc.get(pid)
        assert p["status"] == "validated"
    finally:
        ai.close()


def test_preflight_no_decision_record_no_side_effect(bridge):
    ai, svc, pid = _propose_validate(bridge)
    try:
        # 记录 preflight 前决策链
        chain_before = svc.decisions.replay(
            "bangcle-contract", "contract", "ht-2026-009",
        )
        r = svc.preflight(pid)
        assert r["ok"] is True
        chain_after = svc.decisions.replay(
            "bangcle-contract", "contract", "ht-2026-009",
        )
        # preflight 不产生决策记录
        assert len(chain_after) == len(chain_before) == 0
        # identity metadata 无新 applied_changes（preflight 不应用 change_set）
        ident = bridge.registry.get_identity("HT-2026-009")
        md = ident["metadata"]
        if isinstance(md, str):
            md = json.loads(md)
        assert md.get("applied_changes") == []  # 初始空，preflight 未追加
    finally:
        ai.close()


def test_preflight_no_http(bridge, monkeypatch):
    """preflight 下 OaWritebackConnector.apply 只落审计，无 HTTP。"""
    calls = {"apply": 0}
    real_apply = OaWritebackConnector.apply

    def spy_apply(self, ctx):
        calls["apply"] += 1
        assert ctx.dry_run is True  # 连接器感知 preflight 语义
        return real_apply(self, ctx)

    monkeypatch.setattr(OaWritebackConnector, "apply", spy_apply)
    ai, svc, pid = _propose_validate(bridge)
    try:
        r = svc.preflight(pid)
        assert r["ok"] is True
        assert calls["apply"] == 1
    finally:
        ai.close()


# ---------- 2) 非 validated 拒绝 ----------

def test_preflight_requires_validated(bridge):
    from ai_kb.db import AIKB
    from ai_kb.ontology import ActionRegistry, AssemblyGate, ProposalService
    ai = AIKB(bridge.ai_kb_path)
    ai.init_db()
    ai.init_ontology_tables()
    gate = AssemblyGate(open_by_default=False)
    reg = ActionRegistry(ai, gate=gate)
    svc = ProposalService(
        ai, reg,
        connectors={
            "oa_writeback": OaWritebackConnector(
                dry_run=True, target={"requestid": "882663", "action": "提交"},
            ),
        },
    )
    try:
        proposal = svc.propose_action(
            "bangcle-contract", "submit_to_oa", ["ht-2026-009"],
            {"requestid": "882663", "action": "提交"},
            caller_id="sales", caller_kind="human",
        )
        # pending 提案不可 preflight
        with pytest.raises(ValueError, match="requires 'validated'"):
            svc.preflight(proposal["id"])
    finally:
        ai.close()


# ---------- 3) 失败步骤 preflight → ok=False ----------

def test_preflight_failed_step_returns_ok_false(bridge, monkeypatch):
    """第 1 步成功、第 2 步失败：preflight 报告失败，不落 failed 状态。"""
    from ai_kb.ontology.connectors.saga import SagaStep, SagaOrchestrator

    class BoomConnector(OaWritebackConnector):
        name = "boom_step"

        def apply(self, ctx):
            raise RuntimeError("boom in preflight")

    # 构造带两步的 service（第二步 boom）
    def _svc_with_2steps():
        from ai_kb.db import AIKB
        from ai_kb.ontology import ActionRegistry, AssemblyGate, ProposalService
        ai = AIKB(bridge.ai_kb_path)
        ai.init_db()
        ai.init_ontology_tables()
        gate = AssemblyGate(open_by_default=False)
        reg = ActionRegistry(ai, gate=gate)
        svc = ProposalService(
            ai, reg,
            connectors={
                "oa_writeback": OaWritebackConnector(
                    dry_run=True,
                    target={"requestid": "882663", "action": "提交"},
                ),
                "boom_step": BoomConnector(
                    dry_run=True,
                    target={"requestid": "882663", "action": "提交"},
                ),
            },
        )
        # 补第二步（测试专用直插 ont_writeback_step）
        action = reg.get_action("bangcle-contract", "submit_to_oa")
        import sqlite3
        conn = sqlite3.connect(bridge.ai_kb_path)
        conn.execute(
            "INSERT INTO ont_writeback_step "
            "(action_type_id, seq, connector_key, payload_schema, created_at) "
            "VALUES (?, 2, 'boom_step', NULL, ?)",
            (action["id"], ai.get_now()),
        )
        conn.commit()
        conn.close()
        return ai, svc

    ai, svc = _svc_with_2steps()
    try:
        # propose + validate
        proposal = svc.propose_action(
            "bangcle-contract", "submit_to_oa", ["ht-2026-009"],
            {"requestid": "882663", "action": "提交"},
            caller_id="sales", caller_kind="human",
        )
        vr = svc.validate(proposal["id"], {
            "user_id": "sales", "role": "sales", "clearance": "internal",
        })
        assert vr["ok"] is True
        r = svc.preflight(proposal["id"])
        assert r["ok"] is False
        assert r["error"] == "boom in preflight"
        assert r["saga_report"]["failed_step"] == "boom_step"
        # 提案不落 failed（保持 validated）
        p = svc.get(proposal["id"])
        assert p["status"] == "validated"
    finally:
        ai.close()
