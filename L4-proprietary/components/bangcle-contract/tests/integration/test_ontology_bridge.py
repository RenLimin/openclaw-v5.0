"""P3 黄金基准 — Contract Ontology Bridge 全生命周期真实 SQLite 走查。

依据 DESIGN-OUTLINE-contract-ontology-bridge-v1.0 §7 验收标准：
1. 提交闭环：submit → pending → validated → auto approve → committed
   → contract.status draft→review1（L4 表 + L2 决策记录双写）
2. 越权拒绝：agent 审 human 级 approve → PermissionError，审计留痕
3. 非法转移：未 submit 直接 propose approve → L3 状态机拒绝，留违规痕
4. 幂等重放：同 idempotency_key 重复 submit → 返回既有提案，无二次副作用
5. 补偿回滚：多步 Saga 第二步注入失败 → 逆序补偿，L4 回滚 + failed + 决策记录
6. CWA：未登记对象直接操作 → 拒绝
7. CLI 冒烟：contractctl ontology 子命令真实可跑
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from contract_review.ontology_bridge import (  # noqa: E402
    ContractOntologyBridge,
    ContractWritebackConnector,
    NotifyConnector,
    assemble,
)
from contract_review.ontology_bridge._assembly import l3_register_all  # noqa: E402
from contract_review.ontology_bridge.registry import canonical_contract_no  # noqa: E402


@pytest.fixture()
def bridge(tmp_path):
    """独立 db + ai_kb + 装配 + 登记 2 个合同的桥实例。"""
    db = str(tmp_path / "contract.db")
    aikb = str(tmp_path / "ai_kb.db")
    assemble(db, aikb, register="HT-2026-001:100000,HT-2026-003:50000")
    b = ContractOntologyBridge(db, aikb)
    yield b
    b.registry._ai_kb().close() if hasattr(b.registry, "_ai_kb") else None


def _proposal_ids(bridge):
    return [p["id"] for p in bridge.proposals()]


# ---------- 1) 提交闭环 ----------

def test_submit_commit_closure(bridge):
    """submit：draft→review1，auto 审，L4 表 + L2 决策记录双写。"""
    r = bridge.submit(1, "sales", idempotency_key="k-sub")
    assert r["ok"] is True
    assert r["proposal_status"] == "committed"
    assert r["contract_status"] == "review1"

    # L4 表
    st = bridge.status(1)
    assert st["contract_status"] == "review1"
    assert st["metadata_status"] == "review1"  # 状态已同步回 L2 metadata
    assert st["registered"] is True

    # L2 决策记录
    chain = st["decision_chain"]
    assert len(chain) == 1
    assert chain[0]["action_type"] == "submit_contract"
    assert chain[0]["result"] == "allowed"
    assert chain[0]["actor_kind"] == "human"
    assert chain[0]["evidence"]["connector"] == "contract_writeback"
    assert "saga_steps" in chain[0]["evidence"]


# ---------- 2) 越权拒绝 ----------

def test_agent_review_human_action_permission_error(bridge):
    """agent 审 human 级 approve → PermissionError（L2 内置硬拒绝）。"""
    bridge.submit(1, "sales", idempotency_key="k-sub")
    with pytest.raises(PermissionError, match="human approval"):
        bridge._run(1, "approve", operator="agent-bot",
                    caller_kind="agent", approver_role="销售经理",
                    reviewer_kind="agent")


# ---------- 3) 非法转移 ----------

def test_illegal_transition_rejected(bridge):
    """未 submit 直接 approve → L3 状态机拒绝，提案留违规痕不 committed。"""
    r = bridge.approve(2, "boss", approver_role="销售经理")  # 合同2 仍是 draft
    assert r["ok"] is False
    assert r["proposal_status"] == "pending"  # 不迁移终态
    assert any(v.get("rule") == "illegal_transition" for v in r["violations"])
    # L4 状态未被污染
    st = bridge.status(2)
    assert st["contract_status"] == "draft"


# ---------- 4) 幂等重放 ----------

def test_idempotent_replay(bridge):
    """同 idempotency_key 重复 submit → 返回既有提案，无二次副作用。"""
    r1 = bridge.submit(1, "sales", idempotency_key="k-dup")
    r2 = bridge.submit(1, "sales", idempotency_key="k-dup")
    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r2.get("idempotent_replay") is True
    # 同一提案，无二次写回
    assert r1["proposal_id"] == r2["proposal_id"]
    assert len(_proposal_ids(bridge)) == 1
    # 决策链只有一条 submit
    st = bridge.status(1)
    assert len([d for d in st["decision_chain"] if d["action_type"] == "submit_contract"]) == 1


# ---------- 5) 补偿回滚（Saga 多步写回注入失败） ----------

def test_saga_compensation_rollback(tmp_path):
    """第二步 notify 注入失败 → 逆序补偿 contract 写回，L4 回 draft。"""
    db = str(tmp_path / "contract.db")
    aikb = str(tmp_path / "ai_kb.db")
    assemble(db, aikb, register="HT-2026-003:50000")

    l3_register_all(aikb)
    from ai_kb.db import AIKB
    from ai_kb.ontology import ActionRegistry, AssemblyGate, ProposalService, DecisionService
    from ai_kb.ontology.connectors.saga import SagaExecutionError

    ai = AIKB(aikb)
    ai.init_db()
    ai.init_ontology_tables()

    # 装配：submit 动作挂多步写回（contract_writeback → notify）
    gate = AssemblyGate()
    gate.open()
    reg = ActionRegistry(ai, gate=gate)
    act = reg.get_action("bangcle-contract", "submit_contract")
    reg.register_writeback_steps(act["id"], [
        {"seq": 1, "connector_key": "contract_writeback"},
        {"seq": 2, "connector_key": "notify"},
    ])
    gate.close()

    cw = ContractWritebackConnector(
        db,
        target={"contract_id": 1, "action": "submit"},
        before={"contract_id": 1, "status": "draft", "current_approver": None},
    )
    nf = NotifyConnector(db, fail_next=True)
    svc = ProposalService(ai, reg, connectors={"contract_writeback": cw, "notify": nf})

    p = svc.propose_action(
        "bangcle-contract", "submit_contract",
        [canonical_contract_no("HT-2026-003")],
        {"contract_no": "HT-2026-003", "target_state": "review1", "amount": 50000.0},
        caller_id="sales", caller_kind="human", idempotency_key="saga-t",
    )
    vr = svc.validate(p["id"], {"user_id": "sales", "role": "sales", "clearance": "internal"})
    assert vr["ok"] is True

    with pytest.raises(SagaExecutionError) as ei:
        svc.review(p["id"], "approve", "sales", reviewer_kind="human", auto_commit=True)
    report = ei.value.report
    assert report.executed_steps == ["contract_writeback", "notify"]
    assert report.failed_step == "notify"
    assert report.compensated == ["contract_writeback"]
    assert report.reconciliation_required is False

    # L4 状态补偿回滚 → draft
    from repository.db import Repository
    with Repository(db) as repo:
        row = repo.get_contract_row(1)
        assert row["status"] == "draft"
        audits = [a["action"] for a in repo.get_contract_with_history(1)["audit_logs"]]
        assert "ontology_submit" in audits
        assert "ontology_compensate" in audits

    # 决策记录 result=compensated；proposal failed
    ds = DecisionService(ai)
    stats = ds.stats("bangcle-contract")
    assert stats["by_result"].get("compensated") == 1
    assert svc.get(p["id"])["status"] == "failed"
    ai.close()


# ---------- 6) CWA：未登记对象拒绝 ----------

def test_unregistered_object_denied(bridge):
    """未登记为运营对象的合同直接 submit → 拒绝（封闭世界）。"""
    from repository.db import Repository
    with Repository(bridge.db_path) as repo:
        cid = repo.add_contract(contract_no="HT-UNREG-001", title="未登记", amount=1000)
    with pytest.raises(ValueError, match="not registered as operational object"):
        bridge.submit(cid, "sales")


# ---------- 7) CLI 冒烟 ----------

def test_cli_ontology_subcommands(tmp_path):
    """contractctl ontology 子命令真实可跑（register/submit/status）。"""
    cli = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "cli", "contractctl.py")
    db = str(tmp_path / "cli.db")

    def run(*args):
        proc = subprocess.run(
            [sys.executable, cli, "--db", db, *args],
            capture_output=True, text=True, timeout=120,
        )
        # 过滤 ai_kb 导入期的 llama_cpp 提示（stdout 噪音，非 CLI 产物）
        out = "\n".join(
            ln for ln in proc.stdout.splitlines()
            if "Local embedding not available" not in ln
        )
        return proc.returncode, out

    rc, out = run("ontology", "register", "HT-2026-001:100000")
    assert rc == 0, out
    assert "identity 1" in out

    rc, out = run("ontology", "submit", "1", "--operator", "sales")
    assert rc == 0, out
    assert "→ review1" in out

    rc, out = run("ontology", "status", "1")
    assert rc == 0, out
    st = json.loads(out)
    assert st["contract_status"] == "review1"
    assert st["registered"] is True
