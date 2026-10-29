"""P2：PDF/docx 直读 + 扫描件真实 OCR。"""

import pytest

from file_fixtures import (
    make_native_pdf,
    make_docx,
    make_text_image,
    make_scanned_pdf,
)
from contract_review.digitize import (
    DigitizedText,
    digitize,
    read_pdf_text,
    read_docx_text,
    OCRAdapter,
    DigitizeError,
)


def test_native_pdf_direct_read(tmp_path):
    pdf = make_native_pdf(str(tmp_path / "native.pdf"))
    result = digitize(pdf)
    assert isinstance(result, DigitizedText)
    assert result.method == "native_pdf"
    assert "CONTRACT NATIVE TEXT 2026" in result.full_text
    assert result.ocr_confidence is None


def test_read_pdf_text_helper(tmp_path):
    pdf = make_native_pdf(str(tmp_path / "n.pdf"))
    assert "CONTRACT NATIVE TEXT 2026" in read_pdf_text(pdf)


def test_docx_direct_read(tmp_path):
    docx_path = make_docx(str(tmp_path / "c.docx"))
    result = digitize(docx_path)
    assert result.method == "docx"
    assert "技术服务合同 DOCX NATIVE" in result.full_text
    # 表格文本真实读出
    assert "安全测评服务" in result.full_text
    assert "10000" in result.full_text


def test_read_docx_text_helper(tmp_path):
    docx_path = make_docx(str(tmp_path / "c.docx"))
    text = read_docx_text(docx_path)
    assert "技术服务合同 DOCX NATIVE" in text


def test_image_real_ocr(tmp_path):
    image = make_text_image(str(tmp_path / "scan.png"))
    result = digitize(image)
    assert result.method == "ocr"
    # 真实 OCR 能识别出生成图中的英文文字
    assert "CONTRACT" in result.full_text.upper()
    assert "2026" in result.full_text
    assert result.ocr_confidence is not None
    assert 0.0 < result.ocr_confidence <= 1.0


def test_scanned_pdf_falls_back_to_ocr(tmp_path):
    pdf = make_scanned_pdf(str(tmp_path / "scanned.pdf"))
    # 无文本层：pypdf 直读为空
    assert read_pdf_text(pdf) == ""
    result = digitize(pdf)
    assert result.method == "ocr"
    assert "CONTRACT" in result.full_text.upper()


def test_digitize_missing_file_raises(tmp_path):
    with pytest.raises(DigitizeError):
        digitize(str(tmp_path / "nope.pdf"))


def test_ocr_adapter_bad_scripts_dir(tmp_path):
    adapter = OCRAdapter(l2_scripts_dir=str(tmp_path / "no-such-dir"))
    image = make_text_image(str(tmp_path / "x.png"))
    with pytest.raises(DigitizeError):
        adapter.recognize(image)
