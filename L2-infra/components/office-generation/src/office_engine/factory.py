"""
统一工厂类 — 自动识别格式，返回对应 SDK 实例。

导入方式：from office_engine import OfficeDocument
"""

from __future__ import annotations

import os

from .exceptions import OfficeFormatError

# Word/Excel 由另一个 subagent 实现，延迟 import 避免循环依赖
# 我们的代码只保证 PPT 路径可用，Word/Excel 在测试时可能 mock


def _detect_format_from_path(path: str) -> str:
    """从文件扩展名推断格式。"""
    ext = os.path.splitext(path)[1].lower()
    return {
        ".docx": "word",
        ".xlsx": "excel",
        ".pptx": "ppt",
    }.get(ext, "")


class OfficeDocument:
    """工厂类，自动识别格式，返回对应 SDK 实例。"""

    # 格式 → (模块名, 类名)
    _REGISTRY = {
        "word": ("office_engine.word_engine", "WordDocument"),
        "excel": ("office_engine.excel_engine", "ExcelDocument"),
        "ppt": ("office_engine.ppt_engine", "PPTDocument"),
    }

    @classmethod
    def create(cls, doc_type: str, path: str | None = None):
        """
        创建新文档或打开已有文档。

        Args:
            doc_type: "word" | "excel" | "ppt"，或从文件扩展名自动推断
            path: 已有文件路径（打开模式）；None 则创建新文档

        Returns:
            WordDocument | ExcelDocument | PPTDocument
        """
        # 如果 doc_type 是路径形式（带扩展名），自动推断
        if "." in doc_type and not doc_type.startswith("."):
            inferred = _detect_format_from_path(doc_type)
            if inferred:
                # doc_type 实际是路径
                return cls.open(doc_type)

        if doc_type not in cls._REGISTRY:
            raise OfficeFormatError(
                f"Unsupported doc_type '{doc_type}'. "
                f"Available: {list(cls._REGISTRY.keys())}"
            )

        module_name, class_name = cls._REGISTRY[doc_type]
        doc_cls = cls._load_class(module_name, class_name)
        return doc_cls(path)

    @classmethod
    def open(cls, path: str):
        """
        打开已有文档，按扩展名自动识别。

        Args:
            path: 文档路径

        Returns:
            WordDocument | ExcelDocument | PPTDocument
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        fmt = _detect_format_from_path(path)
        if not fmt:
            raise OfficeFormatError(
                f"Cannot detect format from '{path}'. "
                f"Supported: .docx, .xlsx, .pptx"
            )

        return cls.create(fmt, path)

    @staticmethod
    def _load_class(module_name: str, class_name: str):
        """延迟加载类，避免未实现的 Word/Excel 影响 PPT 路径。"""
        import importlib
        module = importlib.import_module(module_name)
        return getattr(module, class_name)

    @staticmethod
    def detect_format(path: str) -> str:
        """检测文件格式（返回 word/excel/ppt/空字符串）。"""
        return _detect_format_from_path(path)
