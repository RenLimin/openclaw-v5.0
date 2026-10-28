"""P3：风险编排 — 用真实 L3 scan_text，断言 finding 与法条受控。"""

import pytest

from contract_review.digitize import DigitizedText
from contract_review.risk import run_risk, load_l3, RULE_SET_VERSION

# 含多项 L3 关键词的真实文本
GOOD_CONTRACT = """技术服务合同
甲方：北京梆梆安全科技有限公司
乙方：上海示例信息技术有限公司
地址：北京市海淀区中关村大街1号
地址：上海市浦东新区张江路2号
签订日期：2026年1月1日。
服务期限：2026年2月1日 至 2027年1月31日。
合同总金额：人民币 128000 元（大写：壹拾贰万捌仟元整），税率 6%。
以银行转账方式支付，发票为增值税专用发票。
服务内容：移动应用安全测评技术服务。
验收：双方按验收标准组织验收。
违约：违约方承担违约责任，违约金 10%。
争议由合同签订地人民法院管辖。
知识产权归甲方所有。
保密义务，保密期限 3 年。
不可抗力情形依法律规定。
合同解除需书面通知。本合同一式两份，双方各执一份，自盖章签字之日生效。
"""

EMPTY_TEXT = ""


def test_load_l3_returns_scan_and_rules():
    scan_text, check_rules = load_l3()
    assert callable(scan_text)
    assert len(check_rules) >= 20


def test_run_risk_returns_dict_structure():
    result = run_risk(DigitizedText(full_text=GOOD_CONTRACT, method="docx"))
    assert result["overall_risk"] in {"high", "medium", "low"}
    assert set(result["summary"]) == {"pass", "warning", "fail"}
    assert result["findings"]
    assert result["rule_set_version"] == RULE_SET_VERSION


def test_each_finding_has_required_fields():
    result = run_risk(DigitizedText(full_text=GOOD_CONTRACT, method="docx"))
    for f in result["findings"]:
        assert set(f) == {"id", "category", "item", "status", "risk", "law"}
        assert f["status"] in {"pass", "warning", "fail"}
        assert f["risk"] in {"high", "medium", "low"}


def test_laws_only_from_controlled_library():
    """法条依据只能来自 L3 CHECK_RULES（红线）。"""
    _, check_rules = load_l3()
    controlled = {r.law for r in check_rules}
    result = run_risk(DigitizedText(full_text=GOOD_CONTRACT, method="docx"))
    for f in result["findings"]:
        assert f["law"] in controlled


def test_keyword_text_produces_pass_findings():
    """构造含关键词文本，断言相应规则通过（真实 L3）。"""
    result = run_risk(DigitizedText(full_text=GOOD_CONTRACT, method="docx"))
    by_id = {f["id"]: f for f in result["findings"]}
    # 主体名称完整、验收条款、违约金等应通过
    assert by_id["1.1"]["status"] == "pass"
    assert by_id["5.1"]["status"] == "pass"
    assert by_id["6.1"]["status"] == "pass"


def test_empty_text_flags_high_risk_and_fail():
    result = run_risk(DigitizedText(full_text=EMPTY_TEXT, method="native_pdf"))
    assert result["overall_risk"] == "high"
    assert result["summary"]["fail"] > 0


def test_findings_count_matches_rules():
    _, check_rules = load_l3()
    result = run_risk(DigitizedText(full_text=GOOD_CONTRACT, method="docx"))
    assert len(result["findings"]) == len(check_rules)


def test_run_risk_bad_l3_root_raises(tmp_path):
    with pytest.raises(RuntimeError):
        run_risk(
            DigitizedText(full_text="x", method="docx"),
            l3_component_root=str(tmp_path / "missing"),
        )
