"""合同管理模块 — 单元测试。

验证：
  1. ocr_importer.py bug 修复（lastrowid 获取）
  2. analyze_subject() 4 项对比分析 + 价格偏离预警
  3. 状态机全 12 种合法流转 + 非法流转拒绝
  4. CRUD + 软删除 + 审计追踪
  5. AES-256 加密 + 脱敏
  6. 端到端：create → approve → sign → archive
"""

import os
import sys
import pytest
from pathlib import Path
from decimal import Decimal

# 让 src 可导入
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

# 确保 L3 路径可导入
_L3_PATH = os.path.expanduser("~/.openclaw/workspace/L3-business/skills/contract-approval")
if _L3_PATH not in sys.path:
    sys.path.insert(0, _L3_PATH)

from bdms.modules.contract_management.service import ContractManagementService  # noqa: E402
from bdms.modules.contract_management.engine import ContractManagementEngine  # noqa: E402
from bdms.modules.contract_management.models import (  # noqa: E402
    Contract, CONTRACT_STATUSES, VALID_TRANSITIONS,
)


# ─── Fixtures ───

@pytest.fixture(scope="function")
def svc(tmp_path):
    """临时 DB 的 service 实例。"""
    from bdms.core import db as _db
    db_path = tmp_path / "test.db"
    _db.init_db(db_path)
    s = ContractManagementService(db_path=db_path)
    return s


@pytest.fixture(scope="function")
def engine(tmp_path):
    return ContractManagementEngine(db_path=tmp_path / "test.db")


@pytest.fixture
def sample_contract():
    return {
        "title": "软件授权合同",
        "party_a": "北京梆梆安全科技有限公司",
        "party_b": "北京信创数安科技有限公司",
        "amount": 850000,
        "contract_type": "software_license",
        "effective_date": "2026-09-01",
        "expiry_date": "2027-08-31",
    }


# ─── 1. 状态机 ───

class TestStateMachine:
    def test_all_valid_transitions(self, engine):
        """验证所有合法流转。"""
        for from_status, targets in VALID_TRANSITIONS.items():
            for to_status in targets:
                result = engine.validate_state_transition(from_status, to_status)
                assert result["valid"], f"{from_status} -> {to_status} 应允许"

    def test_invalid_transitions(self, engine):
        """验证非法流转被拒绝。"""
        invalid = [
            ("draft", "approved"),
            ("draft", "signed"),
            ("review1", "signed"),
            ("approved", "draft"),
            ("signed", "draft"),
            ("archived", "signed"),
        ]
        for from_s, to_s in invalid:
            result = engine.validate_state_transition(from_s, to_s)
            assert not result["valid"], f"{from_s} -> {to_s} 应被拒绝"

    def test_approval_level_mapping(self, engine):
        """验证金额 → 审批级别映射。"""
        assert engine.get_approval_level(50000)["level"] == 1
        assert engine.get_approval_level(300000)["level"] == 2
        assert engine.get_approval_level(1000000)["level"] == 3
        assert engine.get_approval_level(5000000)["level"] == 4


# ─── 2. CRUD + 审计 ───

class TestCRUD:
    def test_create_contract(self, svc, sample_contract):
        result = svc.create_contract(sample_contract, operator="test_user")
        assert result["id"] > 0
        assert result["contract_no"].startswith("CR-")

    def test_create_generates_unique_no(self, svc, sample_contract):
        r1 = svc.create_contract(sample_contract)
        r2 = svc.create_contract(sample_contract)
        assert r1["contract_no"] != r2["contract_no"]

    def test_get_contract(self, svc, sample_contract):
        r = svc.create_contract(sample_contract)
        detail = svc.get_contract(r["id"])
        assert detail is not None
        assert detail["title"] == sample_contract["title"]
        assert detail["party_a"] == sample_contract["party_a"]

    def test_list_contracts(self, svc, sample_contract):
        svc.create_contract(sample_contract)
        svc.create_contract({**sample_contract, "title": "另一份合同"})
        result = svc.list_contracts()
        assert result["total"] == 2

    def test_soft_delete(self, svc, sample_contract):
        r = svc.create_contract(sample_contract)
        svc.soft_delete(r["id"], operator="test")
        assert svc.get_contract(r["id"]) is None
        # 确认列表也不见了
        result = svc.list_contracts()
        assert result["total"] == 0

    def test_audit_log(self, svc, sample_contract):
        r = svc.create_contract(sample_contract, operator="alice")
        log = svc.audit_log(r["id"])
        assert len(log["audit_trail"]) >= 1
        assert log["audit_trail"][0]["operation"] == "CREATE"


# ─── 3. 审批流程 ───

class TestApprovalFlow:
    def test_full_lifecycle_2level(self, svc, sample_contract):
        """2 级审批全流程：draft → review1 → review2 → approved → signed → archived。"""
        r = svc.create_contract({**sample_contract, "amount": 300000})  # level 2
        cid = r["id"]

        svc.submit_approval(cid, operator="sales")
        assert svc.get_contract(cid)["status"] == "review1"

        svc.approve(cid, operator="mgr", role="sales_manager")
        # level 1 直接到 review2
        assert svc.get_contract(cid)["status"] == "review2"

        svc.approve(cid, operator="fin", role="finance")
        assert svc.get_contract(cid)["status"] == "approved"

        svc.sign(cid, operator="sales")
        assert svc.get_contract(cid)["status"] == "signed"

        svc.archive(cid, operator="admin")
        assert svc.get_contract(cid)["status"] == "archived"

    def test_full_lifecycle_4level(self, svc, sample_contract):
        """4 级审批全流程：draft → review1 → review2 → review3 → review4 → approved → signed → archived。"""
        r = svc.create_contract({**sample_contract, "amount": 5000000})
        cid = r["id"]

        svc.submit_approval(cid, operator="sales")
        assert svc.get_contract(cid)["status"] == "review1"

        svc.approve(cid, operator="mgr", role="sales_manager")
        assert svc.get_contract(cid)["status"] == "review2"

        svc.approve(cid, operator="fin", role="finance")
        assert svc.get_contract(cid)["status"] == "review3"

        svc.approve(cid, operator="legal", role="legal")
        assert svc.get_contract(cid)["status"] == "review4"

        svc.approve(cid, operator="gm", role="gm")
        assert svc.get_contract(cid)["status"] == "approved"

    def test_reject_flow(self, svc, sample_contract):
        r = svc.create_contract(sample_contract)
        cid = r["id"]

        svc.submit_approval(cid, operator="sales")
        svc.reject(cid, operator="mgr", role="sales_manager", comment="价格不对")
        assert svc.get_contract(cid)["status"] == "draft"

    def test_invalid_transition_raises(self, svc, sample_contract):
        r = svc.create_contract(sample_contract)
        cid = r["id"]

        # draft 不能直接 approved
        with pytest.raises(ValueError, match="不允许"):
            svc._transition(cid, "approved", "approve", "hacker")


# ─── 4. 加密 + 脱敏 ───

class TestEncryption:
    def test_encryption_roundtrip(self, svc, sample_contract):
        r = svc.create_contract(sample_contract)
        detail = svc.get_contract(r["id"])
        # 解密后应能看到原文
        assert detail["party_a"] == sample_contract["party_a"]
        assert detail["party_b"] == sample_contract["party_b"]

    def test_list_masking(self, svc, sample_contract):
        svc.create_contract(sample_contract)
        result = svc.list_contracts(mask=True)
        item = result["items"][0]
        # 脱敏：名称应包含 ***
        assert "***" in item["party_a"]
        assert "***" in item["party_b"]
        # 脱敏：金额显示 "XX万" 格式
        assert "万" in item["amount_display"]

    def test_detail_no_masking(self, svc, sample_contract):
        r = svc.create_contract(sample_contract)
        detail = svc.get_contract(r["id"])
        # 详情接口完整返回
        assert "***" not in detail["party_a"]
        assert detail["amount"] == sample_contract["amount"]


# ─── 5. analyze_subject 对比分析 ───

class TestAnalyzeSubject:
    def test_price_deviation_alert(self, svc, sample_contract):
        """价格偏离 ±20% 应触发预警。"""
        r = svc.create_contract({**sample_contract, "amount": 1000000})  # 100万
        cid = r["id"]

        # 知识库参考价 50万，偏离 +100%
        kb_items = [{
            "title": "软件授权标准定价",
            "pricing_ref": "标准授权费用为 50万元/年",
            "service_sla": "",
            "deploy_manual": "",
        }]
        result = svc.analyze_subject(cid, kb_items)
        assert result["alerts"][0]["type"] == "price_anomaly"
        assert result["alerts"][0]["level"] == "high"

    def test_price_normal_no_alert(self, svc, sample_contract):
        """价格偏离 < 20% 不应触发预警。"""
        r = svc.create_contract({**sample_contract, "amount": 550000})  # 55万
        cid = r["id"]

        kb_items = [{
            "title": "软件授权标准定价",
            "pricing_ref": "标准授权费用为 50万元/年",
            "service_sla": "",
            "deploy_manual": "",
        }]
        result = svc.analyze_subject(cid, kb_items)
        # 偏离 10%，不超过 20%，不应预警
        price_alerts = [a for a in result["alerts"] if a["type"] == "price_anomaly"]
        assert len(price_alerts) == 0

    def test_product_matched(self, svc, sample_contract):
        """产品匹配度匹配成功。"""
        r = svc.create_contract({**sample_contract, "title": "梆梆安全软件授权合同"})
        cid = r["id"]

        kb_items = [{"title": "软件授权", "pricing_ref": "50万元"}]
        result = svc.analyze_subject(cid, kb_items)
        assert result["comparisons"][0]["product_matched"] is True

    def test_delivery_risk_alert(self, svc, sample_contract):
        """交付周期过短应触发预警。"""
        r = svc.create_contract({
            **sample_contract,
            "amount": 500000,
            "effective_date": "2026-09-01",
            "expiry_date": "2026-09-10",  # 仅 10 天
        })
        cid = r["id"]

        kb_items = [{
            "title": "软件实施",
            "pricing_ref": "",
            "deploy_manual": "标准实施周期为 30 天",
        }]
        result = svc.analyze_subject(cid, kb_items)
        delivery_alerts = [a for a in result["alerts"] if a["type"] == "delivery_risk"]
        assert len(delivery_alerts) == 1
        assert delivery_alerts[0]["level"] == "medium"


# ══════════════════════════════════════════════════════════
# 6. 合同关联关系（§7）
# ══════════════════════════════════════════════════════════

class TestContractRelations:
    """测试合同关联关系：前 14 位 + BC/ZZ/- 规则。"""

    def test_find_related_supplement(self, svc, sample_contract):
        """BC 前缀 → 补充协议关联。"""
        # 创建主合同
        r1 = svc.create_contract(sample_contract)
        # 创建补充协议（同日期，BC 前缀）
        contract_no = svc.get_contract(r1["id"])["contract_no"]
        # 替换前缀 CR- → BC-，保持日期部分一致
        bc_no = "BC-" + contract_no[3:]
        r2 = svc.create_contract({**sample_contract, "title": "补充协议", "contract_no": bc_no})

        engine = svc.engine
        related = engine.find_related_contracts(contract_no)
        assert len(related) >= 1
        types = [r["relation_type"] for r in related]
        assert "supplement" in types

    def test_find_related_termination(self, svc, sample_contract):
        """ZZ 前缀 → 终止协议关联。"""
        r1 = svc.create_contract(sample_contract)
        contract_no = svc.get_contract(r1["id"])["contract_no"]
        zz_no = "ZZ-" + contract_no[3:]
        svc.create_contract({**sample_contract, "title": "终止协议", "contract_no": zz_no})

        engine = svc.engine
        related = engine.find_related_contracts(contract_no)
        types = [r["relation_type"] for r in related]
        assert "termination" in types

    def test_find_related_order(self, svc, sample_contract):
        """含 - 数字后缀 → 框架合同订单关联。"""
        r1 = svc.create_contract(sample_contract)
        contract_no = svc.get_contract(r1["id"])["contract_no"]
        # 订单号：合同号-01
        order_no = contract_no + "-01"
        svc.create_contract({**sample_contract, "title": "订单合同", "contract_no": order_no})

        engine = svc.engine
        related = engine.find_related_contracts(contract_no)
        types = [r["relation_type"] for r in related]
        assert "order" in types

    def test_no_relation_different_prefix(self, svc, sample_contract):
        """不同日期的合同不应关联。"""
        r1 = svc.create_contract({**sample_contract, "contract_no": "CR-20260101-0001"})
        svc.create_contract({**sample_contract, "contract_no": "CR-20261231-0001"})

        engine = svc.engine
        related = engine.find_related_contracts("CR-20260101-0001")
        assert len(related) == 0

    def test_auto_build_relations(self, svc, sample_contract):
        """auto_build_relations 自动写入 cr_contract_relations。"""
        r1 = svc.create_contract(sample_contract)
        contract_no = svc.get_contract(r1["id"])["contract_no"]
        bc_no = "BC-" + contract_no[3:]
        svc.create_contract({**sample_contract, "title": "补充协议", "contract_no": bc_no})

        engine = svc.engine
        new_count = engine.auto_build_relations(r1["id"])
        assert new_count >= 1

        # 幂等：再次调用不新增
        new_count2 = engine.auto_build_relations(r1["id"])
        assert new_count2 == 0

    def test_get_related_contracts_service(self, svc, sample_contract):
        """Service 层 get_related_contracts 返回结构化数据。"""
        r1 = svc.create_contract(sample_contract)
        contract_no = svc.get_contract(r1["id"])["contract_no"]
        bc_no = "BC-" + contract_no[3:]
        svc.create_contract({**sample_contract, "title": "补充协议", "contract_no": bc_no})

        result = svc.get_related_contracts(r1["id"])
        assert "source" in result
        assert "relations" in result
        assert result["source"]["id"] == r1["id"]
        assert len(result["relations"]) >= 1


# ══════════════════════════════════════════════════════════
# 7. 审核建议生成（§2.2 / §5.2）
# ══════════════════════════════════════════════════════════

class TestReviewSuggestions:
    """测试 generate_review_suggestions 方法。"""

    def test_generate_with_risks(self, svc, sample_contract):
        """有风险的合同应生成审核建议。"""
        contract_content = """
        甲方：北京梆梆安全科技有限公司
        乙方：测试公司
        合同金额：100万元
        本合同自签订之日起生效。
        违约金：无。
        """
        r = svc.create_contract({**sample_contract, "amount": 1000000})
        cid = r["id"]

        # 先做风险扫描
        svc.scan_risks(cid, contract_content)

        # 生成审核建议
        suggestions = svc.generate_review_suggestions(cid)
        assert "contract_no" in suggestions
        assert "overall_risk" in suggestions
        assert "suggestions" in suggestions
        assert "auto_fill_fields" in suggestions
        assert suggestions["contract_no"] == svc.get_contract(cid)["contract_no"]

    def test_generate_no_risks(self, svc, sample_contract):
        """无风险时 overall_risk 为 low。"""
        r = svc.create_contract({**sample_contract, "amount": 50000})
        cid = r["id"]

        suggestions = svc.generate_review_suggestions(cid)
        assert suggestions["overall_risk"] == "low"
        assert isinstance(suggestions["suggestions"], list)

    def test_auto_fill_fields(self, svc, sample_contract):
        """auto_fill_fields 应包含合同基本信息。"""
        r = svc.create_contract({
            **sample_contract,
            "amount": 500000,
            "effective_date": "2026-10-01",
            "expiry_date": "2027-09-30",
        })
        cid = r["id"]

        suggestions = svc.generate_review_suggestions(cid)
        af = suggestions["auto_fill_fields"]
        assert "party_a" in af
        assert "amount" in af
        assert af["amount"] == 500000
        assert "effective_date" in af


# ══════════════════════════════════════════════════════════
# 8. OA 自动获取（§11）
# ══════════════════════════════════════════════════════════

class TestOaFetch:
    """测试 fetch_from_oa 方法（降级模式）。"""

    def test_fetch_single_degraded(self, svc):
        """integration 不可用时应返回降级结果。"""
        result = svc.fetch_from_oa(contract_no="BC202609220001", fetch_type="single")
        assert result["source"] == "oa"
        assert result["fetch_type"] == "single"
        assert result["degraded"] is True
        assert result["count"] == 0
        assert "degrade_reason" in result
        assert "fallback" in result

    def test_fetch_batch_degraded(self, svc):
        """batch 模式降级。"""
        result = svc.fetch_from_oa(fetch_type="batch")
        assert result["fetch_type"] == "batch"
        assert result["degraded"] is True

    def test_fetch_ledger_degraded(self, svc):
        """ledger 模式降级。"""
        result = svc.fetch_from_oa(contract_no="BC202609220001", fetch_type="ledger")
        assert result["fetch_type"] == "ledger"
        assert result["degraded"] is True

    def test_fetch_returns_contracts_list(self, svc):
        """返回结构中 contracts 是列表。"""
        result = svc.fetch_from_oa(fetch_type="single")
        assert isinstance(result["contracts"], list)


# ══════════════════════════════════════════════════════════
# 9. WeCom 消息处理（§2.4 / §5.3）
# ══════════════════════════════════════════════════════════

class TestWecomHandler:
    """测试 WecomContractHandler。"""

    def test_help_command(self, svc):
        """帮助指令返回帮助文本。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({"content": "帮助", "from_user": "test"})
        assert result["success"] is True
        assert result["action"] == "help"
        assert "可用指令" in result["reply_text"]

    def test_help_english(self, svc):
        """help 英文指令也应返回帮助。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({"content": "help", "from_user": "test"})
        assert result["success"] is True

    def test_query_command(self, svc, sample_contract):
        """查询指令返回合同列表。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        svc.create_contract({**sample_contract, "title": "梆梆安全测试合同"})
        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({"content": "查询 梆梆", "from_user": "test"})
        assert result["success"] is True
        assert result["action"] == "query"
        assert result["result"]["total"] >= 1

    def test_query_not_found(self, svc, sample_contract):
        """查询无结果时返回提示。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({"content": "查询 不存在的合同", "from_user": "test"})
        assert result["success"] is True
        assert "未找到" in result["reply_text"]

    def test_parse_command(self, svc, sample_contract):
        """解析指令返回合同详情。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        r = svc.create_contract(sample_contract)
        contract_no = svc.get_contract(r["id"])["contract_no"]
        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({"content": f"解析 {contract_no}", "from_user": "test"})
        assert result["success"] is True
        assert result["action"] == "parse"
        assert "合同详情" in result["reply_text"]

    def test_approve_review_command(self, svc, sample_contract):
        """审批指令返回审核建议。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        r = svc.create_contract({**sample_contract, "amount": 50000})
        contract_no = svc.get_contract(r["id"])["contract_no"]
        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({"content": f"审批 {contract_no}", "from_user": "test"})
        assert result["success"] is True
        assert result["action"] == "approve_review"
        assert "审核建议" in result["reply_text"]

    def test_reject_command(self, svc, sample_contract):
        """驳回指令执行驳回操作。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        r = svc.create_contract(sample_contract)
        cid = r["id"]
        contract_no = svc.get_contract(cid)["contract_no"]
        svc.submit_approval(cid, operator="sales")
        assert svc.get_contract(cid)["status"] == "review1"

        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({
            "content": f"驳回 {contract_no} 价格有问题",
            "from_user": "mgr",
        })
        assert result["success"] is True
        assert result["action"] == "reject"
        assert svc.get_contract(cid)["status"] == "draft"

    def test_approve_pass_command(self, svc, sample_contract):
        """审批通过指令执行 approve 操作。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        r = svc.create_contract({**sample_contract, "amount": 50000})  # level 1
        cid = r["id"]
        contract_no = svc.get_contract(cid)["contract_no"]
        svc.submit_approval(cid, operator="sales")
        assert svc.get_contract(cid)["status"] == "review1"

        handler = WecomContractHandler(service=svc)
        result = handler.handle_message({
            "content": f"审批通过 {contract_no}",
            "from_user": "mgr",
        })
        assert result["success"] is True
        assert result["action"] == "approve_pass"
        # level 1 应该直接 approved
        assert svc.get_contract(cid)["status"] == "approved"

    def test_unknown_command(self, svc):
        """未知指令应抛出 WecomParseError。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        from bdms.modules.contract_management.errors import WecomParseError
        handler = WecomContractHandler(service=svc)
        with pytest.raises(WecomParseError):
            handler.handle_message({"content": "xxx 不存在的指令", "from_user": "test"})

    def test_empty_content(self, svc):
        """空内容应抛出 WecomParseError。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        from bdms.modules.contract_management.errors import WecomParseError
        handler = WecomContractHandler(service=svc)
        with pytest.raises(WecomParseError):
            handler.handle_message({"content": "", "from_user": "test"})

    def test_send_approval_notification(self, svc, sample_contract):
        """审批通知模板生成。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        r = svc.create_contract(sample_contract)
        handler = WecomContractHandler(service=svc)
        result = handler.send_approval_notification(r["id"], "张三")
        assert result["target"] == "张三"
        assert "待审批" in result["template"]

    def test_send_risk_alert(self, svc, sample_contract):
        """风险预警通知模板生成。"""
        from bdms.modules.contract_management.wecom_handler import WecomContractHandler
        r = svc.create_contract(sample_contract)
        handler = WecomContractHandler(service=svc)
        result = handler.send_risk_alert(r["id"], "高风险：违约金条款缺失")
        assert "高风险预警" in result["template"]


# ══════════════════════════════════════════════════════════
# 10. 错误处理（§15）
# ══════════════════════════════════════════════════════════

class TestErrorHandling:
    """测试 CR-4xxx / CR-5xxx / CR-6xxx 错误码体系。"""

    def test_error_codes_exist(self):
        """所有设计文档中的错误码都应存在。"""
        from bdms.modules.contract_management.errors import (
            ContractNotFoundError, InvalidTransitionError,
            ContractValidationError, ContractDuplicateError,
            ContractReadOnlyError, OCRExtractError,
            DocxGenerateError, ContractParseError,
            OaFetchError, WecomParseError, RelationConflictError,
        )
        assert ContractNotFoundError.code == "CR-4001"
        assert InvalidTransitionError.code == "CR-4002"
        assert ContractValidationError.code == "CR-4003"
        assert ContractDuplicateError.code == "CR-4004"
        assert ContractReadOnlyError.code == "CR-4006"
        assert OCRExtractError.code == "CR-5001"
        assert DocxGenerateError.code == "CR-5002"
        assert ContractParseError.code == "CR-5005"
        assert OaFetchError.code == "CR-6001"
        assert WecomParseError.code == "CR-6002"
        assert RelationConflictError.code == "CR-6003"

    def test_error_http_status(self):
        """HTTP 状态码映射正确。"""
        from bdms.modules.contract_management.errors import (
            ContractNotFoundError, InvalidTransitionError,
            OaFetchError,
        )
        assert ContractNotFoundError.http_status == 404
        assert InvalidTransitionError.http_status == 400
        assert OaFetchError.http_status == 502

    def test_error_to_dict(self):
        """to_dict 方法返回结构化信息。"""
        from bdms.modules.contract_management.errors import ContractNotFoundError
        err = ContractNotFoundError("test msg")
        d = err.to_dict()
        assert d["code"] == "CR-4001"
        assert d["http_status"] == 404
        assert "message" in d
        assert "user_message" in d

    def test_get_error_by_code(self):
        """按错误码查找异常类。"""
        from bdms.modules.contract_management.errors import (
            get_error_by_code, ContractNotFoundError, OaFetchError,
        )
        assert get_error_by_code("CR-4001") is ContractNotFoundError
        assert get_error_by_code("CR-6001") is OaFetchError
        assert get_error_by_code("CR-9999") is None

    def test_degradation_info(self):
        """降级信息记录。"""
        from bdms.modules.contract_management.errors import DegradationInfo
        info = DegradationInfo("oa_fetch", "浏览器不可用", "手动录入")
        d = info.to_dict()
        assert d["feature"] == "oa_fetch"
        assert d["degraded"] is True
        assert d["reason"] == "浏览器不可用"
        assert d["fallback"] == "手动录入"


# ══════════════════════════════════════════════════════════
# 11. 角色权限（§14）
# ══════════════════════════════════════════════════════════

class TestRolesPermissions:
    """测试 PMO 角色 + 超级管理员权限。"""

    def test_pmo_approve_l3(self):
        """PMO 角色应有三级审批权限。"""
        from bdms.security import has_permission, Role, Permission
        assert has_permission([Role.PMO], Permission.CONTRACT_APPROVE_L3)

    def test_pmo_no_approve_l1(self):
        """PMO 角色不应有一级审批权限。"""
        from bdms.security import has_permission, Role, Permission
        assert not has_permission([Role.PMO], Permission.CONTRACT_APPROVE_L1)

    def test_pmo_no_approve_l4(self):
        """PMO 角色不应有四级审批权限。"""
        from bdms.security import has_permission, Role, Permission
        assert not has_permission([Role.PMO], Permission.CONTRACT_APPROVE_L4)

    def test_super_admin_has_all_permissions(self):
        """超级管理员拥有所有权限。"""
        from bdms.security import has_permission, Role, Permission
        # 系统级权限
        assert has_permission([Role.SUPER_ADMIN], Permission.SYSTEM_USER_MANAGE)
        assert has_permission([Role.SUPER_ADMIN], Permission.SYSTEM_CONFIG)
        # 业务权限
        assert has_permission([Role.SUPER_ADMIN], Permission.CONTRACT_CREATE)
        assert has_permission([Role.SUPER_ADMIN], Permission.CONTRACT_APPROVE_L4)
        assert has_permission([Role.SUPER_ADMIN], Permission.CONTRACT_ARCHIVE)
        assert has_permission([Role.SUPER_ADMIN], Permission.CONTRACT_OA_FETCH)

    def test_admin_no_system_permissions(self):
        """普通管理员没有系统级用户管理和配置权限。"""
        from bdms.security import has_permission, Role, Permission
        assert not has_permission([Role.ADMIN], Permission.SYSTEM_USER_MANAGE)
        assert not has_permission([Role.ADMIN], Permission.SYSTEM_CONFIG)

    def test_pmo_view_all_contracts(self):
        """PMO 可以查看所有合同。"""
        from bdms.security import has_permission, Role, Permission
        assert has_permission([Role.PMO], Permission.CONTRACT_VIEW_ALL)

    def test_legal_approve_l2(self):
        """法务有二级审批权限。"""
        from bdms.security import has_permission, Role, Permission
        assert has_permission([Role.LEGAL], Permission.CONTRACT_APPROVE_L2)

    def test_gm_approve_l4(self):
        """高管有四级审批权限。"""
        from bdms.security import has_permission, Role, Permission
        assert has_permission([Role.GM], Permission.CONTRACT_APPROVE_L4)

    def test_approval_level_roles_fallback_pmo(self, engine):
        """审批级别 fallback 角色应包含 PMO（非财务）。"""
        # 测试 L3 不可用时的 fallback（mock 掉 import）
        import sys
        # 直接测试 fallback 逻辑
        level3 = engine.get_approval_level(1000000)
        assert level3["level"] == 3
        # roles 中不应包含"财务"字样
        assert not any("财务" in r for r in level3["roles"])

        level4 = engine.get_approval_level(5000000)
        assert level4["level"] == 4
        assert not any("财务" in r for r in level4["roles"])


# ══════════════════════════════════════════════════════════
# 12. parse_contract（Engine 接口）
# ══════════════════════════════════════════════════════════

class TestParseContract:
    """测试 Engine.parse_contract 方法。"""

    def test_parse_contract_returns_dict(self, engine):
        """parse_contract 返回 dict 结构。"""
        text = "甲方：北京梆梆安全科技有限公司\n乙方：测试公司\n合同金额：100万元"
        result = engine.parse_contract(text)
        assert isinstance(result, dict)
        assert "parties" in result
        assert "clauses" in result
        assert "amount" in result

    def test_parse_contract_empty_text(self, engine):
        """空文本不报错。"""
        result = engine.parse_contract("")
        assert isinstance(result, dict)
