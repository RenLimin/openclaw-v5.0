"""最小正则浅解析（parser 兜底）— DETAIL §6。

L3 contract_parser 本期未随 L3 落地，故以最小正则兜底，
输出统一标注 ``parse_mode='浅解析'``，不作权威结构承诺。

抽取：甲方 / 乙方 / 金额 / 服务期 / 标的清单。
纯标准库，纯函数。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

PARSE_MODE = "浅解析"

# 甲乙方：标签后取中文/字母数字公司名（取到换行或空白尾）
_PARTY_PATTERN = re.compile(
    r'(甲方|委托方|买方|出让方)\s*[（(]?(?:盖章)?[）)]?\s*[：:]\s*'
    r'([\u4e00-\u9fa5A-Za-z0-9（）()·\-]+(?:公司|集团|研究院|事务所|银行|厂|店|学校|中心))'
)
_PARTY_B_PATTERN = re.compile(
    r'(乙方|受托方|卖方|受让方)\s*[（(]?(?:盖章)?[）)]?\s*[：:]\s*'
    r'([\u4e00-\u9fa5A-Za-z0-9（）()·\-]+(?:公司|集团|研究院|事务所|银行|厂|店|学校|中心))'
)

# 金额：￥/人民币/元，支持千分位
_AMOUNT_PATTERN = re.compile(
    r'(?:人民币|RMB|￥|¥)?\s*([0-9][0-9,]*(?:\.\d+)?)\s*(?:万元|元)'
)

# 日期：2026年1月1日 / 2026-01-01
_DATE_PATTERN = re.compile(r'\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{1,2}-\d{1,2}')

# 标的清单条目：编号 + 名称（+ 可选 数量/单价）
_ITEM_PATTERN = re.compile(
    r'(?:^|\n)\s*(?:\d+[.、）)]|[（(]\d+[）)])\s*'
    r'(?:(?:服务内容|服务目标|标的|产品名称|采购内容)[：:]\s*)?'
    r'([\u4e00-\u9fa5A-Za-z0-9][\u4e00-\u9fa5A-Za-z0-9\-/（）()]{1,40})'
    r'(?=[\s，,。；;]|$)'
)


@dataclass
class ShallowParseResult:
    """浅解析结果。"""

    party_a: Optional[str] = None
    party_b: Optional[str] = None
    amount: Optional[float] = None
    service_start: Optional[str] = None
    service_end: Optional[str] = None
    items: List[str] = field(default_factory=list)
    parse_mode: str = PARSE_MODE

    def to_dict(self) -> dict:
        return {
            "party_a": self.party_a,
            "party_b": self.party_b,
            "amount": self.amount,
            "service_start": self.service_start,
            "service_end": self.service_end,
            "items": self.items,
            "parse_mode": self.parse_mode,
        }


def _find_party(text: str, pattern: re.Pattern) -> Optional[str]:
    m = pattern.search(text)
    return m.group(2).strip() if m else None


def _find_amount(text: str) -> Optional[float]:
    for m in _AMOUNT_PATTERN.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        # "万元" 单位换算为元
        if "万元" in text[m.start():m.end()]:
            value *= 10000
        return value
    return None


def parse_shallow(text: str) -> ShallowParseResult:
    """对合同全文做最小正则浅解析。"""
    dates = _DATE_PATTERN.findall(text or "")
    service_start = dates[0] if dates else None
    service_end = dates[1] if len(dates) >= 2 else None

    items = []
    for m in _ITEM_PATTERN.finditer(text or ""):
        name = m.group(1).strip()
        # 过滤掉明显是条款编号/纯数字的噪声
        if name and not name.isdigit() and name not in items:
            items.append(name)

    return ShallowParseResult(
        party_a=_find_party(text or "", _PARTY_PATTERN),
        party_b=_find_party(text or "", _PARTY_B_PATTERN),
        amount=_find_amount(text or ""),
        service_start=service_start,
        service_end=service_end,
        items=items,
    )
