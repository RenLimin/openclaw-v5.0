"""Office Engine v2 — 统一 SDK

Word / Excel / PPT 三套 SDK，遵循 OfficeDocumentBase 统一接口。

使用方式：
    from office_engine import OfficeDocument, OfficeConverter

    # 创建新文档
    ppt = OfficeDocument.create("ppt")
    doc = OfficeDocument.create("word")
    xls = OfficeDocument.create("excel")

    # 打开已有文档（自动识别格式）
    doc = OfficeDocument.open("report.pptx")

    # 格式转换
    OfficeConverter.to_pdf("report.pptx", "report.pdf")
"""

from .exceptions import (
    OfficeEngineError,
    OfficeFormatError,
    OfficeParseError,
    OfficeUnsupportedError,
)
from .word_engine import WordDocument
from .excel_engine import ExcelDocument
from .ppt_engine import PPTDocument
from .factory import OfficeDocument
from .converter import OfficeConverter

__all__ = [
    "WordDocument",
    "ExcelDocument",
    "PPTDocument",
    "OfficeDocument",
    "OfficeConverter",
    "OfficeEngineError",
    "OfficeParseError",
    "OfficeFormatError",
    "OfficeUnsupportedError",
]

__version__ = "2.0.0"
