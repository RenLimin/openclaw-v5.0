"""AC-1 公共 API 契约：导出符号 + 关键函数签名稳定性。"""
import inspect

import contract_management as cm


def test_all_exports_present():
    missing = [n for n in cm.__all__ if not hasattr(cm, n)]
    assert missing == []


def test_expected_export_count():
    # 2026-11-05 P2 合并：原 DETAIL §7 冻结的 18 个符号必须全部保留（向后兼容），
    # P2 新增解析/审核/适配 15 个符号。此处断言原 18 个仍在，不锁死总数。
    p1_frozen = [
        "Contract", "ApprovalRecord", "AuditLogEntry", "RiskReport",
        "RiskFinding", "ApprovalConfig", "CONTRACT_STATUSES", "VALID_TRANSITIONS",
        "ApprovalStateMachine", "get_approval_config", "can_transition",
        "next_approval_status", "scan_text", "scan_text_dict", "RiskRule",
        "CHECK_RULES", "amount_to_chinese", "OaProvider",
    ]
    missing = [n for n in p1_frozen if n not in cm.__all__]
    assert missing == [], f"P1 冻结符号丢失: {missing}"
    # P2 新增符号
    p2_new = [
        "ContractClause", "ParsedContract", "parse_contract", "CLAUSE_CATEGORIES",
        "AuditCriterion", "AUDIT_CRITERIA", "get_criterion_by_id",
        "get_criteria_by_category", "get_all_categories", "AuditResult",
        "AuditReport", "audit_contract", "format_audit_report", "HANDLERS",
    ]
    missing_p2 = [n for n in p2_new if n not in cm.__all__]
    assert missing_p2 == [], f"P2 新增符号丢失: {missing_p2}"


def test_state_machine_fn_signature():
    sig = inspect.signature(cm.next_approval_status)
    params = list(sig.parameters)
    assert params == ["amount", "current_status", "action", "level_table"]
    assert sig.parameters["level_table"].default is None


def test_get_approval_config_signature():
    sig = inspect.signature(cm.get_approval_config)
    assert list(sig.parameters) == ["amount", "level_table"]


def test_scan_text_signature():
    sig = inspect.signature(cm.scan_text)
    assert list(sig.parameters) == ["text", "custom_rules"]


def test_scan_text_dict_present():
    assert callable(cm.scan_text_dict)


def test_amount_to_chinese_signature():
    sig = inspect.signature(cm.amount_to_chinese)
    assert list(sig.parameters) == ["amount"]


def test_oa_provider_is_abstract():
    import abc
    assert isinstance(cm.OaProvider, abc.ABCMeta)
    # 抽象方法不可直接实例化
    import pytest
    with pytest.raises(TypeError):
        cm.OaProvider()
