import pytest
"""
测试 1: 数据模型序列化/反序列化

覆盖：OCRLine / QualityScore / OCRPage / OCRResult
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from ocr_engine.types import OCRLine, OCRPage, OCRResult, QualityScore


class TestOCRLine:
    def test_creation(self):
        line = OCRLine(text="测试文字", bbox=(10, 20, 100, 40), confidence=0.9)
        assert line.text == "测试文字"
        assert line.bbox == (10, 20, 100, 40)
        assert line.confidence == 0.9
        assert line.source == "ocr"

    def test_properties(self):
        line = OCRLine(text="test", bbox=(10, 20, 100, 45))
        assert line.x1 == 10
        assert line.y1 == 20
        assert line.x2 == 100
        assert line.y2 == 45
        assert line.width == 90
        assert line.height == 25

    def test_to_dict(self):
        line = OCRLine(text="test", bbox=(1, 2, 3, 4), confidence=0.8, source="native")
        d = line.to_dict()
        assert d["text"] == "test"
        assert d["bbox"] == [1, 2, 3, 4]
        assert d["confidence"] == 0.8
        assert d["source"] == "native"

    def test_from_dict(self):
        d = {"text": "hello", "bbox": [5, 10, 200, 30], "confidence": 0.95, "source": "ocr"}
        line = OCRLine.from_dict(d)
        assert line.text == "hello"
        assert line.bbox == (5, 10, 200, 30)
        assert line.confidence == 0.95

    def test_roundtrip(self):
        original = OCRLine(text="中文测试123", bbox=(10.5, 20.3, 100.7, 45.2), confidence=0.87)
        d = original.to_dict()
        restored = OCRLine.from_dict(d)
        assert restored.text == original.text
        assert restored.confidence == original.confidence
        assert restored.source == original.source
        assert restored.bbox == original.bbox


class TestQualityScore:
    def test_default_values(self):
        q = QualityScore()
        assert q.overall == 0.0
        assert q.confidence == 0.0
        assert q.clarity == 0.0

    def test_grade_a(self):
        q = QualityScore(overall=95.0)
        assert q.grade == "A"

    def test_grade_b(self):
        q = QualityScore(overall=80.0)
        assert q.grade == "B"

    def test_grade_c(self):
        q = QualityScore(overall=65.0)
        assert q.grade == "C"

    def test_grade_f(self):
        q = QualityScore(overall=30.0)
        assert q.grade == "F"

    def test_to_dict_from_dict(self):
        q = QualityScore(
            overall=85.5, confidence=90.0, clarity=80.0,
            text_density=75.0, layout_completeness=82.0,
            details={"num_lines": 100},
        )
        d = q.to_dict()
        q2 = QualityScore.from_dict(d)
        assert q2.overall == 85.5
        assert q2.confidence == 90.0
        assert q2.details["num_lines"] == 100
        assert q2.grade == "B"


class TestOCRPage:
    def test_empty_page(self):
        page = OCRPage(page_num=1)
        assert page.text == ""
        assert page.confidence == 0.0
        assert page.total_chars == 0

    def test_page_with_lines(self):
        lines = [
            OCRLine(text="第一行", bbox=(0, 0, 100, 20), confidence=0.9),
            OCRLine(text="第二行", bbox=(0, 30, 100, 50), confidence=0.8),
        ]
        page = OCRPage(page_num=1, lines=lines, width=600, height=800)
        assert page.text == "第一行\n第二行"
        assert page.confidence == pytest.approx(0.85)
        assert page.total_chars == 6

    def test_to_dict_from_dict(self):
        page = OCRPage(
            page_num=3,
            lines=[
                OCRLine(text="test1", bbox=(1, 2, 3, 4), confidence=0.9),
                OCRLine(text="test2", bbox=(5, 6, 7, 8), confidence=0.8),
            ],
            width=800,
            height=1000,
            is_scanned=True,
            source="ocr",
            quality=QualityScore(overall=80.0, confidence=90.0),
        )
        d = page.to_dict()
        page2 = OCRPage.from_dict(d)
        assert page2.page_num == 3
        assert len(page2.lines) == 2
        assert page2.lines[0].text == "test1"
        assert page2.width == 800
        assert page2.is_scanned is True
        assert page2.quality.overall == 80.0


class TestOCRResult:
    def test_empty_result(self):
        result = OCRResult()
        assert result.total_pages == 0
        assert result.total_lines == 0
        assert result.total_chars == 0
        assert result.confidence == 0.0
        assert result.text == ""

    def test_single_page(self):
        lines = [OCRLine(text="hello", bbox=(0, 0, 50, 20), confidence=0.9)]
        page = OCRPage(page_num=1, lines=lines, width=100, height=100)
        result = OCRResult(pages=[page])
        assert result.total_pages == 1
        assert result.total_lines == 1
        assert result.confidence == 0.9
        assert "hello" in result.text

    def test_multi_page_text(self):
        pages = [
            OCRPage(page_num=1, lines=[OCRLine(text="页一", bbox=(0, 0, 50, 20))]),
            OCRPage(page_num=2, lines=[OCRLine(text="页二", bbox=(0, 0, 50, 20))]),
        ]
        result = OCRResult(pages=pages)
        assert "第 1 页" in result.text
        assert "第 2 页" in result.text
        assert result.total_pages == 2

    def test_to_markdown(self):
        lines = [OCRLine(text="test", bbox=(0, 0, 50, 20), confidence=0.9)]
        page = OCRPage(page_num=1, lines=lines, quality=QualityScore(overall=85.0))
        result = OCRResult(pages=[page])
        md = result.to_markdown()
        assert "# OCR" in md
        assert "## 第 1 页" in md
        assert "test" in md

    def test_json_roundtrip(self):
        result = OCRResult(
            pages=[
                OCRPage(
                    page_num=1,
                    lines=[OCRLine(text="hello", bbox=(1, 2, 3, 4), confidence=0.9)],
                    width=100, height=200, is_scanned=True, source="ocr",
                    quality=QualityScore(overall=75.0, confidence=80.0),
                ),
            ],
            meta={"engine": "test", "dpi": 300},
        )
        json_str = result.to_json()
        result2 = OCRResult.from_json(json_str)
        assert result2.total_pages == 1
        assert result2.pages[0].lines[0].text == "hello"
        assert result2.meta["engine"] == "test"
        assert result2.confidence == 0.9

    def test_to_dict_summary(self):
        lines = [OCRLine(text="a" * 10, bbox=(0, 0, 50, 20), confidence=0.8)]
        page = OCRPage(page_num=1, lines=lines, quality=QualityScore(overall=70.0))
        result = OCRResult(pages=[page])
        d = result.to_dict()
        assert "summary" in d
        assert d["summary"]["total_pages"] == 1
        assert d["summary"]["total_lines"] == 1
        assert d["summary"]["total_chars"] == 10
        assert d["summary"]["confidence"] == 0.8
