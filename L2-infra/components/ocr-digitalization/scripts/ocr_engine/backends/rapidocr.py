"""
RapidOCR 后端（默认主引擎）

基于 ONNXRuntime 的轻量级 OCR 引擎，纯 CPU 运行。
优点：速度快、无重依赖、中文精度不错
缺点：精度略低于 PaddleOCR
"""
from __future__ import annotations

from typing import List, Tuple
from PIL import Image
import numpy as np

from .base import OCRBackend


class RapidOCRBackend(OCRBackend):
    """RapidOCR 后端（默认主引擎）"""

    name = "rapidocr"
    priority = 20  # 次高优先级（默认主引擎，轻量快速）
    supports_languages = ["ch", "en", "ch+en"]

    def load(self, lang: str = "chi_sim+eng") -> bool:
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
            self._lang = lang
            self._loaded = True
            return True
        except Exception:
            self._loaded = False
            return False

    def recognize(self, image: Image.Image) -> List[Tuple]:
        if not self._loaded:
            return []

        try:
            result, _ = self._ocr(np.array(image.convert("RGB")))
        except Exception:
            return []

        if not result:
            return []

        out = []
        for item in result:
            # RapidOCR 返回: [box, text, confidence]
            if len(item) < 3:
                continue
            box = item[0]
            text = item[1]
            conf = float(item[2])
            if not text.strip():
                continue
            # 统一 bbox 格式: [[x,y], [x,y], [x,y], [x,y]]
            # RapidOCR 可能返回 4 个点（列表）
            if isinstance(box, (list, tuple)) and len(box) == 4:
                bbox_float = [[float(p[0]), float(p[1])] for p in box]
            elif isinstance(box, (list, tuple)) and len(box) == 2:
                # 可能是 [[x1,y1], [x2,y2]] 格式，补全四个点
                x1, y1 = float(box[0][0]), float(box[0][1])
                x2, y2 = float(box[1][0]), float(box[1][1])
                bbox_float = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            else:
                continue
            out.append((bbox_float, text.strip(), conf))

        return out
