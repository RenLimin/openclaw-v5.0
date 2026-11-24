"""AC-9 主体信息抽取（v1.1）：按方归属，禁止跨方串用。

背景：v1.0 `_extract_party_info` 对地址/邮箱/开户行/账号按「全文首个匹配」赋值，
甲乙方共用同一规则 → 真实样本 886377 复现 `party_a == party_b`（银行账号实为乙方）。
本文件锁定 v1.1 口径：双列表格按列归属、单值按最近提及距离归属、并列不归属、
缺失优于错误。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract_management.contract_parser import parse_contract

# ---- 构造样本：双列表格 + 单列字段 ----
TABLE_SAMPLE = """合同编号：XSZS20260101001
甲方：上海某某科技有限公司
乙方：北京某某信息技术有限公司
需方： | 上海某某科技有限公司（以下简称"甲方"） | 供方： | 北京某某信息技术有限公司（以下简称"乙方"）
地址： | 上海市浦东新区世纪大道100号 | 地址： | 北京市海淀区中关村大街27号
电话： | 021-60001111 | 电话： | 010-88886666
联系人： | 张三 | 联系人： | 李四
"""

SINGLE_SAMPLE = """甲方：杭州甲公司
地址：浙江省杭州市西湖区文三路90号
联系电话：0571-88886666
乙方：深圳乙公司
地址：广东省深圳市南山区科技园路1号
"""


def _parse(text):
    return parse_contract(text)


def test_name_from_signature_block():
    p = _parse(TABLE_SAMPLE)
    assert p.party_a["name"] == "上海某某科技有限公司"
    assert p.party_b["name"] == "北京某某信息技术有限责任公司" or \
        p.party_b["name"] == "北京某某信息技术有限公司"


def test_table_columns_attributed_by_column_not_global_first():
    """表格两列必须分属甲乙方（v1.0 缺陷=双方同值）。"""
    p = _parse(TABLE_SAMPLE)
    assert p.party_a.get("address") == "上海市浦东新区世纪大道100号", p.party_a
    assert p.party_b.get("address") == "北京市海淀区中关村大街27号", p.party_b
    assert p.party_a.get("address") != p.party_b.get("address")


def test_table_phone_columns_split():
    p = _parse(TABLE_SAMPLE)
    assert p.party_a.get("phone") == "021-60001111"
    assert p.party_b.get("phone") == "010-88886666"


def test_single_column_nearest_distance():
    """单列地址按最近标签距离归属。"""
    p = _parse(SINGLE_SAMPLE)
    assert p.party_a.get("address") == "浙江省杭州市西湖区文三路90号"
    assert p.party_b.get("address") == "广东省深圳市南山区科技园路1号"


def test_missing_beats_wrong():
    """只出现一个地址且贴近甲方时，乙方地址应缺失而非复制。"""
    text = "甲方：A公司\n地址：仅甲方地址\n乙方：B公司\n"
    p = _parse(text)
    assert p.party_a.get("address")
    assert not p.party_b.get("address"), p.party_b


def test_real_sample_886377_no_mixing():
    """真实样本回归：886377 甲方(海通恒信)不得拿乙方地址/银行。"""
    sample = "/Users/bangcle/.openclaw/workspace/tmp/oa-757/886377/contract.txt"
    if not os.path.exists(sample):
        pytest.skip("缺 886377 样本")
    p = _parse(open(sample, encoding="utf-8").read())
    # 甲乙方地址不同
    assert p.party_a.get("address") != p.party_b.get("address")
    # 甲方=上海（海通恒信），乙方=北京（梆梆）
    assert "上海" in (p.party_a.get("address") or "")
    assert "北京" in (p.party_b.get("address") or "")
    # 银行信息属乙方（合同 2.3 乙方指定账户）
    assert p.party_b.get("bank") == "上海银行股份有限公司北京海淀支行"
    assert not p.party_a.get("bank"), "甲方不应拿到乙方开户行"
    # 邮箱带「向」前缀须剥离
    if p.party_a.get("email"):
        assert p.party_a["email"].startswith(("huijuan", "delivery")), p.party_a["email"]


def test_backward_compatible_signature():
    """AC-1 契约稳定：parse_contract(text) 签名不变。"""
    import inspect
    assert list(inspect.signature(parse_contract).parameters) == ["text"]


# ---- 无管道版式（docx 表格提取，标签重复连排）----
DOCX_SAMPLE = """合同编号：XSZS20260101001
甲方：上海某某科技有限公司
乙方：北京某某信息技术有限公司
需方： 上海某某科技有限公司（以下简称“甲方”） 供方： 北京某某信息技术有限公司（以下简称“乙方”）
地址： 上海市浦东新区世纪大道100号 地址： 北京市海淀区中关村大街27号
电话： 021-60001111 电话： 010-88886666
"""


def test_docx_style_no_pipe_columns():
    """docx 提取文本无 | 分隔时，同名字段两列仍须按列分配。"""
    p = _parse(DOCX_SAMPLE)
    assert p.party_a.get("address") == "上海市浦东新区世纪大道100号", p.party_a
    assert p.party_b.get("address") == "北京市海淀区中关村大街27号", p.party_b
    assert p.party_a.get("phone") == "021-60001111"
    assert p.party_b.get("phone") == "010-88886666"


def test_plain_body_line_not_treated_as_table():
    """正文散行（如「甲方指定地址：」）不得被当表格行切分。"""
    text = "甲方：A公司\n甲方指定地址：\n全包装产品：某地\n乙方：B公司\n"
    p = _parse(text)
    # 只有带冒号的散值才可能被距离归属；不得凭空造两列
    assert "address" not in p.party_b or not p.party_b["address"]
