"""
文档级处理

处理多页文档（PDF、多图目录），提供：
- PDF 转图片（多种后端自动选择）
- 多页文档的 OCR 结果合并与组织
- 原生 PDF 文本提取优先（非扫描件直接抽文字）
- 批量目录处理
"""
from __future__ import annotations

import os
import re
import tempfile
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path
from PIL import Image

from .types import OCRLine, OCRPage, OCRResult


# ============================================================
# PDF 转图片
# ============================================================

def pdf_to_images(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
    """PDF 转高分辨率图片

    自动选择可用的后端（按优先级）：
    1. PyMuPDF（fitz） — 最快，像素与 DPI 严格对应
    2. pdf2image（poppler）
    3. macOS sips + PyPDF2 — 无额外依赖（macOS 自带）

    Args:
        pdf_path: PDF 文件路径
        dpi: 渲染 DPI

    Returns:
         PIL Image 列表（按页码顺序）

    Raises:
        RuntimeError: 所有后端都不可用
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

    # 1. PyMuPDF（优先，最准确）
    try:
        import pymupdf
        doc = pymupdf.open(pdf_path)
        images = []
        zoom = dpi / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
        doc.close()
        if images:
            return images
    except ImportError:
        pass
    except Exception:
        pass

    # 2. pdf2image
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=dpi)
        if images:
            return images
    except ImportError:
        pass
    except Exception:
        pass

    # 3. macOS sips + PyPDF2
    try:
        from PyPDF2 import PdfReader, PdfWriter
        reader = PdfReader(pdf_path)
        images = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            for i in range(len(reader.pages)):
                writer = PdfWriter()
                writer.add_page(reader.pages[i])
                single_pdf = os.path.join(tmp_dir, f"page_{i+1:04d}.pdf")
                with open(single_pdf, "wb") as f:
                    writer.write(f)

                out_png = os.path.join(tmp_dir, f"page_{i+1:04d}.png")
                import subprocess
                r = subprocess.run(
                    ["sips", "-s", "format", "png",
                     "-s", "dpiHeight", str(dpi),
                     "-s", "dpiWidth", str(dpi),
                     single_pdf, "--out", out_png],
                    capture_output=True, text=True
                )
                if os.path.exists(out_png):
                    images.append(Image.open(out_png).copy())
        if images:
            return images
    except (ImportError, FileNotFoundError):
        pass
    except Exception:
        pass

    raise RuntimeError(
        "无法将 PDF 转图片，请安装以下任一依赖：\n"
        "  - PyMuPDF (推荐): pip install pymupdf\n"
        "  - pdf2image: pip install pdf2image (需系统安装 poppler)\n"
        "  - macOS: 系统自带 sips + PyPDF2"
    )


# ============================================================
# 原生 PDF 文本提取
# ============================================================

def extract_native_text(pdf_path: str) -> Tuple[List[OCRPage], bool]:
    """尝试用 PyMuPDF 提取原生文本

    对于非扫描件 PDF（可选中文字的那种），直接提取原生文本准确率 100%，
    比 OCR 快得多也准得多。

    Args:
        pdf_path: PDF 文件路径

    Returns:
        (pages, is_scanned)
        - pages: 提取结果列表（如果是扫描件则为空）
        - is_scanned: 是否为扫描件（原生文本不足则为 True）
    """
    try:
        import pymupdf
    except ImportError:
        return [], True

    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return [], True

    pages = []
    total_chars = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("blocks")
        lines = []

        for block in blocks:
            if len(block) < 5:
                continue
            x0, y0, x1, y1, block_text = block[:5]
            if not block_text.strip():
                continue

            # 按行拆分
            for line_text in block_text.strip().split('\n'):
                line_text = line_text.strip()
                if not line_text:
                    continue
                lines.append(OCRLine(
                    text=line_text,
                    bbox=(float(x0), float(y0), float(x1), float(y1)),
                    confidence=1.0,
                    source="native",
                ))
                total_chars += len(line_text)

        pages.append(OCRPage(
            page_num=page_num + 1,
            lines=lines,
            width=int(page.rect.width),
            height=int(page.rect.height),
            is_scanned=False,
            source="native",
        ))

    doc.close()

    # 判断是否是扫描件：每页平均字符数少于 50 认为是扫描件
    avg_chars = total_chars / max(1, len(pages))
    is_scanned = avg_chars < 50

    if is_scanned:
        return [], True

    return pages, False


# ============================================================
# 批量目录处理
# ============================================================

SUPPORTED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
SUPPORTED_DOC_EXT = {".pdf"}


def list_input_files(input_path: str) -> List[str]:
    """列出输入路径下的所有待处理文件

    支持：
    - 单个文件（图片或 PDF）
    - 目录（递归扫描所有支持的文件）

    Args:
        input_path: 文件或目录路径

    Returns:
        文件路径列表（绝对路径）
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"路径不存在: {input_path}")

    if path.is_file():
        return [str(path.resolve())]

    # 目录：收集所有支持的文件
    files = []
    for ext in sorted(SUPPORTED_IMAGE_EXT | SUPPORTED_DOC_EXT):
        files.extend(sorted(path.rglob(f"*{ext}")))
        files.extend(sorted(path.rglob(f"*{ext.upper()}")))

    return [str(f.resolve()) for f in files]


def load_image_file(file_path: str) -> Image.Image:
    """加载图片文件"""
    return Image.open(file_path).convert("RGB")


def load_document_images(file_path: str, dpi: int = 300) -> List[Image.Image]:
    """加载文档为图片列表

    如果是图片文件，返回单元素列表；
    如果是 PDF，返回所有页面的图片。
    """
    ext = Path(file_path).suffix.lower()
    if ext in SUPPORTED_IMAGE_EXT:
        return [load_image_file(file_path)]
    elif ext in SUPPORTED_DOC_EXT:
        return pdf_to_images(file_path, dpi=dpi)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


# ============================================================
# 文档结果组装
# ============================================================

def build_document_result(
    pages: List[OCRPage],
    meta: Optional[Dict[str, Any]] = None,
) -> OCRResult:
    """组装文档级 OCR 结果"""
    return OCRResult(
        pages=pages,
        meta=meta or {},
    )


def merge_results(results: List[OCRResult]) -> OCRResult:
    """合并多个 OCRResult（批量处理时用）"""
    all_pages = []
    all_meta = {"merged_results": len(results)}

    page_offset = 0
    for i, result in enumerate(results):
        for page in result.pages:
            new_page = OCRPage(
                page_num=page.page_num + page_offset,
                lines=page.lines,
                width=page.width,
                height=page.height,
                is_scanned=page.is_scanned,
                source=page.source,
                quality=page.quality,
            )
            all_pages.append(new_page)
        page_offset += len(result.pages)
        all_meta[f"result_{i}_meta"] = result.meta

    return OCRResult(pages=all_pages, meta=all_meta)
