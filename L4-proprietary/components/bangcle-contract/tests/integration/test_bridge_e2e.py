"""P2 集成测试：Ontology Bridge 全生命周期真实 SQLite 走查。

覆盖（DESIGN §4 / §6）：
- 4 级合同（300 万）create → submit → approve×4 → sign → archive
- 3 级合同（80 万）submit → approve×3
- 迁移幂等 ×3
- 黄金映射集成（card_golden.json main_fields 落库逐字段比对）
"""

import json
import os
import sqlite3

import pytest

from repository.db import init_db
from services.contract_service import (
    apply_action,
    create_contract_from_card,
    get_contract,
)

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "fixtures")


def _card(no: str, amount_text: str):
    return {
        "合同编号": no,
        "合同名称": f"集成测试合同 {no}",
        "合同类型": "tech_service",
        "甲方": "北京梆梆安全科技有限公司",
        "乙方": "北京云动网络科技有限公司",
        "合同金额": amount_text,
        "生效日期": "2026-11-01",
        "到期日期": "2027-10-31",
    }


# ---------- 4 级合同全生命周期（300 万） ----------

def test_full_lifecycle_four_level(tmp_path):
    db_path = str(tmp_path / "e2e4.db")
    contract = create_contract_from_card(_card("E2E-4-001", "¥3,000,000"), db_path=db_path)
    cid = contract.id
    # L3 DEFAULT_APPROVAL_LEVELS 4 级档仅列 3 个角色：review1 首角色
    # VP/CEO，之后依次 法务总监/财务总监，进入 review4 时 next_role=None。
    approver_roles = ["VP/CEO", "法务总监", "财务总监", "VP/CEO"]
    next_roles = {1: "法务总监", 2: "财务总监", 3: None}

    detail = get_contract(cid, db_path=db_path)
    assert detail["status"] == "draft"
    assert len(detail["approval_instances"]) == 0

    # submit
    r = apply_action(cid, "submit", operator="sales", db_path=db_path)
    assert r["next_status"] == "review1"
    assert r["next_approver_role"] == "VP/CEO"
    assert r["total_steps"] == 4
    detail = get_contract(cid, db_path=db_path)
    assert detail["status"] == "review1"
    assert detail["current_approver"] == "VP/CEO"
    assert [a["action"] for a in detail["audit_logs"]] == ["create", "submit"]

    # approve ×4：前三次进入下一级，第四次到 approved
    for step in range(1, 5):
        r = apply_action(
            cid, "approve",
            operator=f"boss{step}", approver_role=approver_roles[step - 1],
            comment=f"同意 step{step}",
            db_path=db_path,
        )
        detail = get_contract(cid, db_path=db_path)
        instances = detail["approval_instances"]
        assert len(instances) == step
        assert instances[-1]["action"] == "approve"
        assert instances[-1]["level"] == step
        assert instances[-1]["approver_name"] == f"boss{step}"
        audits = detail["audit_logs"]
        assert audits[-1]["action"] == "approve"
        payload = json.loads(audits[-1]["detail"])
        assert payload["from_status"] == f"review{step}"
        if step < 4:
            assert r["next_status"] == f"review{step + 1}"
            assert r["next_approver_role"] == next_roles[step]
            assert detail["status"] == f"review{step + 1}"
            assert detail["current_approver"] == next_roles[step]
        else:
            assert r["next_status"] == "approved"
            assert detail["status"] == "approved"
            assert detail["current_approver"] is None

    # sign
    r = apply_action(cid, "sign", operator="legal", db_path=db_path)
    assert r["next_status"] == "signed"
    detail = get_contract(cid, db_path=db_path)
    assert detail["status"] == "signed"
    assert detail["audit_logs"][-1]["action"] == "sign"
    # sign 不产生审批实例
    assert len(detail["approval_instances"]) == 4

    # archive
    r = apply_action(cid, "archive", operator="legal", db_path=db_path)
    assert r["next_status"] == "archived"
    detail = get_contract(cid, db_path=db_path)
    assert detail["status"] == "archived"
    assert detail["audit_logs"][-1]["action"] == "archive"
    assert len(detail["approval_instances"]) == 4


# ---------- 3 级合同路径（80 万） ----------

def test_three_level_path(tmp_path):
    db_path = str(tmp_path / "e2e3.db")
    contract = create_contract_from_card(_card("E2E-3-001", "¥800,000"), db_path=db_path)
    cid = contract.id
    roles = ["销售总监", "法务审查员", "财务经理"]

    r = apply_action(cid, "submit", operator="sales", db_path=db_path)
    assert r["total_steps"] == 3
    assert r["next_approver_role"] == "销售总监"

    for step in range(1, 4):
        r = apply_action(
            cid, "approve",
            operator=f"mgr{step}", approver_role=roles[step - 1], comment="ok",
            db_path=db_path,
        )
        detail = get_contract(cid, db_path=db_path)
        assert len(detail["approval_instances"]) == step
        if step < 3:
            assert r["next_status"] == f"review{step + 1}"
            assert detail["current_approver"] == roles[step]
        else:
            assert r["next_status"] == "approved"

    assert get_contract(cid, db_path=db_path)["status"] == "approved"


# ---------- reject 后可重提（集成） ----------

def test_reject_then_resubmit(tmp_path):
    db_path = str(tmp_path / "e2er.db")
    contract = create_contract_from_card(_card("E2E-R-001", "¥800,000"), db_path=db_path)
    cid = contract.id
    apply_action(cid, "submit", operator="sales", db_path=db_path)
    r = apply_action(cid, "reject", operator="mgr1",
                     approver_role="销售总监", comment="退回修改", db_path=db_path)
    assert r["next_status"] == "draft"

    r = apply_action(cid, "submit", operator="sales", db_path=db_path)
    assert r["next_status"] == "review1"
    detail = get_contract(cid, db_path=db_path)
    actions = [a["action"] for a in detail["audit_logs"]]
    assert actions == ["create", "submit", "reject", "submit"]
    assert len(detail["approval_instances"]) == 1


# ---------- 迁移幂等 ×3 ----------

def test_migration_idempotent_three_times(tmp_path):
    db_path = str(tmp_path / "e2em.db")
    snapshots = []
    for _ in range(3):
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        ddl = conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        conn.close()
        snapshots.append(ddl)
    assert snapshots[0] == snapshots[1] == snapshots[2]

    # 既有 reviews 三表仍在，V2 两表 + 索引齐全
    names = {row[1] for row in snapshots[0]}
    assert {
        "reviews", "kb_matches", "audit_logs",
        "contracts", "approval_instances",
        "uq_contracts_oa_billid", "ix_approval_instances_contract_id",
    } <= names

    # 迁移后既有域仍可写
    from repository.db import Repository
    with Repository(db_path) as repo:
        rid = repo.add_review("REF-1", "upload", "low", "full")
        assert repo.get_review(rid)["contract_ref"] == "REF-1"


# ---------- 黄金映射集成 ----------

def test_golden_card_persisted(tmp_path):
    fixture_path = os.path.join(FIXTURE_DIR, "card_golden.json")
    with open(fixture_path, encoding="utf-8") as fh:
        golden = json.load(fh)

    db_path = str(tmp_path / "golden.db")
    contract = create_contract_from_card(golden["main_fields"], db_path=db_path)
    detail = get_contract(contract.id, db_path=db_path)
    expected = golden["expected_contract"]

    for key in (
        "contract_no", "title", "contract_type",
        "party_a", "party_b", "effective_date", "expiry_date",
    ):
        assert detail[key] == expected[key], key
    assert detail["amount"] == expected["amount"] == 125000.0
    assert detail["status"] == "draft" == expected["status"]
