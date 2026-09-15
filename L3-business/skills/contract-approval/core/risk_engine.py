"""
风险扫描引擎 — L3 纯逻辑核心
==============================

基于《民法典》合同编的 22 条规则，对合同文本做纯函数式风险扫描。
输入：合同文本字符串。输出：RiskReport（结构化报告）。
零副作用 — 不读文件、不写数据库、不调外部 API。
"""

import re
from dataclasses import dataclass
from typing import List, Callable, Dict, Any
from datetime import datetime

from .models import RiskFinding, RiskReport


@dataclass
class RiskRule:
    """一条风险检查规则"""
    id: str
    category: str
    item: str
    risk: str           # high / medium / low
    law: str            # 法条依据，如 "§470"
    check: Callable[[str], bool]   # 检查函数：输入文本，返回 True=通过


def _check_penalty_reasonable(text: str) -> bool:
    """检查违约金比例是否合理（不超过 30%）"""
    patterns = [
        r'违约金.*?(\d+(?:\.\d+)?)\s*%',
        r'百分之(\d+(?:\.\d+)?)',
        r'按.*?(\d+(?:\.\d+)?)\s*%',
    ]
    for pat in patterns:
        for m in re.findall(pat, text):
            try:
                if float(m) > 30:
                    return False
            except ValueError:
                pass
    return True


# ============================================================
# 22 条风险检查规则
# ============================================================

CHECK_RULES: List[RiskRule] = [
    # 一、主体信息
    RiskRule("1.1", "主体信息", "双方当事人名称完整", "high", "§470",
             lambda t: len(re.findall(r'(甲方|乙方|委托方|受托方)[：:]\s*[\u4e00-\u9fa5]{2,}', t)) >= 2),
    RiskRule("1.2", "主体信息", "双方地址完整", "medium", "§470",
             lambda t: len(re.findall(r'地址[：:]\s*[\u4e00-\u9fa5省市区县街道路号\d]+', t)) >= 2),
    RiskRule("1.3", "主体信息", "双方联系电话/邮箱", "low", "—",
             lambda t: len(re.findall(r'联系电话[：:]\s*\d{8,}', t)) >= 2
                       or len(re.findall(r'[\w.+-]+@[\w-]+\.[\w]+', t)) >= 2),
    RiskRule("1.5", "主体信息", "签字盖章", "high", "§490",
             lambda t: "盖章" in t or "签字" in t or "签章" in t),

    # 二、合同标的
    RiskRule("2.1", "合同标的", "服务内容描述清晰", "high", "§470",
             lambda t: "服务内容" in t or "服务目标" in t or "技术服务" in t),
    RiskRule("2.4", "合同标的", "服务期限/起止日期明确", "medium", "§511",
             lambda t: len(re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', t)) >= 2),

    # 三、金额与支付
    RiskRule("3.1", "金额与支付", "合同金额大小写", "high", "—",
             lambda t: "大写" in t or "（大写）" in t or "整" in t),
    RiskRule("3.2", "金额与支付", "税率明确", "high", "—",
             lambda t: "%" in t and ("税率" in t or "税" in t)),
    RiskRule("3.3", "金额与支付", "支付方式明确", "medium", "§510",
             lambda t: "支付" in t and ("转账" in t or "银行" in t or "工作日" in t)),
    RiskRule("3.5", "金额与支付", "发票要求明确", "medium", "—",
             lambda t: "发票" in t or "增值税" in t),

    # 五、验收标准
    RiskRule("5.1", "验收标准", "验收标准/方式明确", "high", "§509",
             lambda t: "验收" in t),

    # 六、违约责任
    RiskRule("6.1", "违约责任", "违约责任条款存在", "high", "§577",
             lambda t: "违约" in t or "违约金" in t),
    RiskRule("6.2", "违约责任", "违约金比例合理（不超过实际损失30%）", "high", "§585",
             _check_penalty_reasonable),

    # 七、争议解决
    RiskRule("7.1", "争议解决", "管辖法院/仲裁机构明确", "high", "§507",
             lambda t: "人民法院" in t or "仲裁" in t or "管辖" in t),
    RiskRule("7.3", "争议解决", "争议解决方式唯一", "medium", "—",
             lambda t: not ("人民法院" in t and "仲裁" in t and "起诉" in t)),

    # 八、知识产权
    RiskRule("8.1", "知识产权", "知识产权归属明确", "medium", "§847",
             lambda t: "知识产权" in t or "成果" in t),

    # 九、保密条款
    RiskRule("9.1", "保密条款", "保密条款存在", "medium", "§501",
             lambda t: "保密" in t),
    RiskRule("9.2", "保密条款", "保密期限明确", "medium", "—",
             lambda t: "保密" in t and ("年" in t or "终止" in t)),

    # 十、不可抗力
    RiskRule("10.1", "不可抗力", "不可抗力条款存在", "low", "§180",
             lambda t: "不可抗力" in t),

    # 十一、合同解除
    RiskRule("11.1", "合同解除", "合同解除条件明确", "medium", "§563",
             lambda t: "解除" in t),

    # 十三、其他
    RiskRule("13.1", "其他", "合同份数约定明确", "low", "—",
             lambda t: "份" in t and ("甲乙" in t or "双方" in t)),
    RiskRule("13.2", "其他", "合同生效条件明确", "medium", "—",
             lambda t: "生效" in t),
]


def scan_text(text: str, custom_rules: List[RiskRule] = None) -> RiskReport:
    """扫描合同文本，返回风险报告（纯函数）

    Args:
        text: 合同文本字符串
        custom_rules: 可选，自定义规则列表（覆盖默认 22 条）

    Returns:
        RiskReport — 结构化扫描结果
    """
    rules = custom_rules or CHECK_RULES
    findings: List[RiskFinding] = []

    for rule in rules:
        passed = rule.check(text)
        status = "pass" if passed else ("fail" if rule.risk == "high" else "warning")
        findings.append(RiskFinding(
            id=rule.id,
            category=rule.category,
            item=rule.item,
            status=status,
            risk=rule.risk,
            law=rule.law,
        ))

    # 统计
    pass_count = sum(1 for f in findings if f.status == "pass")
    warning_count = sum(1 for f in findings if f.status == "warning")
    fail_count = sum(1 for f in findings if f.status == "fail")

    # 综合评级
    if fail_count > 0:
        overall = "high"
    elif warning_count > 2:
        overall = "medium"
    else:
        overall = "low"

    return RiskReport(
        scan_time=datetime.now().isoformat(),
        overall_risk=overall,
        summary={"pass": pass_count, "warning": warning_count, "fail": fail_count},
        findings=findings,
    )


def scan_text_dict(text: str, custom_rules: List[RiskRule] = None) -> Dict[str, Any]:
    """scan_text 的 dict 版本（方便 JSON 序列化）"""
    return scan_text(text, custom_rules).to_dict()
