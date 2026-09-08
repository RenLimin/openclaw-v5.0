"""
统一工厂测试 — 至少 3 个用例。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from office_engine.factory import OfficeDocument
from office_engine.ppt_engine import PPTDocument
from office_engine.exceptions import OfficeFormatError

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_create_by_type_ppt():
    """测试：按类型创建 PPT。"""
    doc = OfficeDocument.create("ppt")
    assert isinstance(doc, PPTDocument)
    assert doc.format == "pptx"
    doc.close()


def test_open_by_path_pptx():
    """测试：按路径打开 pptx 文件（自动识别格式）。"""
    # 先创建一个测试文件
    ppt = PPTDocument()
    ppt.add_slide("blank")
    test_path = os.path.join(OUTPUT_DIR, "factory_test_input.pptx")
    ppt.save(test_path)
    ppt.close()

    # 用工厂打开
    doc = OfficeDocument.open(test_path)
    assert isinstance(doc, PPTDocument)
    assert doc.slide_count() >= 1
    doc.close()


def test_detect_format():
    """测试：格式识别。"""
    assert OfficeDocument.detect_format("report.docx") == "word"
    assert OfficeDocument.detect_format("data.xlsx") == "excel"
    assert OfficeDocument.detect_format("deck.pptx") == "ppt"
    assert OfficeDocument.detect_format("notes.txt") == ""
    assert OfficeDocument.detect_format("no_extension") == ""


def test_create_unknown_type_raises():
    """测试：未知类型抛异常。"""
    with pytest.raises(OfficeFormatError):
        OfficeDocument.create("pdf")


def test_open_nonexistent_file():
    """测试：打开不存在的文件抛异常。"""
    with pytest.raises(FileNotFoundError):
        OfficeDocument.open("/nonexistent/path.pptx")


def test_create_with_path():
    """测试：创建时带 path（打开已有文件）。"""
    # 创建测试文件
    ppt = PPTDocument()
    ppt.add_slide("blank")
    test_path = os.path.join(OUTPUT_DIR, "factory_with_path.pptx")
    ppt.save(test_path)
    ppt.close()

    doc = OfficeDocument.create("ppt", test_path)
    assert isinstance(doc, PPTDocument)
    assert doc.slide_count() >= 1
    doc.close()
