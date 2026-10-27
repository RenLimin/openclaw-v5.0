"""AC-6 风险规则集与综合评级黄金基准。"""
import pytest

import contract_management as cm


def test_rule_count():
    assert len(cm.CHECK_RULES) == 22


def test_rule_ids_unique():
    ids = [r.id for r in cm.CHECK_RULES]
    assert len(ids) == len(set(ids))


def test_rule_structure():
    for r in cm.CHECK_RULES:
        assert r.risk in {"high", "medium", "low"}
        assert callable(r.check)
        assert isinstance(r.law, str) and r.law


# 构造最小合规文本：命中全部 22 条
COMPLIANT = (
    "甲方：北京某科技公司\n乙方：上海某有限公司\n"
    "地址：北京市海淀区中关村1号\n地址：上海市浦东新区张江路2号\n"
    "联系电话：01012345678\n联系电话：02187654321\n"
    "本合同经双方盖章签字生效。\n"
    "服务内容：技术服务与服务目标明确。\n"
    "服务期限自2026年1月1日至2026年12月31日止。\n"
    "合同金额（大写）：壹万元整。\n"
    "增值税税率6%。\n支付方式：银行转账，10个工作日内支付。\n"
    "乙方开具增值税专用发票。\n"
    "验收标准与方式：按需求文档验收。\n"
    "违约责任：违约方支付违约金，违约金按合同金额10%。\n"
    "争议解决：向甲方所在地人民法院起诉。\n"
    "知识产权与成果归甲方所有。\n"
    "保密条款：保密期限为合同终止后3年。\n"
    "不可抗力：双方互不担责。\n"
    "合同解除条件：协商一致可解除。\n"
    "本合同一式肆份，甲乙双方各执贰份。\n"
)


def test_compliant_text_all_pass_low():
    rep = cm.scan_text(COMPLIANT)
    fails = [f for f in rep.findings if f.status == "fail"]
    assert fails == [], "合规文本不应有 fail: %s" % [(f.id, f.item) for f in fails]
    assert rep.overall_risk == "low"


def test_missing_signature_is_high_fail():
    text = COMPLIANT.replace("盖章签字", "确认")
    rep = cm.scan_text(text)
    f = next(x for x in rep.findings if x.id == "1.5")
    assert f.status == "fail"
    assert rep.overall_risk == "high"


def test_penalty_50pct_fails():
    text = COMPLIANT.replace("违约金按合同金额10%", "违约金按合同金额50%")
    rep = cm.scan_text(text)
    assert next(x for x in rep.findings if x.id == "6.2").status == "fail"


def test_penalty_20pct_passes():
    text = COMPLIANT.replace("违约金按合同金额10%", "违约金按合同金额20%")
    rep = cm.scan_text(text)
    assert next(x for x in rep.findings if x.id == "6.2").status == "pass"


def test_missing_confidentiality_period_warning():
    # 隔离文本：有"保密"但无任何期限"年/终止"字样 → 9.2 判 warning
    text = "本合同约定保密条款，双方承担保密义务。"
    rep = cm.scan_text(text)
    assert next(x for x in rep.findings if x.id == "9.2").status == "warning"


def test_three_warnings_is_medium():
    # 制造恰好 3 条 warning（不含 high fail）：不可抗力10.1 + 份数13.1 + 生效13.2
    text = COMPLIANT
    text = text.replace("不可抗力：双方互不担责。\n", "")          # 10.1 warning
    text = text.replace("本合同一式肆份，甲乙双方各执贰份。\n", "")# 13.1 warning
    text = text.replace("盖章签字生效", "盖章签字确认")             # 13.2 warning
    rep = cm.scan_text(text)
    assert rep.summary["warning"] == 3
    assert rep.overall_risk == "medium"


def test_to_dict_is_plain_native():
    d = cm.scan_text_dict(COMPLIANT)
    assert set(d.keys()) == {"overall_risk", "summary", "scan_time", "findings"}
    for f in d["findings"]:
        assert isinstance(f, dict)
        assert set(f.keys()) == {"id", "category", "item", "status", "risk", "law"}


def test_custom_rules_replace_default():
    custom = [cm.RiskRule("x.1", "自定义", "始终通过", "low", "—", lambda t: True)]
    rep = cm.scan_text("任意", custom)
    assert len(rep.findings) == 1 and rep.findings[0].id == "x.1"


def test_empty_rules_yields_low():
    rep = cm.scan_text("x", [])
    assert rep.findings == [] and rep.overall_risk == "low"


def test_penalty_non_numeric_ignored():
    # 命中百分比正则但 float 转换异常的容错分支
    import contract_management
    from contract_management.risk_engine import _check_penalty_reasonable
    # 正常数值仍判定
    assert _check_penalty_reasonable("违约金10%") is True
    assert _check_penalty_reasonable("违约金40%") is False
