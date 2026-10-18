"""
Base class for document parsers
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class ParsedDocument:
    """Result of document parsing"""
    title: str
    content: str
    metadata: Dict[str, Any]
    chunks: Optional[List[str]] = None
    quality_score: float = 1.0
    parse_errors: List[str] = None

    def __post_init__(self):
        if self.parse_errors is None:
            self.parse_errors = []


class BaseParser(ABC):
    """Base interface for all document parsers"""

    @classmethod
    @abstractmethod
    def supported_formats(cls) -> List[str]:
        """Return list of supported formats (lowercase: md, txt, pdf, docx, etc.)"""
        pass

    @abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        """Parse the document at given path, returns ParsedDocument"""
        pass

    def check_quality(self, content: str) -> float:
        """
        Calculate quality score based on content analysis.
        Returns score between 0.0 (bad) and 1.0 (good).
        """
        if not content or len(content.strip()) < 50:
            return 0.3

        # Check for garbled text / too many weird characters
        weird_chars = sum(1 for c in content if ord(c) < 32 and c not in '\n\r\t')
        weird_ratio = weird_chars / len(content)
        if weird_ratio > 0.05:
            return 0.5 - weird_ratio

        # Empty lines ratio
        lines = content.splitlines()
        empty_lines = sum(1 for line in lines if not line.strip())
        empty_ratio = empty_lines / len(lines)
        if empty_ratio > 0.8:
            return 0.2

        return 1.0
