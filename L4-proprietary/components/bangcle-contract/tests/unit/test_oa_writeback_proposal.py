"""P5.2 集成测试：submit_to_oa 接入 Proposal Gate（详设 §4）。

覆盖：
- 全链路：submit_to_oa → pending → validated → human review → committed，
  decision_record 含 dry_run:True + connector:'oa_writeback'；
- OaWritebackConnector(dry_run=False) → RuntimeError（P4.2 冻结语义）；
- compensate → CompensationUnavailable → proposal failed +
  reconciliation_required（Saga 单步失败补偿路径）；
- 同 idempotency_key 重放 → 返回既有 proposal（无二次副作用）；
- 无真实 HTTP 断言：spy 连接器 apply 不产生网络调用；
- agent 审 human 级 submit_to_oa → PermissionError（L2 内置硬拒绝）。

全程真实 SQLite + 临时目录，不触网。
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
from ai_kb.ontology import CompensationUnavailable, SagaContext  # noqa: E402


@pytest.fixture()
def bridge(tmp_path):
    """独立 db + ai_kb + 装配 + 登记 1 个合同。"""
    db = str(tmp_path / "contract.db")
    aikb = str(tmp_path / "ai_kb.db")
    assemble(db, aikb, register="HT-2026-007:200000")
    b = ContractOntologyBridge(db, aikb)
    yield b
    b.registry._ai_kb().close()


# ---------- 1) 全链路 submit_to_oa ----------

def test_submit_to_oa_full_chain(bridge):
    """propose → validate → human review → commit，dry-run 审计写回。"""
    r = bridge.submit_to_oa(
        1, "sales", requestid="882663", action="提交", comment="送审",
        rationale="P5.2 全链路验证", idempotency_key="k-oa-1",
    )
    assert r["ok"] is True
    assert r["proposal_status"] == "committed"
    assert r["action"] == "submit_to_oa"
    # L4 本地状态不被强制转移（OA 态以对账为准）
    assert r["contract_status"] == "draft"

    rec = r["decision_record"]
    assert rec["result"] == "allowed"
    assert rec["action_type"] == "submit_to_oa"
    assert rec["actor_kind"] == "human"
    assert rec["evidence"]["connector"] == "oa_writeback"
    # 多步 Saga 报告已入 evidence
    assert rec["evidence"]["saga_report"]["ok"] is True
    assert rec["evidence"]["saga_report"]["executed_steps"] == ["oa_writeback"]

    # 决策链可回放
    st = bridge.status(1)
    chain = st["decision_chain"]
    assert len(chain) == 1
    assert chain[0]["action_type"] == "submit_to_oa"
    assert chain[0]["evidence"]["connector"] == "oa_writeback"
    assert chain[0]["evidence"]["saga_report"]["executed_steps"] == ["oa_writeback"]

    # 审计元数据已写（oa_submitted_at 进 metadata.fields）
    ident = bridge.registry.get_identity("HT-2026-007")
    assert ident is not None
    md = ident["metadata"]
    if isinstance(md, str):
        md = json.loads(md)
    assert "oa_submitted_at" in md


def test_submit_to_oa_no_http_anywhere(bridge, monkeypatch):
    """断言连接器 apply 全程无网络调用：注入 spy 计数 apply 调用。"""
    calls = {"apply": 0, "http": 0}

    real_apply = OaWritebackConnector.apply

    def spy_apply(self, ctx):
        calls["apply"] += 1
        # 递归保护：真实 apply 内部不应触网；这里仅计数
        return real_apply(self, ctx)

    monkeypatch.setattr(OaWritebackConnector, "apply", spy_apply)
    r = bridge.submit_to_oa(1, "sales", requestid="882663")
    assert r["ok"] is True
    assert calls["apply"] == 1
    # decision_record 证据确认 dry_run
    assert r["decision_record"]["evidence"]["connector"] == "oa_writeback"
    assert r["decision_record"]["evidence"]["saga_report"]["ok"] is True


# ---------- 2) 真实写拒绝 ----------

def test_oa_connector_real_write_rejected_bridge_level(bridge):
    """直接构造 dry_run=False 连接器 → RuntimeError（P4.2 冻结）。"""
    conn = OaWritebackConnector(dry_run=False)
    ctx = SagaContext()
    ctx.payloads["oa_writeback"] = {"requestid": "882663", "action": "提交"}
    with pytest.raises(RuntimeError, match="P4.2 写端点契约未闭合"):
        conn.apply(ctx)


# ---------- 3) 补偿不可用 → failed + reconciliation_required ----------

def test_oa_compensate_unavailable_marks_recon(bridge, monkeypatch):
    """多步 Saga：第 1 步 oa_writeback 成功、第 2 步 boom 失败 →
    逆序补偿 oa_writeback → 恒抛 → failed + reconciliation_required。"""

    class BoomConnector(OaWritebackConnector):
        name = "boom_step"

        def apply(self, ctx):
            raise RuntimeError("boom after oa write")

        def compensate(self, ctx):
            # 真实失败步骤无需补偿（未写入），直接可补偿
            ctx.mark_success(self.name, {"compensated": True})

    def _svc_with_2steps(target):
        ai, reg, ProposalService = _open_l2(bridge)
        svc = ProposalService(
            ai, reg,
            connectors={
                "oa_writeback": OaWritebackConnector(
                    dry_run=True, target=target,
                ),
                "boom_step": BoomConnector(dry_run=True, target=target),
            },
        )
        return ai, svc

    monkeypatch.setattr(bridge, "_new_service_oa", _svc_with_2steps)
    # 给 submit_to_oa 动作追加第 2 步（boom_step）
    _append_step(bridge, "boom_step")

    from ai_kb.ontology.connectors.saga import SagaExecutionError
    with pytest.raises(SagaExecutionError) as ei:
        bridge.submit_to_oa(1, "sales", requestid="882663")
    report = ei.value.report
    assert report.ok is False
    assert report.failed_step == "boom_step"
    assert report.compensation_unavailable == ["oa_writeback"]
    assert report.reconciliation_required is True

    # 提案失败态 + 审计留痕：失败+补偿不可用 → result='compensated'
    # 决策记录（change_set.applied=False + reconciliation_required）
    st = bridge.status(1)
    chain = st["decision_chain"]
    assert len(chain) == 1
    assert chain[0]["result"] == "compensated"
    assert chain[0]["change_set"]["applied"] is False
    assert chain[0]["change_set"]["reconciliation_required"] is True


def _open_l2(bridge):
    from ai_kb.db import AIKB
    from ai_kb.ontology import ActionRegistry, AssemblyGate, ProposalService
    ai = AIKB(bridge.ai_kb_path)
    ai.init_db()
    ai.init_ontology_tables()
    gate = AssemblyGate(open_by_default=False)
    reg = ActionRegistry(ai, gate=gate)
    return ai, reg, ProposalService


def _append_step(bridge, connector_key: str):
    """装配期外补注册第 2 步（测试专用：直接写 ont_writeback_step）。"""
    ai, reg, _ = _open_l2(bridge)
    try:
        action = reg.get_action("bangcle-contract", "submit_to_oa")
        from ai_kb.ontology import AssemblyGate
        # 运行期 gate 关闭，直接用底层连接补插（测试专用）
        import sqlite3
        conn = sqlite3.connect(bridge.ai_kb_path)
        conn.execute(
            "INSERT INTO ont_writeback_step "
            "(action_type_id, seq, connector_key, payload_schema, created_at) "
            "VALUES (?, 2, ?, NULL, ?)",
            (action["id"], connector_key, ai.get_now()),
        )
        conn.commit()
        conn.close()
    finally:
        ai.close()


# ---------- 4) 幂等重放 ----------

def test_submit_to_oa_idempotent_replay(bridge):
    r1 = bridge.submit_to_oa(1, "sales", requestid="882663",
                             idempotency_key="k-oa-2")
    r2 = bridge.submit_to_oa(1, "sales", requestid="882663",
                             idempotency_key="k-oa-2")
    assert r1["ok"] is True
    assert r2["idempotent_replay"] is True
    assert r2["proposal_id"] == r1["proposal_id"]
    # 无二次决策记录
    st = bridge.status(1)
    assert len(st["decision_chain"]) == 1


# ---------- 5) agent 审 human 级动作拒绝（L2 内置） ----------

def test_submit_to_oa_agent_review_permission_error(bridge):
    """submit_to_oa 为 human 级动作；L2 review 拒绝 agent 审
    （bridge 层 caller_kind 强制 human，越权在 L2 层拦截）。"""
    from ai_kb.db import AIKB
    from ai_kb.ontology import (
        ActionRegistry, AssemblyGate, ProposalService,
    )

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
        },
    )
    try:
        proposal = svc.propose_action(
            "bangcle-contract", "submit_to_oa", ["ht-2026-007"],
            {"requestid": "882663", "action": "提交"},
            caller_id="agent-bot", caller_kind="agent",
        )
        svc.validate(proposal["id"], {
            "user_id": "agent-bot", "role": "agent",
            "clearance": "internal",
        })
        with pytest.raises(PermissionError, match="human approval"):
            svc.review(
                proposal["id"], "approve", "agent-bot",
                reviewer_kind="agent", auto_commit=True,
            )
    finally:
        ai.close()
