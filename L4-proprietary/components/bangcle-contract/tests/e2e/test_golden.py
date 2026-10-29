"""P8 §3/§9：黄金基准 E2E + 法条受控 + 幂等。

对冻结的黄金样例（真实合同文本）跑 run_risk：
  - findings rule_id 集合 == golden_expected.rule_ids（100% 匹配，不多不少）
  - overall_risk 一致
  - 每条 finding 的 law 都在 L3 CHECK_RULES（含 law='—' 的非法条项按受控库原样放行）
  - 连跑 3 次 rule_id/overall_risk 稳定（时间戳字段除外）
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
COMPONENT_ROOT = os.path.dirname(os.path.dirname(HERE))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(COMPONENT_ROOT)))
L3_ROOT = os.path.join(REPO_ROOT, "L3-business", "components", "contract-management")
for p in (COMPONENT_ROOT, L3_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract_review.digitize import DigitizedText
from contract_review.risk import run_risk, load_l3

GOLDEN_TEXT = (
    "技术服务合同\n甲方：北京某科技有限公司\n乙方：上海某服务有限公司\n"
    "本合同经双方盖章签字后生效。\n"
    "1. 服务内容：安全测评服务\n2. 服务内容：合规评估服务\n"
    "服务期限自2026年1月1日至2026年12月31日止。\n"
    "合同金额（大写）：壹万元整，人民币10000元。\n增值税税率6%。\n"
    "支付方式：银行转账，10个工作日内支付。\n乙方开具增值税专用发票。\n"
    "验收标准：按需求文档验收。\n"
    "违约责任：违约方支付违约金，违约金按合同金额10%。\n"
    "争议解决：向甲方所在地人民法院起诉。\n"
    "知识产权与成果归甲方所有。\n保密条款：保密期限为合同终止后3年。\n"
    "不可抗力：双方互不担责。\n合同解除条件：协商一致可解除。\n"
    "本合同一式肆份，甲乙双方各执贰份。\n"
)


@pytest.fixture(scope="module")
def expected():
    p = os.path.join(COMPONENT_ROOT, "tests", "fixtures", "golden_expected.json")
    return json.load(open(p, encoding="utf-8"))


def _run():
    return run_risk(DigitizedText(full_text=GOLDEN_TEXT, method="native_pdf"))


def test_golden_rule_ids_match(expected):
    r = _run()
    ids = [f["id"] for f in r["findings"]]
    assert ids == expected["rule_ids"], "黄金基准 rule_id 不匹配"
    assert r["overall_risk"] == expected["overall_risk"]


def test_golden_findings_law_controlled():
    r = _run()
    _, check_rules = load_l3()
    controlled_laws = {rule.law for rule in check_rules}
    controlled_ids = {rule.id for rule in check_rules}
    assert len(r["findings"]) == 22
    for f in r["findings"]:
        assert f["id"] in controlled_ids, "出现规则库外 id: %s" % f["id"]
        assert f["law"] in controlled_laws, "非受控法条: %r" % f["law"]


def test_golden_idempotent_three_runs(expected):
    outs = []
    for _ in range(3):
        r = _run()
        outs.append((r["overall_risk"], [f["id"] for f in r["findings"]]))
    assert outs[0] == outs[1] == outs[2]
    assert outs[0][1] == expected["rule_ids"]
