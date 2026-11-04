"""ontology.mapper 单测（纯函数，无网络/DB）。

契约：DESIGN-DETAIL-contract-ontology-bridge-v1.0 §2.1 / §4 P1。
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

from contract_management.models import Contract
from ontology.mapper import (
    FIELD_ALIASES,
    map_card_to_contract,
    map_contract_to_card,
    map_oa_status,
    parse_amount,
)

FIXTURE_PATH = os.path.join(
    COMPONENT_ROOT, "tests", "fixtures", "card_golden.json"
)


# ---------- 基础字段映射 ----------

def test_map_card_basic_fields():
    fields = {
        "合同编号": "XSZS001",
        "合同名称": "技术服务合同",
        "甲方": "梆梆安全",
        "乙方": "云动网络",
    }
    c = map_card_to_contract(fields)
    assert isinstance(c, Contract)
    assert c.contract_no == "XSZS001"
    assert c.title == "技术服务合同"
    assert c.party_a == "梆梆安全"
    assert c.party_b == "云动网络"
    # L3 默认值
    assert c.contract_type == "tech_service"
    assert c.status == "draft"
    assert c.id is None
    assert c.amount == 0.0
    assert c.effective_date is None


def test_map_card_uses_aliases():
    # 非首选别名也要命中
    fields = {"合同号": "N-1", "标题": "T", "委托方": "A", "受托方": "B",
              "合同生效日": "2026-01-01", "截止日期": "2026-12-31"}
    c = map_card_to_contract(fields)
    assert c.contract_no == "N-1"
    assert c.title == "T"
    assert c.party_a == "A"
    assert c.party_b == "B"
    assert c.effective_date == "2026-01-01"
    assert c.expiry_date == "2026-12-31"


def test_alias_priority_first_label_wins():
    # 多个别名同时出现时，取 FIELD_ALIASES 中最靠前的
    fields = {"合同编号": "FIRST", "合同号": "SECOND", "编号": "THIRD"}
    c = map_card_to_contract(fields)
    assert c.contract_no == "FIRST"

    fields2 = {"金额": "SECOND-LABEL", "合同金额": "111"}
    c2 = map_card_to_contract(fields2)
    assert c2.amount == 111.0


def test_missing_fields_do_not_raise():
    c = map_card_to_contract({})
    assert isinstance(c, Contract)
    assert c.contract_no == ""
    assert c.amount == 0.0
    assert c.contract_type == "tech_service"
    assert c.status == "draft"

    # 非 dict 输入也不抛
    c2 = map_card_to_contract(None)
    assert isinstance(c2, Contract)


# ---------- 金额解析多形态 ----------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("人民币 12.5 万元", 125000.0),
        ("12.5万", 125000.0),
        ("¥1,000,000", 1000000.0),
        ("￥1,000,000元", 1000000.0),
        ("1000000", 1000000.0),
        ("合同金额 5000 元", 5000.0),
        ("", 0.0),
        (None, 0.0),
        ("无", 0.0),
        (123, 123.0),
        (12.5, 12.5),
    ],
)
def test_parse_amount_forms(raw, expected):
    assert parse_amount(raw) == expected


def test_amount_missing_is_zero():
    c = map_card_to_contract({"合同编号": "X"})
    assert c.amount == 0.0


# ---------- 反向映射 / 往返 ----------

def test_map_contract_to_card_roundtrip():
    fields = {
        "合同编号": "XSZS001",
        "合同名称": "技术服务合同",
        "合同类型": "tech_service",
        "甲方": "梆梆安全",
        "乙方": "云动网络",
        "合同金额": "人民币 12.5 万元",
        "生效日期": "2026-11-01",
        "到期日期": "2027-10-31",
    }
    c = map_card_to_contract(fields)
    card = map_contract_to_card(card_contract := c)
    # 规范显示名存在且值与合同一致（amount 已归一化为数值文本）
    assert card["合同编号"] == "XSZS001"
    assert card["合同名称"] == "技术服务合同"
    assert card["甲方"] == "梆梆安全"
    assert card["乙方"] == "云动网络"
    assert card["合同金额"] == "125000.0"
    assert card["生效日期"] == "2026-11-01"
    assert card["到期日期"] == "2027-10-31"

    # 再映回 Contract，字段保持稳定
    c2 = map_card_to_contract(card)
    assert c2.contract_no == c.contract_no
    assert c2.amount == c.amount
    assert c2.party_a == c.party_a


# ---------- OA 状态 ----------

def test_map_oa_status_unavailable():
    assert map_oa_status(None) == {
        "l3_status": "unknown", "confidence": 0.0, "source": "unavailable"
    }
    assert map_oa_status({"foo": "bar"}, available=False) == {
        "l3_status": "unknown", "confidence": 0.0, "source": "unavailable"
    }
    # P1 无数据源：即便 payload 带状态字样也绝不臆造映射
    assert map_oa_status({"status": "审批中"})["l3_status"] == "unknown"


# ---------- 黄金夹具逐字段比对 ----------

def test_golden_fixture_field_by_field():
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        golden = json.load(f)

    c = map_card_to_contract(golden["main_fields"])
    expected = golden["expected_contract"]

    for key, value in expected.items():
        assert getattr(c, key) == value, f"黄金夹具字段不一致: {key}"
