"""E2E：真实文件（docx / txt / 扫描 PNG）走完整管线，断言黄金契约。

2026-11-05 合并 sandbox 测试时适配主仓库 API：
- r.matches 是 List[KbMatchResult]（字段 input_name/product/sku/alert），
  满足度在 r.satisfaction（来自 kb.satisfaction）；
- 报告免责声明来自 contract_review.report.DISCLAIMER（主仓库版）；
- 持久化回查用 r.repo_review_id（int，主仓库 Repository 主键）。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import _bootstrap  # noqa: F401

from contract_review.pipeline import ReviewService
from contract_review.report import DISCLAIMER
from contract_management.risk_engine import CHECK_RULES

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
DOCX = os.path.join(FIX, "sample_contract.docx")
TXT = os.path.join(FIX, "sample_contract.txt")
PNG = os.path.join(FIX, "scan_contract.png")


class TestDocx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.svc = ReviewService()

    def tearDown(self):
        self.svc.close()

    def test_docx_full(self):
        r = self.svc.review_file(DOCX, out_dir=self.tmp, formats=("md", "xlsx"))
        # 黄金：rule_id 集合 100% == L3 受控规则库
        got = sorted(f["id"] for f in r.risk["findings"])
        want = sorted(x.id for x in CHECK_RULES)
        self.assertEqual(got, want)
        # 免责声明 + 报告文件
        self.assertTrue(os.path.isfile(r.report_md_path))
        self.assertTrue(os.path.isfile(r.report_xlsx_path))
        with open(r.report_md_path, encoding="utf-8") as fh:
            md = fh.read()
        self.assertIn(DISCLAIMER, md)
        # 持久化可回查（主仓库 Repository 主键）
        self.assertIsNotNone(self.svc.repo.get_review(r.repo_review_id))


class TestTxtContractBoundary(unittest.TestCase):
    """txt/md 支持是 sandbox MVP 的未获批范围。

    主仓库 DESIGN-DETAIL §191 明确本期格式 = pdf/docx/image；
    tests/unit/test_ingest.py::test_detect_file_type 已断言 txt 被拒。
    合并时以主仓库已批准契约为准，此测试锁定该边界（防止回归）。
    """

    def test_txt_rejected(self):
        from contract_review.ingest import ingest_file, IngestError
        with self.assertRaises(IngestError):
            ingest_file(TXT)


class TestScanPng(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.svc = ReviewService()

    def tearDown(self):
        self.svc.close()

    @unittest.skipUnless(
        os.path.isfile(PNG), "scan_contract.png 夹具缺失")
    def test_png_ocr_pipeline(self):
        r = self.svc.review_file(PNG, out_dir=self.tmp, formats=("md",))
        # OCR 后至少识别出标的名称
        names = [m.input_name for m in r.matches]
        self.assertTrue(any("全渠道" in n for n in names), names)


class TestAppendOnly(unittest.TestCase):
    def test_no_update_delete_methods(self):
        svc = ReviewService()
        for forbidden in ("update_review", "delete_review", "update", "delete"):
            self.assertFalse(hasattr(svc.repo, forbidden), forbidden)
        svc.close()


if __name__ == "__main__":
    unittest.main()
