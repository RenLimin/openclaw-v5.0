"""P3：最小正则浅解析（甲乙方/金额/服务期/标的）。"""

from contract_review.parser import parse_shallow, PARSE_MODE

CONTRACT = """技术服务合同
甲方：北京梆梆安全科技有限公司
乙方：上海示例信息技术有限公司
签订日期：2026年1月1日。

服务期限：2026年2月1日 至 2027年1月31日。

合同总金额：人民币 128,000 元（大写：壹拾贰万捌仟元整）。

服务标的清单：
1、移动应用安全测评服务
2、源代码审计服务
3、渗透测试服务
"""


def test_parse_mode_marked():
    result = parse_shallow(CONTRACT)
    assert result.parse_mode == PARSE_MODE == "浅解析"
    assert result.to_dict()["parse_mode"] == "浅解析"


def test_parse_parties():
    result = parse_shallow(CONTRACT)
    assert result.party_a == "北京梆梆安全科技有限公司"
    assert result.party_b == "上海示例信息技术有限公司"


def test_parse_amount():
    result = parse_shallow(CONTRACT)
    assert result.amount == 128000.0


def test_parse_amount_wanyuan():
    text = "合同金额为人民币 12.5 万元。"
    result = parse_shallow(text)
    assert result.amount == 125000.0


def test_parse_service_dates():
    result = parse_shallow(CONTRACT)
    # 前两个日期：签订日期与服务起始
    assert result.service_start is not None
    assert result.service_end is not None
    assert "2026" in result.service_start


def test_parse_items():
    result = parse_shallow(CONTRACT)
    assert "移动应用安全测评服务" in result.items
    assert "源代码审计服务" in result.items
    assert "渗透测试服务" in result.items


def test_parse_empty_text_safe():
    result = parse_shallow("")
    assert result.party_a is None
    assert result.amount is None
    assert result.items == []
    assert result.parse_mode == "浅解析"
