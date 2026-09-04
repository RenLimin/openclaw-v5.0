"""
兼容层：OCR 后端代码已迁移到 skills/ocr-digitalization/scripts/ocr_backends.py
此文件仅做 re-export，保持向后兼容。
"""
import os
import sys

# 添加 ocr-digitalization scripts 路径
_ocr_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ocr-digitalization', 'scripts')
if _ocr_dir not in sys.path:
    sys.path.insert(0, _ocr_dir)

# re-export 公共 API
from ocr_backends import (
    OCRBackend,
    RapidOCRBackend,
    PaddleOCRBackend,
    preprocess_image,
    correct_ocr_errors,
    sort_text_lines,
    pdf_to_images,
    PageResult,
    OCRResult,
    ContractOCR,
    digitalize_document,
)

__all__ = [
    'OCRBackend', 'RapidOCRBackend', 'PaddleOCRBackend',
    'preprocess_image', 'correct_ocr_errors', 'sort_text_lines',
    'pdf_to_images', 'PageResult', 'OCRResult', 'ContractOCR',
    'digitalize_document',
]
