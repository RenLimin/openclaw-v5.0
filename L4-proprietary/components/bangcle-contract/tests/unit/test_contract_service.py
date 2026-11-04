"""P2 单元测试：contract_service 持久化 + L3 状态机接线。

全部使用 tmp_path 临时 DB，不碰真实 data/bangcle_contract.db。
"""

import json
import os

import pytest

from repository.db import Repository, init_db
from services.contract_service import (
    ContractStateError,
    apply_action,
    create_contract_from_card,
    get_contract,
    list_contracts,
)

CARD_FIELDS = {
    "合同编号": "XSZS-2026-T1",
    "合同名称": "单元测试技术服务合同",
    "合同类型": "tech_service",
    "甲方": "梆梆安全",
    "乙方": "供应商甲",
    "合同金额": "¥300,000",
    "生效日期": "2026-11-01",
    "到期日期": "2027-10-31",
}


def _count(db_path, table, where="", params=()):
    import sqlite3

    conn = sqlite3.connect(db_path)
    n = conn.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0]
    conn.close()
    return n


# ---------- create 闭环 ----------

def test_create_contract_from_card(tmp_path):
    db_path = str(tmp_path / "c.db")
    contract = create_contract_from_card(CARD_FIELDS, db_path=db_path)

    assert contract.id is not None and contract.id > 0
    assert contract.status == "draft"
    assert contract.amount == 300_000.0
    assert contract.contract_no == "XSZS-2026-T1"

    detail = get_contract(contract.id, db_path=db_path)
    assert detail["status"] == "draft"
    assert detail["amount"] == 300_000.0

    audits = detail["audit_logs"]
    assert len(audits) == 1
    assert audits[0]["action"] == "create"
    assert audits[0]["operator"] == "system"
    assert audits[0]["review_id"] is None
    detail_payload = json.loads(audits[0]["detail"])
    assert detail_payload["contract_id"] == contract.id


def test_list_contracts_filter(tmp_path):
    db_path = str(tmp_path / "c.db")
    c1 = create_contract_from_card(CARD_FIELDS, db_path=db_path)
    c2 = create_contract_from_card(
        {**CARD_FIELDS, "合同编号": "XSZS-2026-T2"}, db_path=db_path
    )
    apply_action(c1.id, "submit", operator="alice", db_path=db_path)

    drafts = list_contracts("draft", db_path=db_path)
    assert [c["id"] for c in drafts] == [c2.id]

    all_rows = list_contracts(db_path=db_path)
    assert [c["id"] for c in all_rows] == [c1.id, c2.id]


# ---------- submit ----------

def test_apply_action_submit(tmp_path):
    db_path = str(tmp_path / "c.db")
    contract = create_contract_from_card(CARD_FIELDS, db_path=db_path)

    result = apply_action(contract.id, "submit", operator="alice", db_path=db_path)
    assert result["next_status"] == "review1"
    assert result["next_approver_role"] == "销售经理"  # 30 万落在 2 级档
    assert result["total_steps"] == 2

    detail = get_contract(contract.id, db_path=db_path)
    assert detail["status"] == "review1"
    assert detail["current_approver"] == "销售经理"
    assert len(detail["approval_instances"]) == 0  # submit 不落审批实例
    assert [a["action"] for a in detail["audit_logs"]] == ["create", "submit"]


# ---------- 非法动作：原子回滚 ----------

def test_invalid_action_approve_on_draft_atomic(tmp_path):
    db_path = str(tmp_path / "c.db")
    contract = create_contract_from_card(CARD_FIELDS, db_path=db_path)

    before = {
        "contracts": _count(db_path, "contracts"),
        "approval_instances": _count(db_path, "approval_instances"),
        "audit_logs": _count(db_path, "audit_logs"),
    }

    with pytest.raises(ContractStateError):
        apply_action(
            contract.id, "approve",
            operator="bob", approver_role="销售总监",
            db_path=db_path,
        )

    detail = get_contract(contract.id, db_path=db_path)
    assert detail["status"] == "draft"
    assert detail["current_approver"] is None
    assert len(detail["approval_instances"]) == 0
    assert [a["action"] for a in detail["audit_logs"]] == ["create"]

    assert _count(db_path, "contracts") == before["contracts"]
    assert _count(db_path, "approval_instances") == before["approval_instances"]
    assert _count(db_path, "audit_logs") == before["audit_logs"]


def test_invalid_action_archive_on_approved_atomic(tmp_path):
    db_path = str(tmp_path / "c.db")
    contract = create_contract_from_card(CARD_FIELDS, db_path=db_path)
    # 走到 approved（3 级合同）
    apply_action(contract.id, "submit", operator="alice", db_path=db_path)
    roles = ["销售经理", "法务审查员"]
    for role in roles:
        apply_action(
            contract.id, "approve",
            operator=role, approver_role=role, comment="ok",
            db_path=db_path,
        )
    assert get_contract(contract.id, db_path=db_path)["status"] == "approved"

    audit_count = _count(db_path, "audit_logs")
    with pytest.raises(ContractStateError):
        apply_action(contract.id, "archive", operator="alice", db_path=db_path)

    assert get_contract(contract.id, db_path=db_path)["status"] == "approved"
    assert _count(db_path, "audit_logs") == audit_count


def test_unknown_action_raises(tmp_path):
    db_path = str(tmp_path / "c.db")
    contract = create_contract_from_card(CARD_FIELDS, db_path=db_path)
    with pytest.raises(ContractStateError):
        apply_action(contract.id, "explode", operator="alice", db_path=db_path)


def test_missing_contract_raises(tmp_path):
    db_path = str(tmp_path / "c.db")
    init_db(db_path)
    with pytest.raises(ContractStateError):
        apply_action(999, "submit", operator="alice", db_path=db_path)


# ---------- reject 路径 + 审批实例落行 ----------

def test_reject_returns_draft_and_persists_instance(tmp_path):
    db_path = str(tmp_path / "c.db")
    contract = create_contract_from_card(CARD_FIELDS, db_path=db_path)
    apply_action(contract.id, "submit", operator="alice", db_path=db_path)

    result = apply_action(
        contract.id, "reject",
        operator="bob", approver_role="销售经理", comment="材料不全",
        db_path=db_path,
    )
    assert result["next_status"] == "draft"
    assert result["rejected_at_level"] == 1

    detail = get_contract(contract.id, db_path=db_path)
    assert detail["status"] == "draft"
    assert detail["current_approver"] is None
    instances = detail["approval_instances"]
    assert len(instances) == 1
    inst = instances[0]
    assert inst["action"] == "reject"
    assert inst["level"] == 1
    assert inst["approver_role"] == "销售经理"
    assert inst["approver_name"] == "bob"
    assert inst["comment"] == "材料不全"
    assert inst["created_at"]


# ---------- oa_billid 唯一索引 ----------

def test_duplicate_oa_billid_rejected(tmp_path):
    db_path = str(tmp_path / "c.db")
    init_db(db_path)
    with Repository(db_path) as repo:
        repo.add_contract(contract_no="A", oa_billid="bill-1")
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            repo.add_contract(contract_no="B", oa_billid="bill-1")

    # 可空 oa_billid 互不冲突
    with Repository(db_path) as repo:
        repo.add_contract(contract_no="C")
        repo.add_contract(contract_no="D")
    assert _count(db_path, "contracts") == 3


# ---------- 审计 append-only 接口断言 ----------

def test_audit_logs_append_only_interface(tmp_path):
    db_path = str(tmp_path / "c.db")
    repo = Repository(db_path)
    names = dir(repo)
    forbidden = [
        n for n in names
        if ("audit" in n.lower())
        and (n.startswith("update") or n.startswith("delete") or n.startswith("remove"))
    ]
    assert forbidden == [], f"出现非 append-only 审计方法: {forbidden}"
    assert "append_audit_log" in names


# ---------- 迁移幂等 ×3 ----------

def test_init_db_idempotent_three_times(tmp_path):
    db_path = str(tmp_path / "c.db")
    signatures = []
    for _ in range(3):
        init_db(db_path)
        import sqlite3

        conn = sqlite3.connect(db_path)
        objects = conn.execute(
            "SELECT type, name, tbl_name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        conn.close()
        signatures.append(objects)

    assert signatures[0] == signatures[1] == signatures[2]
    # 唯一索引存在
    names = {row[1] for row in signatures[0]}
    assert "uq_contracts_oa_billid" in names


# ---------- 幂等 ×3：同输入连跑结果一致（新建各自新库） ----------

def test_same_input_three_runs_consistent(tmp_path):
    results = []
    for i in range(3):
        db_path = str(tmp_path / f"r{i}.db")
        contract = create_contract_from_card(CARD_FIELDS, db_path=db_path)
        snapshot = get_contract(contract.id, db_path=db_path)
        results.append({
            "contract_no": snapshot["contract_no"],
            "amount": snapshot["amount"],
            "status": snapshot["status"],
            "audit_actions": [a["action"] for a in snapshot["audit_logs"]],
        })
    assert results[0] == results[1] == results[2]
