"""
格式转换测试 — 可用性检测 + 格式识别。
不强求真转 PDF，LibreOffice 不可用时跳过转换测试。
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from office_engine.converter import OfficeConverter
from office_engine.ppt_engine import PPTDocument
from office_engine.exceptions import OfficeUnsupportedError

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_is_available_returns_bool():
    """测试：is_available 返回布尔值。"""
    result = OfficeConverter.is_available()
    assert isinstance(result, bool)


def test_detect_format_pptx():
    """测试：检测 pptx 格式。"""
    # 创建测试文件
    ppt = PPTDocument()
    test_path = os.path.join(OUTPUT_DIR, "converter_test_input.pptx")
    ppt.save(test_path)
    ppt.close()

    assert OfficeConverter.detect_format(test_path) == "pptx"


def test_detect_format_nonexistent():
    """测试：不存在的文件返回空。"""
    assert OfficeConverter.detect_format("/nonexistent/file.pptx") == ""


def test_detect_format_unsupported_extension():
    """测试：不支持的扩展名返回空。"""
    # 创建一个假文件
    fake_path = os.path.join(OUTPUT_DIR, "fake.txt")
    with open(fake_path, "w") as f:
        f.write("not an office file")
    assert OfficeConverter.detect_format(fake_path) == ""


@pytest.mark.skipif(
    not OfficeConverter.is_available(),
    reason="LibreOffice not available"
)
def test_to_pdf_actual_conversion():
    """测试：实际 PDF 转换（仅 LibreOffice 可用时执行）。"""
    # 创建 PPT
    ppt = PPTDocument()
    slide = ppt.add_slide("title")
    ppt.set_slide_title(slide, "PDF 转换测试")
    input_path = os.path.join(OUTPUT_DIR, "pdf_test_input.pptx")
    ppt.save(input_path)
    ppt.close()

    output_path = os.path.join(OUTPUT_DIR, "pdf_test_output.pdf")
    result = OfficeConverter.to_pdf(input_path, output_path)
    assert result == output_path
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0


def test_to_pdf_unavailable_raises(monkeypatch):
    """测试：LibreOffice 不可用时抛 OfficeUnsupportedError。"""
    # 强制设置为不可用
    monkeypatch.setattr(OfficeConverter, "_soffice_path", None)
    monkeypatch.setattr(
        OfficeConverter, "is_available",
        classmethod(lambda cls: False)
    )

    # 创建假文件
    fake_pptx = os.path.join(OUTPUT_DIR, "fake_unavailable.pptx")
    ppt = PPTDocument()
    ppt.save(fake_pptx)
    ppt.close()

    with pytest.raises(OfficeUnsupportedError):
        OfficeConverter.to_pdf(fake_pptx)
