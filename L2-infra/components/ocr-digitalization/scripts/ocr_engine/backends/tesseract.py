"""
Tesseract OCR 后端

系统级 OCR 引擎，通过 pytesseract 调用。
优点：安装简单、跨平台、支持语言多
缺点：中文精度一般，适合作为 fallback
"""
from __future__ import annotations

from typing import List, Tuple
from PIL import Image

from .base import OCRBackend


class TesseractBackend(OCRBackend):
    """Tesseract OCR 后端"""

    name = "tesseract"
    priority = 50  # 优先级较低，作为 fallback
    supports_languages = ["eng", "chi_sim", "chi_tra", "chi_sim+eng"]

    def load(self, lang: str = "chi_sim+eng") -> bool:
        try:
            import pytesseract
            # 检查 tesseract 可执行文件
            pytesseract.get_tesseract_version()
            self._ocr = pytesseract
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
            data = self._ocr.image_to_data(
                image,
                lang=self._lang,
                output_type=self._ocr.Output.DICT,
            )
        except Exception:
            return []

        results = []
        n = len(data.get("text", []))
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            conf = float(data["conf"][i]) / 100.0 if data["conf"][i] != "-1" else 0.5
            if conf <= 0:
                continue
            x1 = float(data["left"][i])
            y1 = float(data["top"][i])
            w = float(data["width"][i])
            h = float(data["height"][i])
            x2 = x1 + w
            y2 = y1 + h
            bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            results.append((bbox, text, conf))

        return results
