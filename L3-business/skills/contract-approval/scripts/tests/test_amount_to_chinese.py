#!/usr/bin/env python3
"""
测试 amount_to_chinese 金额大写转换函数
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contract_gen import amount_to_chinese


class TestAmountToChinese(unittest.TestCase):
    """金额大写转换测试"""

    def test_zero(self):
        """零元"""
        self.assertEqual(amount_to_chinese(0), "零元整")

    def test_wan_exact(self):
        """整万"""
        self.assertEqual(amount_to_chinese(10000), "壹万元整")
        self.assertEqual(amount_to_chinese(50000), "伍万元整")

    def test_shi_wan_bug(self):
        """整十万 - bug 用例：原函数会漏掉'万'字"""
        self.assertEqual(amount_to_chinese(100000), "壹拾万元整")

    def test_er_shi_wan(self):
        """贰拾伍万"""
        self.assertEqual(amount_to_chinese(250000), "贰拾伍万元整")

    def test_bai_wan_bug(self):
        """整百万 - bug 用例：原函数会漏掉'万'字"""
        self.assertEqual(amount_to_chinese(1000000), "壹佰万元整")

    def test_qian_wan(self):
        """整千万"""
        self.assertEqual(amount_to_chinese(10000000), "壹仟万元整")

    def test_decimal(self):
        """带小数"""
        self.assertEqual(amount_to_chinese(12345.67), "壹万贰仟叁佰肆拾伍元陆角柒分")

    def test_max_eight_digits(self):
        """最大8位整数+两位小数"""
        self.assertEqual(amount_to_chinese(99999999.99),
                         "玖仟玖佰玖拾玖万玖仟玖佰玖拾玖元玖角玖分")

    def test_jiao_only(self):
        """只有角"""
        self.assertEqual(amount_to_chinese(0.5), "伍角")

    def test_fen_only(self):
        """只有分"""
        self.assertEqual(amount_to_chinese(0.05), "伍分")

    def test_middle_zero(self):
        """中间零"""
        self.assertEqual(amount_to_chinese(101), "壹佰零壹元整")
        self.assertEqual(amount_to_chinese(1001), "壹仟零壹元整")
        self.assertEqual(amount_to_chinese(10001), "壹万零壹元整")
        self.assertEqual(amount_to_chinese(100001), "壹拾万零壹元整")
        self.assertEqual(amount_to_chinese(1000001), "壹佰万零壹元整")

    def test_yi_level(self):
        """亿级"""
        self.assertEqual(amount_to_chinese(100000000), "壹亿元整")
        self.assertEqual(amount_to_chinese(100000001), "壹亿零壹元整")
        self.assertEqual(amount_to_chinese(123456789.12),
                         "壹亿贰仟叁佰肆拾伍万陆仟柒佰捌拾玖元壹角贰分")

    def test_wan_level_zero_in_middle(self):
        """万级中间零"""
        self.assertEqual(amount_to_chinese(1050000), "壹佰零伍万元整")
        self.assertEqual(amount_to_chinese(10050000), "壹仟零伍万元整")

    def test_decimal_with_jiao_zero(self):
        """整数+零角+分"""
        self.assertEqual(amount_to_chinese(100.5), "壹佰元伍角")
        self.assertEqual(amount_to_chinese(100.05), "壹佰元零伍分")


if __name__ == "__main__":
    unittest.main(verbosity=2)
