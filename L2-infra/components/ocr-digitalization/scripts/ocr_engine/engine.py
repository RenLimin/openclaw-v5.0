"""
OCREngine 主类 — 统一入口

提供简洁的 API，封装：
- 后端自动发现与选择
- 图像预处理
- OCR 识别
- 后处理（排序、纠错、去重）
- 质量评分
- 多格式输出
"""
from __future__ import annotations

import os
from typing import List, Optional, Dict, Any, Union
from pathlib import Path
from PIL import Image

from .types import OCRLine, OCRPage, OCRResult, QualityScore
from .backends import OCRBackend, discover_backends, get_backend_class, list_available_backends
from .preprocess import preprocess_pipeline, generate_preprocess_variants, PreprocessConfig
from .postprocess import postprocess_lines, PostprocessConfig
from .quality import compute_quality_score
from .document import (
    pdf_to_images,
    extract_native_text,
    load_document_images,
    build_document_result,
)


class OCREngine:
    """OCR 统一引擎

    核心 API:
        engine = OCREngine(backend="auto", lang="chi_sim+eng")
        result = engine.recognize(image_path)
        result = engine.recognize_batch(paths)
        result = engine.recognize_document(pdf_path)
    """

    def __init__(
        self,
        backend: str = "auto",
        lang: str = "chi_sim+eng",
        preprocess_config: Optional[PreprocessConfig] = None,
        postprocess_config: Optional[PostprocessConfig] = None,
        multi_version: bool = True,
        quality_analysis: bool = True,
    ):
        """初始化 OCR 引擎

        Args:
            backend: 后端选择 ("auto" / "tesseract" / "rapidocr" / "paddleocr" / "easyocr")
            lang: 语言代码（用 + 分隔，如 "chi_sim+eng"）
            preprocess_config: 预处理配置（None 用默认）
            postprocess_config: 后处理配置（None 用默认）
            multi_version: 是否启用多版本预处理投票（更准但更慢）
            quality_analysis: 是否进行质量评分分析
        """
        self.backend_name = backend
        self.lang = lang
        self.multi_version = multi_version
        self.quality_analysis = quality_analysis
        self.preprocess_config = preprocess_config or PreprocessConfig()
        self.postprocess_config = postprocess_config or PostprocessConfig()

        # 后端实例（延迟加载）
        self._backends: Dict[str, OCRBackend] = {}
        self._loaded = False

    # ---- 后端管理 ----

    def load(self) -> "OCREngine":
        """加载后端引擎（显式加载，避免首次识别时等待）"""
        self._load_backends()
        return self

    def _load_backends(self) -> None:
        """加载 OCR 后端"""
        if self._loaded:
            return

        if self.backend_name == "auto":
            # 自动发现所有可用后端
            available = discover_backends(self.lang)
            for b in available:
                self._backends[b.name] = b
            if not self._backends:
                # 没有可用后端，用 MockBackend（测试用）
                raise RuntimeError(
                    "没有可用的 OCR 后端。请安装以下任一引擎：\n"
                    "  - Tesseract: brew install tesseract tesseract-lang (macOS)\n"
                    "  - RapidOCR: pip install rapidocr-onnxruntime\n"
                    "  - PaddleOCR: pip install paddleocr paddlepaddle\n"
                )
        else:
            # 指定后端
            backend_cls = get_backend_class(self.backend_name)
            if backend_cls is None:
                raise ValueError(
                    f"未知后端: {self.backend_name}, "
                    f"可用: {list_available_backends()}"
                )
            backend = backend_cls()
            if not backend.load(self.lang):
                raise RuntimeError(f"后端 {self.backend_name} 加载失败")
            self._backends[self.backend_name] = backend

        self._loaded = True

    @property
    def available_backends(self) -> List[str]:
        """已加载的后端名称列表"""
        if not self._loaded:
            self._load_backends()
        return list(self._backends.keys())

    def get_backend_info(self) -> List[dict]:
        """获取所有已加载后端的信息"""
        if not self._loaded:
            self._load_backends()
        return [b.info() for b in self._backends.values()]

    # ---- 核心识别 ----

    def recognize(
        self,
        image: Union[str, Image.Image],
        preprocess: bool = True,
    ) -> OCRResult:
        """识别单张图片

        Args:
            image: 图片路径或 PIL Image
            preprocess: 是否进行预处理

        Returns:
            OCRResult 对象（单页）
        """
        # 加载后端
        if not self._loaded:
            self._load_backends()

        # 加载图片
        if isinstance(image, str):
            img = Image.open(image).convert("RGB")
        else:
            img = image.convert("RGB")

        # 图像尺寸
        w, h = img.size

        # 预处理
        preprocess_info = {}
        if preprocess:
            processed_img, preprocess_info = preprocess_pipeline(
                img, self.preprocess_config
            )
        else:
            processed_img = img

        # 识别
        if self.multi_version and len(self._backends) >= 1:
            # 多版本 + 多引擎，取最优
            lines = self._recognize_best(processed_img)
        else:
            # 单版本，用最优后端
            best_backend = self._get_best_backend()
            raw_results = best_backend.recognize(processed_img)
            lines = self._raw_to_lines(raw_results)

        # 后处理
        lines = postprocess_lines(lines, self.postprocess_config)

        # 构建页结果
        page = OCRPage(
            page_num=1,
            lines=lines,
            width=w,
            height=h,
            is_scanned=True,
            source="ocr",
        )

        # 质量评分
        if self.quality_analysis:
            page.quality = compute_quality_score(lines, image=img)

        # 元信息
        meta = {
            "backend": self._best_backend_name or "unknown",
            "lang": self.lang,
            "preprocess": preprocess_info,
            "multi_version": self.multi_version,
        }

        result = OCRResult(pages=[page], meta=meta)
        return result

    def recognize_batch(
        self,
        image_paths: List[str],
        preprocess: bool = True,
    ) -> OCRResult:
        """批量识别多张图片

        Args:
            image_paths: 图片路径列表
            preprocess: 是否进行预处理

        Returns:
            OCRResult 对象（多页，每页对应一张图片）
        """
        pages = []
        for i, path in enumerate(image_paths):
            result = self.recognize(path, preprocess=preprocess)
            if result.pages:
                page = result.pages[0]
                page.page_num = i + 1
                # 保存源文件名
                if "source_file" not in page.quality.details:
                    page.quality.details["source_file"] = path
                pages.append(page)

        return OCRResult(
            pages=pages,
            meta={
                "batch_size": len(image_paths),
                "lang": self.lang,
            },
        )

    def recognize_document(
        self,
        doc_path: str,
        dpi: int = 300,
        native_first: bool = True,
        preprocess: bool = True,
    ) -> OCRResult:
        """识别文档（PDF 或图片）

        智能处理：
        1. 先尝试原生文本提取（PDF 可选中文字时，100%准确）
        2. 如果是扫描件，转图片后走 OCR

        Args:
            doc_path: PDF 或图片文件路径
            dpi: PDF 渲染 DPI
            native_first: 是否优先尝试原生文本提取
            preprocess: OCR 前是否预处理

        Returns:
            OCRResult 对象
        """
        ext = Path(doc_path).suffix.lower()

        # 图片直接识别
        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}:
            result = self.recognize(doc_path, preprocess=preprocess)
            result.meta["input_path"] = doc_path
            return result

        # PDF 处理
        if ext == ".pdf":
            # 尝试原生文本提取
            if native_first:
                native_pages, is_scanned = extract_native_text(doc_path)
                if not is_scanned and native_pages:
                    # 原生 PDF，直接返回
                    for page in native_pages:
                        if self.quality_analysis:
                            page.quality = compute_quality_score(
                                page.lines,
                                image_size=(page.width, page.height),
                            )
                    result = OCRResult(
                        pages=native_pages,
                        meta={
                            "input_path": doc_path,
                            "source": "native",
                            "dpi": dpi,
                            "pages": len(native_pages),
                        },
                    )
                    return result

            # 扫描件，走 OCR
            images = pdf_to_images(doc_path, dpi=dpi)
            pages = []
            for i, img in enumerate(images):
                result = self.recognize(img, preprocess=preprocess)
                if result.pages:
                    page = result.pages[0]
                    page.page_num = i + 1
                    pages.append(page)

            return OCRResult(
                pages=pages,
                meta={
                    "input_path": doc_path,
                    "source": "ocr",
                    "dpi": dpi,
                    "pages": len(pages),
                    "backend": self._best_backend_name or "unknown",
                },
            )

        raise ValueError(f"不支持的文件格式: {ext}")

    # ---- 内部方法 ----

    _best_backend_name: Optional[str] = None

    def _get_best_backend(self) -> OCRBackend:
        """获取最优后端（按 priority 排序后的第一个）"""
        if not self._backends:
            raise RuntimeError("没有可用的 OCR 后端")
        # 按 priority 排序，取第一个
        best = min(self._backends.values(), key=lambda b: b.priority)
        self._best_backend_name = best.name
        return best

    def _raw_to_lines(self, raw_results: list) -> List[OCRLine]:
        """将后端原始结果转换为 OCRLine 列表"""
        lines = []
        for item in raw_results:
            if len(item) < 3:
                continue
            bbox_points, text, conf = item[0], item[1], float(item[2])
            if not text.strip():
                continue
            # 从 4 点 bbox 计算 x1,y1,x2,y2
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            lines.append(OCRLine(
                text=text.strip(),
                bbox=bbox,
                confidence=conf,
                source="ocr",
            ))
        return lines

    def _recognize_best(self, image: Image.Image) -> List[OCRLine]:
        """多版本预处理 × 多引擎，取最优结果"""
        if self.multi_version:
            versions = generate_preprocess_variants(image)
        else:
            versions = {"default": image}

        best_result = None
        best_score = 0
        best_backend_name = None

        for vname, vimg in versions.items():
            for bname, backend in self._backends.items():
                result = backend.recognize(vimg)
                if not result:
                    continue
                score = self._score_result(result)
                if score > best_score:
                    best_score = score
                    best_result = result
                    best_backend_name = bname

        if best_backend_name:
            self._best_backend_name = best_backend_name

        if not best_result:
            return []

        return self._raw_to_lines(best_result)

    def _score_result(self, result: list) -> float:
        """对识别结果进行评分（用于多版本/多引擎选优）

        评分维度：行数 + 平均置信度 + 中文字符占比
        """
        if not result:
            return 0.0

        n = len(result)
        avg_conf = sum(float(item[2]) for item in result) / n

        all_text = "".join(item[1] for item in result)
        total_chars = len(all_text)
        cn_chars = sum(1 for c in all_text if '\u4e00' <= c <= '\u9fff')
        cn_ratio = cn_chars / max(total_chars, 1)

        # 评分公式
        score = n * 10 + avg_conf * 50 + cn_ratio * 30
        return score


# ============================================================
# 便捷函数
# ============================================================

def ocr_image(image_path: str, backend: str = "auto", lang: str = "chi_sim+eng") -> OCRResult:
    """便捷函数：识别单张图片"""
    engine = OCREngine(backend=backend, lang=lang)
    return engine.recognize(image_path)


def ocr_pdf(pdf_path: str, backend: str = "auto", lang: str = "chi_sim+eng",
            dpi: int = 300) -> OCRResult:
    """便捷函数：识别 PDF 文档"""
    engine = OCREngine(backend=backend, lang=lang)
    return engine.recognize_document(pdf_path, dpi=dpi)


def digitalize_document(
    path: str,
    output_path: Optional[str] = None,
    backend: str = "auto",
    lang: str = "chi_sim+eng",
    dpi: int = 300,
    format: str = "markdown",
) -> OCRResult:
    """文档数字化便捷入口（与原 skill API 兼容）

    Args:
        path: 输入文件路径（PDF 或图片）
        output_path: 输出文件路径（可选）
        backend: OCR 后端
        lang: 语言
        dpi: PDF 渲染 DPI
        format: 输出格式（text/markdown/json）

    Returns:
        OCRResult 对象
    """
    engine = OCREngine(backend=backend, lang=lang)
    result = engine.recognize_document(path, dpi=dpi)

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        if format == "text":
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result.to_text())
        elif format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result.to_json())
        else:  # markdown
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result.to_markdown())

    return result
