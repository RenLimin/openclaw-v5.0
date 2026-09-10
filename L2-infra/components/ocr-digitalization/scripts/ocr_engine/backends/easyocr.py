"""
EasyOCR 后端（可选）

基于 PyTorch 的深度学习 OCR 引擎，支持 80+ 语言。
优点：精度较高，CPU 可用
缺点：首次加载慢，模型文件大
"""
from __future__ import annotations

from typing import List, Tuple
from PIL import Image
import numpy as np

from .base import OCRBackend


class EasyOCRBackend(OCRBackend):
    """EasyOCR 后端"""

    name = "easyocr"
    priority = 30
    supports_languages = ["ch_sim", "ch_tra", "en", "ch_sim+en"]

    def load(self, lang: str = "chi_sim+eng") -> bool:
        try:
            from easyocr import Reader
            # 转换语言代码
            lang_map = {
                "chi_sim": "ch_sim",
                "chi_tra": "ch_tra",
                "eng": "en",
            }
            langs = []
            for code in lang.replace("+", ",").split(","):
                code = code.strip()
                langs.append(lang_map.get(code, code))
            if not langs:
                langs = ["ch_sim", "en"]
            self._ocr = Reader(langs, gpu=False, verbose=False)
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
            img_array = np.array(image.convert("RGB"))
            raw_results = self._ocr.readtext(img_array)
        except Exception:
            return []

        results = []
        for item in raw_results:
            # EasyOCR 返回: [bbox, text, confidence]
            if len(item) < 3:
                continue
            bbox = item[0]  # [[x,y], [x,y], [x,y], [x,y]]
            text = item[1]
            conf = float(item[2])
            if not text.strip():
                continue
            # 确保 bbox 是 float 列表
            bbox_float = [[float(p[0]), float(p[1])] for p in bbox]
            results.append((bbox_float, text.strip(), conf))

        return results
