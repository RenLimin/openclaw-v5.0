"""
PaddleOCR 后端（可选，高精度）

百度 PaddleOCR，中文识别精度高。
优点：中文精度高、支持版面分析、表格识别
缺点：依赖 paddlepaddle，安装较重
"""
from __future__ import annotations

from typing import List, Tuple
from PIL import Image
import numpy as np

from .base import OCRBackend


class PaddleOCRBackend(OCRBackend):
    """PaddleOCR 后端"""

    name = "paddleocr"
    priority = 10  # 最高优先级（高精度）
    supports_languages = ["ch", "en", "chinese_cht", "korean", "japanese", "ch+en"]

    def load(self, lang: str = "chi_sim+eng") -> bool:
        try:
            from paddleocr import PaddleOCR
            # 转换语言代码
            lang_map = {
                "chi_sim": "ch",
                "chi_tra": "chinese_cht",
                "eng": "en",
            }
            # PaddleOCR 用单个语言代码表示混合
            # chi_sim+eng → ch（PaddleOCR 的 ch 模型已包含中英文）
            has_chinese = any("chi" in c or "ch_sim" in c or "ch" in c
                            for c in lang.replace("+", ",").split(","))
            paddle_lang = "ch" if has_chinese else "en"

            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=paddle_lang,
                show_log=False,
            )
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
            result = self._ocr.ocr(img_array, cls=True)
        except Exception:
            return []

        # PaddleOCR 返回: [[ [box, (text, conf)], ... ]]
        if not result or not result[0]:
            return []

        out = []
        for item in result[0]:
            if len(item) < 2:
                continue
            box = item[0]  # [[x,y], [x,y], [x,y], [x,y]]
            text, conf = item[1]
            if not text.strip():
                continue
            bbox_float = [[float(p[0]), float(p[1])] for p in box]
            out.append((bbox_float, text.strip(), float(conf)))

        return out
