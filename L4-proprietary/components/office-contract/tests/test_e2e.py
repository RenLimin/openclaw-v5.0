"""
端到端集成测试 — Office 合同审批工作流
覆盖: init → create → submit → risk-scan → N级审批 → generate → sign → archive
"""

import os
import sys
import tempfile
import shutil
import pytest

# 路径设置
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODULE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, MODULE_DIR)

# 在 import services 前覆盖配置
import config

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def test_env():
    """创建临时数据库和输出目录，模块级复用"""
    test_db = os.path.join(tempfile.gettempdir(), "test_office_contract_e2e.db")
    test_output_dir = os.path.join(tempfile.gettempdir(), "test_office_contract_e2e_outputs")

    # 备份原配置
    orig_db = config.DB_PATH
    orig_output = config.OUTPUT_DIR

    # 覆盖配置
    config.DB_PATH = test_db
    config.OUTPUT_DIR = test_output_dir

    # 清理旧数据
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)
    os.makedirs(test_output_dir, exist_ok=True)

    yield {"db_path": test_db, "output_dir": test_output_dir}

    # 清理
    config.DB_PATH = orig_db
    config.OUTPUT_DIR = orig_output
    if os.path.exists(test_db):
        os.remove(test_db)
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)


@pytest.fixture(scope="module")
def services(test_env):
    """导入 service 层（配置已覆盖）"""
    from services import (
        init_db, create_contract, submit_for_approval,
        approve, reject, sign_contract, archive_contract,
        risk_scan, generate_contract_doc, get_contract, list_contracts,
        get_approval_level,
    )
    init_db()
    return {
        "init_db": init_db,
        "create_contract": create_contract,
        "submit_for_approval": submit_for_approval,
        "approve": approve,
        "reject": reject,
        "sign_contract": sign_contract,
        "archive_contract": archive_contract,
        "risk_scan": risk_scan,
        "generate_contract_doc": generate_contract_doc,
        "get_contract": get_contract,
        "list_contracts": list_contracts,
        "get_approval_level": get_approval_level,
    }


# ============================================================
# Phase 1: 数据库初始化
# ============================================================

class TestInit:
    def test_db_init(self, test_env):
        from services import init_db
        init_db()
        assert os.path.exists(test_env["db_path"]), "数据库文件未创建"


# ============================================================
# Phase 2: 合同创建 (4 个金额级别)
# ============================================================

class TestContractCreate:
    def test_create_level1(self, services):
        """< 10万 → 1级"""
        result = services["create_contract"](
            title="小型技术服务合同",
            party_b="测试客户A有限公司",
            amount=50000,
            contract_type="tech_service",
            effective_date="2026-09-01",
            expiry_date="2027-08-31",
        )
        assert result["id"] > 0
        assert result["approval_level"] == 1
        assert len(result["approval_roles"]) == 1
        TestContractCreate.l1_id = result["id"]

    def test_create_level2(self, services):
        """10-50万 → 2级"""
        result = services["create_contract"](
            title="中型软件许可合同",
            party_b="测试客户B科技有限公司",
            amount=250000,
            contract_type="software_license",
            effective_date="2026-09-01",
            expiry_date="2027-08-31",
        )
        assert result["approval_level"] == 2
        assert len(result["approval_roles"]) == 2
        TestContractCreate.l2_id = result["id"]

    def test_create_level3(self, services):
        """50-200万 → 3级"""
        result = services["create_contract"](
            title="大型综合服务合同",
            party_b="测试客户C集团有限公司",
            amount=800000,
            contract_type="sow",
            effective_date="2026-09-01",
            expiry_date="2029-08-31",
        )
        assert result["approval_level"] == 3
        assert len(result["approval_roles"]) == 3
        TestContractCreate.l3_id = result["id"]

    def test_create_level4(self, services):
        """> 200万 → 4级"""
        result = services["create_contract"](
            title="超大型战略框架合同",
            party_b="测试客户D控股集团",
            amount=3000000,
            contract_type="tech_service",
            effective_date="2026-09-01",
            expiry_date="2030-08-31",
        )
        assert result["approval_level"] == 4
        assert len(result["approval_roles"]) >= 3
        TestContractCreate.l4_id = result["id"]

    def test_list_contracts(self, services):
        rows = services["list_contracts"]()
        assert len(rows) == 4, f"期望4条，实际{len(rows)}条"


# ============================================================
# Phase 3: 提交审批
# ============================================================

class TestSubmitApproval:
    def test_submit_l1(self, services):
        result = services["submit_for_approval"](TestContractCreate.l1_id)
        assert result["status"] == "review1"
        assert result["total_steps"] == 1

    def test_submit_l3(self, services):
        result = services["submit_for_approval"](TestContractCreate.l3_id)
        assert result["status"] == "review1"
        assert result["total_steps"] == 3


# ============================================================
# Phase 4: 风险扫描
# ============================================================

class TestRiskScan:
    def test_risk_scan_l1(self, services):
        report = services["risk_scan"](TestContractCreate.l1_id)
        assert "overall_risk" in report
        assert "findings" in report
        assert len(report["findings"]) > 0
        assert "summary" in report
        assert report["summary"]["pass"] > 5

    def test_risk_scan_l3(self, services):
        report = services["risk_scan"](TestContractCreate.l3_id)
        assert report["contract_id"] == TestContractCreate.l3_id
        s = report["summary"]
        assert s["pass"] + s["warning"] + s["fail"] == len(report["findings"])


# ============================================================
# Phase 5: 分级审批 — 1级合同 (一步过)
# ============================================================

class TestLevel1Approval:
    def test_approve_step1(self, services):
        result = services["approve"](
            TestContractCreate.l1_id,
            approver_name="张经理",
            approver_role="销售经理",
            comment="同意，项目可行",
        )
        assert result["to_status"] == "approved"
        assert result["next_approver"] is None


# ============================================================
# Phase 6: 分级审批 — 3级合同 (多步)
# ============================================================

class TestLevel3Approval:
    def test_approve_step1_sales(self, services):
        result = services["approve"](
            TestContractCreate.l3_id,
            approver_name="王总监",
            approver_role="销售总监",
            comment="同意，继续流程",
        )
        assert result["to_status"] == "review2"
        assert result["next_approver"] is not None
        assert result["step"] == 1

    def test_approve_step2_legal(self, services):
        result = services["approve"](
            TestContractCreate.l3_id,
            approver_name="李法务",
            approver_role="法务审查员",
            comment="法律条款无问题",
        )
        assert result["to_status"] == "review3"
        assert result["step"] == 2

    def test_approve_step3_finance(self, services):
        result = services["approve"](
            TestContractCreate.l3_id,
            approver_name="赵财务",
            approver_role="财务经理",
            comment="金额核对无误",
        )
        assert result["to_status"] == "approved"
        assert result["next_approver"] is None
        assert result["step"] == 3


# ============================================================
# Phase 7: 驳回回退机制
# ============================================================

class TestRejectFlow:
    reject_id = None

    def test_create_and_submit(self, services):
        result = services["create_contract"](
            title="驳回测试合同",
            party_b="测试驳回客户",
            amount=200000,
            effective_date="2026-09-01",
            expiry_date="2027-08-31",
        )
        TestRejectFlow.reject_id = result["id"]
        services["submit_for_approval"](TestRejectFlow.reject_id)

    def test_reject_at_l1(self, services):
        result = services["reject"](
            TestRejectFlow.reject_id,
            approver_name="张经理",
            approver_role="销售经理",
            comment="合同标的描述不清晰，需要补充",
        )
        assert result["rejected_at_level"] == 1
        detail = services["get_contract"](TestRejectFlow.reject_id)
        assert detail["contract"]["status"] == "draft"

    def test_resubmit_after_reject(self, services):
        """驳回后可重新提交"""
        result = services["submit_for_approval"](TestRejectFlow.reject_id)
        assert result["status"] == "review1"


# ============================================================
# Phase 8: 合同文档生成
# ============================================================

class TestDocGeneration:
    def test_generate_l1(self, services, test_env):
        result = services["generate_contract_doc"](TestContractCreate.l1_id)
        assert os.path.exists(result["output_path"]), f"文件不存在: {result['output_path']}"
        size = os.path.getsize(result["output_path"])
        assert size > 1000, f"文件过小: {size} bytes"

    def test_generate_l3(self, services):
        result = services["generate_contract_doc"](TestContractCreate.l3_id)
        assert os.path.exists(result["output_path"])


# ============================================================
# Phase 9: 签署与归档
# ============================================================

class TestSignAndArchive:
    def test_sign_l1(self, services):
        result = services["sign_contract"](TestContractCreate.l1_id)
        assert result["status"] == "signed"
        detail = services["get_contract"](TestContractCreate.l1_id)
        assert detail["contract"]["status"] == "signed"

    def test_sign_unapproved_fails(self, services):
        """未通过审批的合同不能签署"""
        with pytest.raises(ValueError):
            services["sign_contract"](TestContractCreate.l2_id)

    def test_archive_l1(self, services):
        result = services["archive_contract"](TestContractCreate.l1_id)
        assert result["status"] == "archived"
        detail = services["get_contract"](TestContractCreate.l1_id)
        assert detail["contract"]["status"] == "archived"


# ============================================================
# Phase 10: 审计日志
# ============================================================

class TestAuditLogs:
    def test_l1_audit_complete(self, services):
        detail = services["get_contract"](TestContractCreate.l1_id)
        audits = detail["audit_logs"]
        actions = [a["action"] for a in audits]
        for exp in ["create", "submit", "approve", "sign", "archive"]:
            assert exp in actions, f"缺少审计操作: {exp}, 实际: {actions}"

    def test_l3_three_approvals(self, services):
        detail = services["get_contract"](TestContractCreate.l3_id)
        audits = detail["audit_logs"]
        actions = [a["action"] for a in audits]
        assert actions.count("approve") == 3, f"期望3次审批记录，实际{actions.count('approve')}次"

    def test_l3_approval_records(self, services):
        detail = services["get_contract"](TestContractCreate.l3_id)
        approvals = detail["approvals"]
        assert len(approvals) == 3, f"期望3条审批记录，实际{len(approvals)}条"
        levels = [a["approval_level"] for a in approvals]
        assert levels == [1, 2, 3], f"审批级别顺序错误: {levels}"
