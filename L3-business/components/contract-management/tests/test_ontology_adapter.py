"""L2 Function 化适配器单测 — 7 handler 契约验证。

契约：handler(snapshot, params) -> {"ok", "violations", "data?"}
- 合法状态通过（ok=True, violations=[]）
- 非法状态返回 violations（ok=False），绝不抛异常
- 风险报告法条来自受控规则库 CHECK_RULES
- 金额分级边界：99999/100000/500000/2000000
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract_management.ontology_adapter import HANDLERS
from contract_management.risk_engine import CHECK_RULES

def mk_ident(status, amount=50000, key="HT-001"):
    return {
        "id": 1,
        "canonical_key": key,
        "object_type": "contract",
        "system_of_record": "oa",
        "status": "active",
        "metadata": {"status": status, "amount": amount, "contract_no": key},
    }

def snapshot(*idents):
    return {"domain_id": 1, "object_type": "contract", "identities": list(idents)}


class TestStateHandlers(unittest.TestCase):
    def test_submit_legal_draft(self):
        r = HANDLERS["validate_submit_state"](snapshot(mk_ident("draft")), {"target_state": "review1"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["approval_level"], 1)
        self.assertEqual(r["data"]["first_approver"], "销售经理")

    def test_submit_illegal_approved(self):
        r = HANDLERS["validate_submit_state"](snapshot(mk_ident("approved")), {"target_state": "review1"})
        self.assertFalse(r["ok"])
        self.assertTrue(any("illegal_transition" in str(v) for v in r["violations"]))

    def test_submit_illegal_review(self):
        r = HANDLERS["validate_submit_state"](snapshot(mk_ident("review2")), {})
        self.assertFalse(r["ok"])

    def test_approve_legal_review(self):
        for st in ("review1", "review2", "review3"):
            r = HANDLERS["validate_approve_state"](snapshot(mk_ident(st)), {})
            self.assertTrue(r["ok"], st)

    def test_approve_illegal_draft(self):
        r = HANDLERS["validate_approve_state"](snapshot(mk_ident("draft")), {})
        self.assertFalse(r["ok"])

    def test_reject_legal_review(self):
        r = HANDLERS["validate_reject_state"](snapshot(mk_ident("review2")), {})
        self.assertTrue(r["ok"])

    def test_reject_illegal_approved(self):
        r = HANDLERS["validate_reject_state"](snapshot(mk_ident("approved")), {})
        self.assertFalse(r["ok"])

    def test_sign_legal_approved(self):
        r = HANDLERS["validate_sign_state"](snapshot(mk_ident("approved")), {})
        self.assertTrue(r["ok"])

    def test_sign_illegal_review(self):
        r = HANDLERS["validate_sign_state"](snapshot(mk_ident("review1")), {})
        self.assertFalse(r["ok"])

    def test_archive_legal_signed(self):
        r = HANDLERS["validate_archive_state"](snapshot(mk_ident("signed")), {})
        self.assertTrue(r["ok"])

    def test_archive_illegal_approved(self):
        r = HANDLERS["validate_archive_state"](snapshot(mk_ident("approved")), {})
        self.assertFalse(r["ok"])

    def test_missing_status(self):
        r = HANDLERS["validate_submit_state"](
            {"identities": [{"canonical_key": "X", "metadata": {}}]}, {})
        self.assertFalse(r["ok"])
        self.assertTrue(any("missing_status" in str(v) for v in r["violations"]))

    def test_no_identity(self):
        r = HANDLERS["validate_submit_state"]({"identities": []}, {})
        self.assertFalse(r["ok"])

    def test_never_raises_on_illegal(self):
        # 非法输入不炸：状态处理必须返回 dict
        for h in ("validate_submit_state", "validate_approve_state",
                  "validate_reject_state", "validate_sign_state", "validate_archive_state"):
            r = HANDLERS[h](snapshot(mk_ident("archived")), {})
            self.assertIsInstance(r, dict)
            self.assertIn("ok", r)
            self.assertIn("violations", r)


class TestRiskScan(unittest.TestCase):
    def test_structured_report(self):
        text = ("甲方：测试公司\n乙方：客户公司\n服务内容：技术服务\n"
                "违约金按每日1%计算\n人民法院管辖\n验收标准明确")
        r = HANDLERS["risk_scan"](snapshot(mk_ident("draft")), {"text": text})
        self.assertTrue(r["ok"])
        d = r["data"]
        self.assertIn("overall_risk", d)
        self.assertIn("summary", d)
        self.assertEqual(len(d["findings"]), len(CHECK_RULES))
        # JSON 可序列化
        json.dumps(d, ensure_ascii=False)

    def test_citations_controlled(self):
        # 每条 finding 的 law 必须来自受控规则库（不自由生成）
        text = "甲方：测试公司\n乙方：客户公司\n服务内容：技术服务"
        r = HANDLERS["risk_scan"](snapshot(mk_ident("draft")), {"text": text})
        laws = {f["law"] for f in r["data"]["findings"]}
        controlled = {rule.law for rule in CHECK_RULES}
        self.assertTrue(laws <= controlled, f"不受控法条: {laws - controlled}")

    def test_empty_text(self):
        r = HANDLERS["risk_scan"](snapshot(mk_ident("draft")), {"text": "  "})
        self.assertFalse(r["ok"])


class TestComputeHandlers(unittest.TestCase):
    SAMPLE = (
        "技术服务合同\n\n甲方：北京示例科技有限公司\n地址：北京市朝阳区示例路1号\n"
        "联系电话：010-12345678\n乙方：上海客户有限公司\n地址：上海市浦东新区客户大道2号\n"
        "联系电话：021-87654321\n\n第一条 服务内容\n甲方委托乙方提供技术服务。\n\n"
        "第二条 价款与报酬\n本合同金额为人民币壹佰万元整，含税，银行转账支付。\n\n"
        "第三条 服务期限\n自2026年1月1日至2026年12月31日。\n\n第四条 验收标准\n"
        "验收标准以双方确认的技术方案为准。\n\n第五条 违约责任\n按合同金额的5%支付违约金。\n\n"
        "第六条 争议解决\n提交北京市朝阳区人民法院管辖。\n\n第七条 知识产权\n成果归甲方所有。\n\n"
        "第八条 保密条款\n双方对合同内容保密。\n\n第九条 不可抗力\n不可抗力免责。\n\n"
        "第十条 合同生效\n自双方签字盖章之日起生效。"
    )

    def test_parse_contract_text(self):
        r = HANDLERS["parse_contract_text"](snapshot(mk_ident("draft")), {"text": self.SAMPLE})
        self.assertTrue(r["ok"])
        d = r["data"]
        self.assertIn("clauses", d)
        self.assertTrue(len(d["clauses"]) > 0)
        json.dumps(d, ensure_ascii=False)

    def test_parse_empty_text(self):
        r = HANDLERS["parse_contract_text"](snapshot(mk_ident("draft")), {"text": ""})
        self.assertFalse(r["ok"])

    def test_audit_contract_text(self):
        r = HANDLERS["audit_contract_text"](snapshot(mk_ident("draft")), {"text": self.SAMPLE})
        self.assertTrue(r["ok"])
        d = r["data"]
        self.assertIn("overall_risk", d)
        self.assertIn("summary", d)
        self.assertEqual(d["summary"]["total"], 43)  # 43 项审核标准
        json.dumps(d, ensure_ascii=False)

    def test_audit_empty_text(self):
        r = HANDLERS["audit_contract_text"](snapshot(mk_ident("draft")), {"text": " "})
        self.assertFalse(r["ok"])


class TestApprovalLevel(unittest.TestCase):
    def test_boundaries(self):
        for amount, lvl in ((99999, 1), (100000, 2), (500000, 3), (2000000, 4)):
            r = HANDLERS["approval_level"](snapshot(mk_ident("draft")), {"amount": amount})
            self.assertTrue(r["ok"], amount)
            self.assertEqual(r["data"]["level"], lvl, amount)

    def test_invalid_amount(self):
        r = HANDLERS["approval_level"](snapshot(mk_ident("draft")), {"amount": "abc"})
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
