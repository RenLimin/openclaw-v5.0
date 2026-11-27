"""回归：_extract_clause_合同标的 对无捕获组正则调用 group(1) → IndexError。

背景（2026-11-27 Rex 实测）：真实 OA 单据 888194/888171/888166 的 .doc
附件（textutil 抽文本）含「Android应用加固软件…」行，命中模式
``r'Android应用加固软件[^\\n]+'``——该模式**无捕获组**，旧代码直接
``m.group(1)`` 抛 ``IndexError: no such group``，导致整份合同 R3 拆解失败
（L4 编排降级为 CONTRACT_REVIEW: IndexError）。修复=无分组时用 m.group(0) 兜底。

本用例锁定：任何正则无分组时不得崩溃，且产品名称仍可提取。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract_management.contract_parser import parse_contract


# 取自 888194《小米钱包-Android应用安全加固》真实 .doc 的形态（含表格空白行）
DOC_LIKE = """合同编码：

【 小米钱包-Android应用安全加固   项目】
软件授权许可使用合同

甲方：  捷付睿通（内蒙古）支付股份有限公司
乙方：北京梆梆安全科技有限公司

第一条 合同标的
Android应用加固软件V7.0  公有云增强版  数量3

第二条 付款方式
本协议生效后30日内，甲方一次性支付全额服务费用。
"""


def test_parse_contract_survives_no_group_pattern():
    """含无分组命中的真实 .doc 形态：不得抛 IndexError，条款仍抽出。"""
    parsed = parse_contract(DOC_LIKE)
    assert parsed is not None
    cats = {getattr(c, "category", "") for c in (parsed.clauses or [])}
    assert "合同标的" in cats, "合同标的条款应被抽出: %s" % cats


def test_product_name_extracted_from_unparenthesized_match():
    """兜底分支生效：无分组命中时取整段匹配作为产品名称。"""
    parsed = parse_contract(DOC_LIKE)
    clause = next((c for c in (parsed.clauses or [])
                   if getattr(c, "category", "") == "合同标的"), None)
    assert clause is not None
    blob = str(getattr(clause, "key_terms", "")) + str(getattr(clause, "summary", ""))
    assert "加固软件" in blob, "产品名称应从整段匹配兜底提取: %s" % blob
