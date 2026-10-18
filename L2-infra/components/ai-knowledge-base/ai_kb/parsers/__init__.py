"""
Document parser module entry
"""
from .base import BaseParser, ParsedDocument
from .text import TextParser, MarkdownParser, HtmlParser, CsvParser, JsonParser
from .text import *
from .office import *
from .ocr import *

# Registry of all parsers
_parsers = []


def register_parser(cls):
    """Register a parser class"""
    if issubclass(cls, BaseParser):
        _parsers.append(cls)
    return cls


# Register built-in parsers
register_parser(TextParser)
register_parser(MarkdownParser)
register_parser(HtmlParser)
register_parser(CsvParser)
register_parser(JsonParser)

from .office import get_available_office_parsers
for parser_cls in get_available_office_parsers():
    register_parser(parser_cls)

if ImageOcrParser.is_available():
    register_parser(ImageOcrParser)


def get_parser_for_format(format_: str) -> BaseParser:
    """Get a parser instance for the file format"""
    format_lower = format_.lower()
    for cls in _parsers:
        if format_lower in cls.supported_formats():
            return cls()
    return None


def get_supported_formats():
    """Get all supported formats"""
    formats = []
    for cls in _parsers:
        formats.extend(cls.supported_formats())
    return list(set(formats))
