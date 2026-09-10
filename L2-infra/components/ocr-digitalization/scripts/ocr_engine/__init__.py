"""
OCR 文档数字化组件 (OCR-001) — L2 基础设施层

统一入口:
    from ocr_engine import OCREngine, OCRResult, OCRLine, OCRPage, QualityScore

    engine = OCREngine(backend="auto", lang="chi_sim+eng")
    result = engine.recognize(image_path)
    result = engine.recognize_document(pdf_path, dpi=300)
    result = engine.recognize_batch([path1, path2])

输出格式:
    result.text           # 纯文本
    result.to_markdown()  # Markdown
    result.to_json()      # JSON
    result.lines          # 行级结果（含坐标、置信度）
    result.confidence     # 平均置信度
    result.quality_score  # 质量评分
"""
from .types import OCRLine, OCRPage, OCRResult, QualityScore
from .engine import OCREngine, ocr_image, ocr_pdf, digitalize_document
from .preprocess import PreprocessConfig, preprocess_pipeline, generate_preprocess_variants
from .postprocess import PostprocessConfig, postprocess_lines, sort_lines_reading_order
from .quality import compute_quality_score, estimate_image_clarity
from .document import pdf_to_images, extract_native_text, list_input_files

__version__ = "2.0.0"
__all__ = [
    # 核心
    "OCREngine",
    "OCRResult",
    "OCRPage",
    "OCRLine",
    "QualityScore",
    # 便捷函数
    "ocr_image",
    "ocr_pdf",
    "digitalize_document",
    # 预处理
    "PreprocessConfig",
    "preprocess_pipeline",
    "generate_preprocess_variants",
    # 后处理
    "PostprocessConfig",
    "postprocess_lines",
    "sort_lines_reading_order",
    # 质量
    "compute_quality_score",
    "estimate_image_clarity",
    # 文档
    "pdf_to_images",
    "extract_native_text",
    "list_input_files",
]
