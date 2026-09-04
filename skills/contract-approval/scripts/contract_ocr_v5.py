"""
兼容层：OCR 核心代码已迁移到 skills/ocr-digitalization/scripts/ocr_engine.py
此文件仅做 re-export，保持向后兼容。
"""
import os
import sys

# 添加 ocr-digitalization scripts 路径
_ocr_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ocr-digitalization', 'scripts')
if _ocr_dir not in sys.path:
    sys.path.insert(0, _ocr_dir)

# re-export 公共 API
from ocr_engine import (
    OCRLine,
    SignatureRegion,
    PageResult,
    OCRResultV5,
    extract_native_text,
    detect_signature_page_v2,
    detect_red_seals,
    detect_signatures,
    pdf_to_images,
    ocr_image,
    sort_lines_reading_order,
    correct_contract_text,
    digitalize_document_v5,
)

__all__ = [
    'OCRLine', 'SignatureRegion', 'PageResult', 'OCRResultV5',
    'extract_native_text', 'detect_signature_page_v2',
    'detect_red_seals', 'detect_signatures',
    'pdf_to_images', 'ocr_image', 'sort_lines_reading_order',
    'correct_contract_text', 'digitalize_document_v5',
]
