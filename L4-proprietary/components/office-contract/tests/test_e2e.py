#!/usr/bin/env python3
"""
端到端集成测试 — Office 合同审批工作流
覆盖: init → create → submit → risk-scan → N级审批 → generate → sign → archive
"""

import os
import sys
import tempfile
import shutil

# 路径设置
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODULE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, MODULE_DIR)

# 测试用临时数据库
TEST_DB = os.path.join(tempfile.gettempdir(), "test_office_contract.db")
TEST_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "test_office_contract_outputs")

# 在 import services 前覆盖配置
import config
config.DB_PATH = TEST_DB
config.OUTPUT_DIR = TEST_OUTPUT_DIR

# 清理旧数据
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
if os.path.exists(TEST_OUTPUT_DIR):
    shutil.rmtree(TEST_OUTPUT_DIR)
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

from services import (
    init_db, create_contract, submit_for_approval,
    approve, reject, sign_contract, archive_contract,
    risk_scan, generate_contract_doc, get_contract, list_contracts,
    get_approval_level,
)

passed = 0
failed = 0


def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✅ {name}")
        passed += 1
    except AssertionError as e:
        print(f"  ❌ {name}: {e}")
        failed += 1
    except Exception as e:
        print(f"  💥 {name}: 异常 - {e}")
        failed += 1


# ============================================================
# 测试 1: 初始化
# ============================================================
print("\n🧪 Phase 1: 数据库初始化")

def t_init():
    init_db()
    assert os.path.exists(TEST_DB), "数据库文件未创建"

test("数据库初始化", t_init)


# ============================================================
# 测试 2: 合同创建 (3 个不同金额级别)
# ============================================================
print("\n🧪 Phase 2: 合同创建")

contracts = {}

def t_create_level1():
    result = create_contract(
        title="小型技术服务合同",
        party_b="测试客户A有限公司",
        amount=50000,  # < 10万 → 1级
        contract_type="tech_service",
        effective_date="2026-09-01",
        expiry_date="2027-08-31",
    )
    assert result["id"] > 0
    assert result["approval_level"] == 1
    assert len(result["approval_roles"]) == 1
    contracts["l1"] = result["id"]

test("创建1级审批合同 (<10万)", t_create_level1)


def t_create_level2():
    result = create_contract(
        title="中型软件许可合同",
        party_b="测试客户B科技有限公司",
        amount=250000,  # 10-50万 → 2级
        contract_type="software_license",
        effective_date="2026-09-01",
        expiry_date="2027-08-31",
    )
    assert result["approval_level"] == 2
    assert len(result["approval_roles"]) == 2
    contracts["l2"] = result["id"]

test("创建2级审批合同 (10-50万)", t_create_level2)


def t_create_level3():
    result = create_contract(
        title="大型综合服务合同",
        party_b="测试客户C集团有限公司",
        amount=800000,  # 50-200万 → 3级
        contract_type="sow",
        effective_date="2026-09-01",
        expiry_date="2029-08-31",
    )
    assert result["approval_level"] == 3
    assert len(result["approval_roles"]) == 3
    contracts["l3"] = result["id"]

test("创建3级审批合同 (50-200万)", t_create_level3)


def t_create_level4():
    result = create_contract(
        title="超大型战略框架合同",
        party_b="测试客户D控股集团",
        amount=3000000,  # >200万 → 4级
        contract_type="tech_service",
        effective_date="2026-09-01",
        expiry_date="2030-08-31",
    )
    assert result["approval_level"] == 4
    assert len(result["approval_roles"]) == 3  # 4级审批有3个角色
    contracts["l4"] = result["id"]

test("创建4级审批合同 (>200万)", t_create_level4)


def t_list_contracts():
    rows = list_contracts()
    assert len(rows) == 4, f"期望4条，实际{len(rows)}条"

test("合同列表查询", t_list_contracts)


# ============================================================
# 测试 3: 提交审批
# ============================================================
print("\n🧪 Phase 3: 提交审批")

def t_submit_l1():
    result = submit_for_approval(contracts["l1"])
    assert result["status"] == "review1"
    assert result["total_steps"] == 1

test("提交1级合同审批", t_submit_l1)


def t_submit_l3():
    result = submit_for_approval(contracts["l3"])
    assert result["status"] == "review1"
    assert result["total_steps"] == 3

test("提交3级合同审批", t_submit_l3)


# ============================================================
# 测试 4: 风险扫描
# ============================================================
print("\n🧪 Phase 4: 风险扫描")

def t_risk_scan_l1():
    report = risk_scan(contracts["l1"])
    assert "overall_risk" in report
    assert "findings" in report
    assert len(report["findings"]) > 0
    assert "summary" in report
    # 基于生成的模拟文本，应有不少通过项
    assert report["summary"]["pass"] > 5, f"通过项过少: {report['summary']}"

test("风险扫描 (1级合同)", t_risk_scan_l1)


def t_risk_scan_l3():
    report = risk_scan(contracts["l3"])
    assert report["contract_id"] == contracts["l3"]
    # 3级合同金额大，风险扫描结果应同样完整
    assert report["summary"]["pass"] + report["summary"]["warning"] + report["summary"]["fail"] == len(report["findings"])

test("风险扫描 (3级合同)", t_risk_scan_l3)


# ============================================================
# 测试 5: 分级审批 (完整流程 — 1级合同)
# ============================================================
print("\n🧪 Phase 5: 分级审批 (1级合同)")

def t_approve_l1_step1():
    """1级合同一步审批通过"""
    result = approve(
        contracts["l1"],
        approver_name="张经理",
        approver_role="销售经理",
        comment="同意，项目可行",
    )
    assert result["to_status"] == "approved"
    assert result["next_approver"] is None

test("1级合同: 销售经理审批通过 → approved", t_approve_l1_step1)


# ============================================================
# 测试 6: 分级审批 (3级合同 — 多步)
# ============================================================
print("\n🧪 Phase 6: 分级审批 (3级合同)")

def t_approve_l3_step1():
    result = approve(
        contracts["l3"],
        approver_name="王总监",
        approver_role="销售总监",
        comment="同意，继续流程",
    )
    assert result["to_status"] == "review2"
    assert result["next_approver"] is not None
    assert result["step"] == 1

test("3级合同: L1 销售总监通过 → review2", t_approve_l3_step1)


def t_approve_l3_step2():
    result = approve(
        contracts["l3"],
        approver_name="李法务",
        approver_role="法务审查员",
        comment="法律条款无问题",
    )
    assert result["to_status"] == "review3"
    assert result["step"] == 2

test("3级合同: L2 法务通过 → review3", t_approve_l3_step2)


def t_approve_l3_step3():
    result = approve(
        contracts["l3"],
        approver_name="赵财务",
        approver_role="财务经理",
        comment="金额核对无误",
    )
    assert result["to_status"] == "approved"
    assert result["next_approver"] is None
    assert result["step"] == 3

test("3级合同: L3 财务通过 → approved", t_approve_l3_step3)


# ============================================================
# 测试 7: 驳回回退
# ============================================================
print("\n🧪 Phase 7: 驳回回退机制")

reject_contract_id = None

def t_create_reject_test():
    global reject_contract_id
    result = create_contract(
        title="驳回测试合同",
        party_b="测试驳回客户",
        amount=200000,  # 2级
        effective_date="2026-09-01",
        expiry_date="2027-08-31",
    )
    reject_contract_id = result["id"]
    submit_for_approval(reject_contract_id)

test("创建驳回测试合同并提交", t_create_reject_test)


def t_reject_at_l1():
    result = reject(
        reject_contract_id,
        approver_name="张经理",
        approver_role="销售经理",
        comment="合同标的描述不清晰，需要补充",
    )
    assert result["rejected_at_level"] == 1

    # 验证状态回退
    detail = get_contract(reject_contract_id)
    assert detail["contract"]["status"] == "draft"

test("一级审批驳回 → 回退到 draft", t_reject_at_l1)


def t_reject_draft_cannot_submit_again():
    """驳回后可以重新提交（正常流程应该可以）"""
    result = submit_for_approval(reject_contract_id)
    assert result["status"] == "review1"

test("驳回后可重新提交审批", t_reject_draft_cannot_submit_again)


# ============================================================
# 测试 8: 合同文档生成
# ============================================================
print("\n🧪 Phase 8: 合同文档生成")

def t_generate_doc_l1():
    result = generate_contract_doc(contracts["l1"])
    assert os.path.exists(result["output_path"]), f"文件不存在: {result['output_path']}"
    # 验证文件大小合理 (> 1KB)
    size = os.path.getsize(result["output_path"])
    assert size > 1000, f"文件过小: {size} bytes"

test("生成1级合同 docx", t_generate_doc_l1)


def t_generate_doc_l3():
    result = generate_contract_doc(contracts["l3"])
    assert os.path.exists(result["output_path"])

test("生成3级合同 docx", t_generate_doc_l3)


# ============================================================
# 测试 9: 签署 + 归档
# ============================================================
print("\n🧪 Phase 9: 签署与归档")

def t_sign_l1():
    result = sign_contract(contracts["l1"])
    assert result["status"] == "signed"
    detail = get_contract(contracts["l1"])
    assert detail["contract"]["status"] == "signed"

test("签署1级合同", t_sign_l1)


def t_sign_before_approve_fails():
    """未通过审批的合同不能签署"""
    try:
        sign_contract(contracts["l2"])  # l2 还没提交过
        assert False, "应该抛出异常"
    except ValueError:
        pass  # 预期行为

test("未批准合同不能签署 (状态校验)", t_sign_before_approve_fails)


def t_archive_l1():
    result = archive_contract(contracts["l1"])
    assert result["status"] == "archived"
    detail = get_contract(contracts["l1"])
    assert detail["contract"]["status"] == "archived"

test("归档1级合同", t_archive_l1)


# ============================================================
# 测试 10: 审计日志完整性
# ============================================================
print("\n🧪 Phase 10: 审计日志")

def t_audit_logs_complete():
    """验证合同有完整的审计轨迹"""
    detail = get_contract(contracts["l1"])
    audits = detail["audit_logs"]
    actions = [a["action"] for a in audits]

    # 1级合同应有的操作: create, submit, risk_scan, approve, sign, archive
    expected = ["create", "submit", "approve", "sign", "archive"]
    for exp in expected:
        assert exp in actions, f"缺少审计操作: {exp}, 实际: {actions}"

test("审计日志完整性 (1级合同)", t_audit_logs_complete)


def t_audit_logs_l3_complete():
    detail = get_contract(contracts["l3"])
    audits = detail["audit_logs"]
    actions = [a["action"] for a in audits]

    # 3级合同应有 3 次 approve
    approve_count = actions.count("approve")
    assert approve_count == 3, f"期望3次审批记录，实际{approve_count}次"

test("审计日志完整性 (3级合同 3次审批)", t_audit_logs_l3_complete)


# ============================================================
# 测试 11: 合同详情 - 审批记录
# ============================================================
print("\n🧪 Phase 11: 审批记录")

def t_approval_records_l3():
    detail = get_contract(contracts["l3"])
    approvals = detail["approvals"]
    assert len(approvals) == 3, f"期望3条审批记录，实际{len(approvals)}条"

    # 验证级别递增
    levels = [a["approval_level"] for a in approvals]
    assert levels == [1, 2, 3], f"审批级别顺序错误: {levels}"

test("3级合同审批记录完整", t_approval_records_l3)


# ============================================================
# 汇总
# ============================================================
print(f"\n{'='*60}")
print(f"📊 测试结果: {passed} 通过, {failed} 失败")
print(f"{'='*60}")

if failed > 0:
    print("\n❌ 有失败的测试")
    sys.exit(1)
else:
    print("\n🎉 全部测试通过！")
    sys.exit(0)
