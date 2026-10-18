"""
OCR parsers for images and scanned PDFs
"""
import os
from typing import List, Optional

# Lazy imports: OCR deps are optional, don't break other parsers if missing
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

from .base import BaseParser, ParsedDocument


class ImageOcrParser(BaseParser):
    """Image parser with OCR (.png, .jpg, .jpeg, .bmp, .tiff)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif', 'gif']

    @classmethod
    def is_available(cls) -> bool:
        if not (PIL_AVAILABLE and TESSERACT_AVAILABLE):
            return False
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def parse(self, file_path: str) -> ParsedDocument:
        if not self.is_available():
            return ParsedDocument(
                title=os.path.basename(file_path),
                content='',
                metadata={'error': 'Tesseract OCR not available. Install: pip install pytesseract pillow + system tesseract'},
                quality_score=0.0,
                parse_errors=['Tesseract OCR not available']
            )

        title = os.path.basename(file_path)
        image = Image.open(file_path)
        content = pytesseract.image_to_string(image)

        quality = self.check_quality(content)
        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'image', 'ocr': 'tesseract'},
            quality_score=quality
        )
