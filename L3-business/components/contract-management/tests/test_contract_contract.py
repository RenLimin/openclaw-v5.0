"""AC-1 公共 API 契约：导出符号 + 关键函数签名稳定性。"""
import inspect

import contract_management as cm


def test_all_exports_present():
    missing = [n for n in cm.__all__ if not hasattr(cm, n)]
    assert missing == []


def test_expected_export_count():
    # DETAIL §7 冻结的 18 个公共符号
    assert len(cm.__all__) == 18


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
