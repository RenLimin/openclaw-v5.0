"""AC-7 金额中文大写黄金基准。"""
import pytest

import contract_management as cm


@pytest.mark.parametrize("amount,expected", [
    (0, "零元整"),
    (105, "壹佰零伍元整"),
    (10000, "壹万元整"),
    (12345.67, "壹万贰仟叁佰肆拾伍元陆角柒分"),
    (100.05, "壹佰元零伍分"),
    (200000000, "贰亿元整"),
    (-50, "负伍拾元整"),
])
def test_amount_to_chinese(amount, expected):
    assert cm.amount_to_chinese(amount) == expected


def test_round_amounts_no_trailing_zero_branch():
    # 触发末尾"零"裁剪分支：如 1010 等
    assert cm.amount_to_chinese(1010) == "壹仟零壹拾元整"


def test_single_zero_position():
    assert cm.amount_to_chinese(100) == "壹佰元整"


@pytest.mark.parametrize("amount,expected", [
    (1.1, "壹元壹角"),
    (0.05, "零元伍分"),
    (1.2, "壹元贰角"),
])
def test_decimal_branches(amount, expected):
    assert cm.amount_to_chinese(amount) == expected
