"""
Office document parsers: Word, Excel, PowerPoint, PDF
"""
import os
import re
from typing import List, Optional
from dataclasses import dataclass
from .base import BaseParser, ParsedDocument


@dataclass
class ParserDependency:
    name: str
    available: bool
    error: Optional[str] = None


# Check dependencies
dependencies = {
    'docx': ParserDependency('python-docx', False),
    'openpyxl': ParserDependency('openpyxl', False),
    'pptx': ParserDependency('python-pptx', False),
    'pdfplumber': ParserDependency('pdfplumber', False),
}

try:
    import docx
    dependencies['docx'].available = True
except ImportError as e:
    dependencies['docx'].error = str(e)

try:
    import openpyxl
    dependencies['openpyxl'].available = True
except ImportError as e:
    dependencies['openpyxl'].error = str(e)

try:
    from pptx import Presentation
    dependencies['pptx'].available = True
except ImportError as e:
    dependencies['pptx'].error = str(e)

try:
    import pdfplumber
    dependencies['pdfplumber'].available = True
except ImportError as e:
    dependencies['pdfplumber'].error = str(e)


class WordParser(BaseParser):
    """Microsoft Word parser (.docx, .doc)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['docx', 'doc', 'word', 'msword']

    @classmethod
    def is_available(cls) -> bool:
        return dependencies['docx'].available

    def parse(self, file_path: str) -> ParsedDocument:
        if not self.is_available():
            return ParsedDocument(
                title=os.path.basename(file_path),
                content='',
                metadata={'error': f'Missing dependency: python-docx. Install with: pip install python-docx'},
                quality_score=0.0,
                parse_errors=['Missing dependency: python-docx']
            )

        document = docx.Document(file_path)
        paragraphs = []
        title = ''

        # Extract title from first heading
        for para in document.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if not title and para.style.name.startswith('Heading 1'):
                title = text
                continue
            paragraphs.append(text)

        if not title and paragraphs:
            title = paragraphs[0]

        content = '\n\n'.join(paragraphs)
        quality = self.check_quality(content)

        # Collect tables
        table_texts = []
        for table in document.tables:
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(' | '.join(cells))
            table_texts.append('\n'.join(rows))
        if table_texts:
            content += '\n\n--- Tables ---\n\n' + '\n\n'.join(table_texts)

        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'docx', 'paragraphs': len(paragraphs)},
            quality_score=quality
        )


class ExcelParser(BaseParser):
    """Microsoft Excel parser (.xlsx, .xls)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['xlsx', 'xls', 'excel', 'spreadsheet']

    @classmethod
    def is_available(cls) -> bool:
        return dependencies['openpyxl'].available

    def parse(self, file_path: str) -> ParsedDocument:
        if not self.is_available():
            return ParsedDocument(
                title=os.path.basename(file_path),
                content='',
                metadata={'error': 'Missing dependency: openpyxl. Install with: pip install openpyxl'},
                quality_score=0.0,
                parse_errors=['Missing dependency: openpyxl']
            )

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheets_text = []
        title = os.path.basename(file_path)

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell is not None]
                if cells:
                    rows.append(' | '.join(cells))
            if rows:
                sheets_text.append(f"# Sheet: {sheet_name}\n" + '\n'.join(rows))

        content = '\n\n'.join(sheets_text)
        quality = self.check_quality(content)

        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'xlsx', 'sheets': len(wb.sheetnames)},
            quality_score=quality
        )


class PowerPointParser(BaseParser):
    """Microsoft PowerPoint parser (.pptx, .ppt)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['pptx', 'ppt', 'powerpoint', 'presentation']

    @classmethod
    def is_available(cls) -> bool:
        return dependencies['pptx'].available

    def parse(self, file_path: str) -> ParsedDocument:
        if not self.is_available():
            return ParsedDocument(
                title=os.path.basename(file_path),
                content='',
                metadata={'error': 'Missing dependency: python-pptx. Install with: pip install python-pptx'},
                quality_score=0.0,
                parse_errors=['Missing dependency: python-pptx']
            )

        prs = Presentation(file_path)
        slides = []
        title = os.path.basename(file_path)

        for i, slide in enumerate(prs.slides):
            shapes_text = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    shapes_text.append(shape.text.strip())
            if shapes_text:
                slides.append(f"## Slide {i + 1}\n" + '\n'.join(shapes_text))

        content = '\n\n'.join(slides)
        quality = self.check_quality(content)

        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'pptx', 'slides': len(prs.slides)},
            quality_score=quality
        )


class PdfParser(BaseParser):
    """PDF parser (.pdf)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['pdf']

    @classmethod
    def is_available(cls) -> bool:
        return dependencies['pdfplumber'].available

    def parse(self, file_path: str) -> ParsedDocument:
        if not self.is_available():
            return ParsedDocument(
                title=os.path.basename(file_path),
                content='',
                metadata={'error': 'Missing dependency: pdfplumber. Install with: pip install pdfplumber'},
                quality_score=0.0,
                parse_errors=['Missing dependency: pdfplumber']
            )

        pages = []
        title = os.path.basename(file_path)
        total_words = 0

        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
                    total_words += len(text.split())

        content = '\n\n'.join(pages)
        quality = self.check_quality(content)

        # Try to get title from first page
        if pages:
            first_lines = pages[0].splitlines()
            for line in first_lines:
                if line.strip() and not line.startswith('---'):
                    title = line.strip()
                    break

        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'pdf', 'pages': len(pdf.pages), 'words': total_words},
            quality_score=quality
        )


def get_available_office_parsers():
    """Return list of available office parser classes"""
    parsers = []
    if WordParser.is_available():
        parsers.append(WordParser)
    if ExcelParser.is_available():
        parsers.append(ExcelParser)
    if PowerPointParser.is_available():
        parsers.append(PowerPointParser)
    if PdfParser.is_available():
        parsers.append(PdfParser)
    return parsers
