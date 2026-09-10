"""
OCR 后端抽象基类

所有 OCR 引擎后端都必须实现这个接口，
OCREngine 主类通过统一接口调度不同后端。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from PIL import Image


class OCRBackend(ABC):
    """OCR 引擎后端抽象基类

    生命周期：
    1. 实例化（轻量，不加载模型）
    2. load() — 加载模型/初始化引擎（较重）
    3. available() — 检查是否可用
    4. recognize(image) — 识别
    """

    name: str = "base"
    """后端名称，用于标识和日志"""

    priority: int = 100
    """优先级（越小越优先），用于自动选择后端"""

    supports_languages: List[str] = []
    """支持的语言代码列表"""

    def __init__(self) -> None:
        self._loaded: bool = False
        self._lang: str = "chi_sim+eng"

    # ---- 生命周期 ----

    def load(self, lang: str = "chi_sim+eng") -> bool:
        """加载引擎模型。返回是否加载成功。

        基类提供默认实现（标记为已加载）。
        子类应重写此方法进行实际的模型加载。
        """
        self._lang = lang
        self._loaded = True
        return True

    def available(self) -> bool:
        """引擎是否可用（已加载且能正常工作）"""
        return self._loaded

    def unload(self) -> None:
        """卸载引擎，释放资源"""
        self._loaded = False

    # ---- 核心识别 ----

    @abstractmethod
    def recognize(self, image: Image.Image) -> List[Tuple]:
        """识别单张图片

        Args:
            image: PIL Image（RGB）

        Returns:
            List of (bbox, text, confidence)
            - bbox: List of 4 points [[x,y], [x,y], [x,y], [x,y]]
            - text: str
            - confidence: float (0.0 ~ 1.0)
        """
        ...

    # ---- 语言支持 ----

    def supports_lang(self, lang: str) -> bool:
        """是否支持指定语言"""
        if not self.supports_languages:
            return True  # 未声明则默认支持
        # 简单匹配：检查 lang 中的每个语言代码
        lang_codes = lang.replace("+", ",").split(",")
        for code in lang_codes:
            code = code.strip()
            if not code:
                continue
            if not any(code in supported for supported in self.supports_languages):
                return False
        return True

    # ---- 信息 ----

    def info(self) -> dict:
        """返回后端信息字典"""
        return {
            "name": self.name,
            "loaded": self._loaded,
            "lang": self._lang,
            "priority": self.priority,
        }
