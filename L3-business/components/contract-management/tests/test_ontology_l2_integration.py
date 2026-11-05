"""L3 → L2 运营本体集成测试：装配 + submit_contract 五态闭环。

依据 DESIGN-DETAIL-contract-management-v1.0 §7.3：
- 通过装配脚本注册 domain=bangcle-contract + 7 function + 3 action type；
- 用 ProposalService（NullConnector）驱动 submit_contract：
  propose_action → validate → review(auto) → commit；
- 断言：五态闭环（pending→validated→committed）、validated≠committed、
  决策记录存在且 evidence 完整、幂等不重放。
"""
import json
import os
import sys
import tempfile
import unittest

COMPONENT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_WORKSPACE = os.path.abspath(os.path.join(COMPONENT_ROOT, "..", "..", ".."))
_L2_ROOT = os.path.join(_WORKSPACE, "L2-infra", "components", "ai-knowledge-base")

for p in (COMPONENT_ROOT, _L2_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from ai_kb.db import AIKB
from ai_kb.ontology import IdentityService, ProposalService
from ai_kb.ontology.connectors.base import NullConnector

from scripts.register_ontology_functions import (
    DOMAIN_CODE, register_all,
)

DOMAIN = DOMAIN_CODE


class TestL2Integration(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.summary = register_all(self.db_path)
        self.db = AIKB(self.db_path)

    def tearDown(self):
        self.db.close()
        os.unlink(self.db_path)

    # --- 装配 ---
    def test_assembly_registers_all(self):
        self.assertEqual(len(self.summary["functions"]), 9)
        self.assertEqual(len(self.summary["actions"]), 3)
        self.assertEqual(len(self.summary["bindings"]), 3)
        # 每个 action 的 precondition 绑定都存在
        for b in self.summary["bindings"]:
            self.assertTrue(b["refs"], f"action {b['action']} has no refs")

    def test_assembly_idempotent(self):
        s2 = register_all(self.db_path)
        # 第二次全部 skipped(dup)，总数不变
        self.assertTrue(all(x.startswith("skipped") for x in s2["functions"]))
        self.assertTrue(all(x.startswith("skipped") for x in s2["actions"]))
        self.assertEqual(len(s2["functions"]), 9)
        self.assertEqual(len(s2["actions"]), 3)

    def test_assembly_registers_deterministic(self):
        reg = _registry(self.db)
        for name, kind in (
            ("validate_submit_state", "rule"),
            ("validate_approve_state", "rule"),
            ("validate_reject_state", "rule"),
            ("validate_sign_state", "rule"),
            ("validate_archive_state", "rule"),
            ("risk_scan", "risk"),
            ("approval_level", "compute"),
            ("parse_contract_text", "compute"),
            ("audit_contract_text", "compute"),
        ):
            fn = reg.get_function(DOMAIN, name)
            self.assertIsNotNone(fn, name)
            self.assertEqual(int(fn["deterministic"]), 1, name)
            self.assertEqual(fn["kind"], kind, name)

    # --- 五态闭环 ---
    def test_submit_contract_full_loop(self):
        reg = _registry(self.db)
        ids = IdentityService(self.db)
        cid = ids.register_identity(DOMAIN, "contract", "HT-001", "oa", "Contract 1")
        self.db.execute(
            "UPDATE ont_identity SET metadata = ? WHERE id = ?",
            (json.dumps({"status": "draft", "amount": 80000}), cid),
        )
        self.db.commit()

        ps = ProposalService(self.db, reg, default_connector=NullConnector())

        # 1) propose → pending（validated≠committed 不变量第一步）
        p = ps.propose_action(
            DOMAIN, "submit_contract", ["HT-001"],
            {"contract_no": "HT-001", "target_state": "review1", "amount": 80000},
            caller_id="agent-1", caller_kind="agent",
            rationale="submit for approval", idempotency_key="L3-IT-1",
        )
        self.assertEqual(p["status"], "pending")
        # propose 零写：对象 metadata 未被业务字段修改
        md = json.loads(self.db.execute(
            "SELECT metadata FROM ont_identity WHERE id = ?", (cid,)
        ).fetchone()[0])
        self.assertEqual(md["status"], "draft")

        # 2) validate → validated；状态机校验通过（draft 可 submit）
        r = ps.validate(p["id"])
        self.assertTrue(r["ok"], r.get("violations"))
        self.assertEqual(r["status"], "validated")
        p2 = ps.get(p["id"])
        self.assertEqual(p2["status"], "validated")

        # validated ≠ committed：对象状态仍未变
        md = json.loads(self.db.execute(
            "SELECT metadata FROM ont_identity WHERE id = ?", (cid,)
        ).fetchone()[0])
        self.assertEqual(md["status"], "draft")

        # 3) review(auto 审批) → 内部 commit
        out = ps.review(p["id"], "approve", "auto-gate",
                        reviewer_kind="agent", auto_commit=True)
        self.assertEqual(out["status"], "committed")

        # 4) 决策记录存在，evidence 含 connector
        rec = out["decision_record"]
        self.assertEqual(rec["result"], "allowed")
        ev = rec["evidence"] if isinstance(rec["evidence"], dict) else json.loads(rec["evidence"])
        self.assertEqual(ev["connector"], "null")
        self.assertIn("validation_result", ev)

        # 5) 对象 metadata 记录 applied_changes（change_set 可回放）
        md = json.loads(self.db.execute(
            "SELECT metadata FROM ont_identity WHERE id = ?", (cid,)
        ).fetchone()[0])
        self.assertEqual(md["status"], "draft")  # 业务状态由 L4 写；L2 只记变更集
        self.assertTrue(md.get("applied_changes"), "no applied_changes recorded")

        # 6) 幂等：同 idempotency_key 不重放
        p3 = ps.propose_action(
            DOMAIN, "submit_contract", ["HT-001"],
            {"contract_no": "HT-001", "target_state": "review1", "amount": 80000},
            caller_id="agent-1", caller_kind="agent",
            rationale="dup", idempotency_key="L3-IT-1",
        )
        self.assertTrue(p3.get("idempotent_replay"))

    def test_submit_contract_illegal_state_rejected(self):
        """已提交（review1）再 submit → validate 必须 violations。"""
        reg = _registry(self.db)
        ids = IdentityService(self.db)
        cid = ids.register_identity(DOMAIN, "contract", "HT-002", "oa", "Contract 2")
        self.db.execute(
            "UPDATE ont_identity SET metadata = ? WHERE id = ?",
            (json.dumps({"status": "review1", "amount": 80000}), cid),
        )
        self.db.commit()

        ps = ProposalService(self.db, reg, default_connector=NullConnector())
        p = ps.propose_action(
            DOMAIN, "submit_contract", ["HT-002"],
            {"contract_no": "HT-002", "target_state": "review1", "amount": 80000},
            caller_id="agent-2", caller_kind="agent", rationale="bad submit",
        )
        r = ps.validate(p["id"])
        self.assertFalse(r["ok"])
        # 状态不迁移到 validated（仍是 pending）
        self.assertEqual(ps.get(p["id"])["status"], "pending")
        # commit 必须被拒（validated≠committed 反向：未 validated 不能 commit）
        with self.assertRaises(ValueError):
            ps.commit(p["id"])


def _registry(db):
    from ai_kb.ontology import ActionRegistry, AssemblyGate
    gate = AssemblyGate()
    gate.open()
    return ActionRegistry(db, gate=gate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
