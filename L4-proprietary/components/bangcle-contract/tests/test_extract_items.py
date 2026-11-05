"""extract_line_items 单测。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import _bootstrap  # noqa: F401

from contract_management.contract_parser import parse_contract
from contract_review.extract_items import extract_line_items


def _p(text):
    p = parse_contract(text)
    p.raw_text = text
    return p


class TestExtractItems(unittest.TestCase):
    def test_enum_dot(self):
        text = "服务合同\n甲方：甲\n乙方：梆梆\n第一条 服务内容\n1. 梆梆加固V5.0，单价10万元\n2. 渠道监测V2.1，单价50000元\n"
        items = extract_line_items(text, _p(text))
        self.assertEqual(len(items), 2)
        self.assertIn("梆梆加固", items[0].raw_name)
        self.assertEqual(items[0].price, 100000.0)
        self.assertEqual(items[1].price, 50000.0)

    def test_wan_conversion(self):
        text = "合同\n甲方：甲\n乙方：乙\n服务内容：梆梆加固V5.0，单价：3万元"
        items = extract_line_items(text, _p(text))
        self.assertTrue(any(i.price == 30000.0 for i in items))

    def test_model(self):
        text = "合同\n甲方：甲\n乙方：乙\n服务内容：梆梆加固 V5.0"
        items = extract_line_items(text, _p(text))
        self.assertTrue(any(i.model == "5.0" for i in items))

    def test_ocr_bare_number(self):
        text = "合同\n甲方：甲\n乙方：乙\n采购内容\n1全渠道应用安全监测软件V6.0单价100000元\n"
        items = extract_line_items(text, _p(text))
        self.assertTrue(any("全渠道" in i.raw_name for i in items))

    def test_dedup(self):
        text = "合同\n甲方：甲\n乙方：乙\n服务内容：梆梆加固V5.0\n服务内容：梆梆加固V5.0"
        items = extract_line_items(text, _p(text))
        names = [i.raw_name for i in items]
        self.assertEqual(len(names), len(set(n.lower() for n in names)))

    def test_no_items(self):
        text = "纯粹的框架协议\n甲方：甲公司\n乙方：乙公司\n双方本着友好原则合作。"
        items = extract_line_items(text, _p(text))
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
