"""
Text format parsers: MD, TXT, HTML, CSV, JSON
"""
import re
import csv
import json
from typing import List
from bs4 import BeautifulSoup
from .base import BaseParser, ParsedDocument


class TextParser(BaseParser):
    """Plain text parser (.txt)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['txt', 'text']

    def parse(self, file_path: str) -> ParsedDocument:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Extract title from first non-empty line
        lines = content.splitlines()
        title = ''
        for line in lines:
            if line.strip():
                title = line.strip()
                break

        quality = self.check_quality(content)
        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'txt'},
            quality_score=quality
        )


class MarkdownParser(BaseParser):
    """Markdown parser (.md)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['md', 'markdown', 'mkd']

    def parse(self, file_path: str) -> ParsedDocument:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        # Extract title from first heading
        title_match = re.search(r'^#\s+(.*)$', content, re.MULTILINE)
        title = ''
        if title_match:
            title = title_match.group(1).strip()
        else:
            # Fallback to first non-empty line
            lines = content.splitlines()
            for line in lines:
                if line.strip():
                    title = line.strip()
                    break

        quality = self.check_quality(content)
        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'md'},
            quality_score=quality
        )


class HtmlParser(BaseParser):
    """HTML parser (.html, .htm)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['html', 'htm']

    def parse(self, file_path: str) -> ParsedDocument:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            html = f.read()

        soup = BeautifulSoup(html, 'html.parser')

        # Extract title
        title = ''
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Extract text from body
        for script in soup(["script", "style"]):
            script.extract()
        content = soup.get_text('\n', strip=True)

        quality = self.check_quality(content)
        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'html'},
            quality_score=quality
        )


class CsvParser(BaseParser):
    """CSV parser (.csv)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['csv', 'comma']

    def parse(self, file_path: str) -> ParsedDocument:
        rows = []
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append('\t'.join(row))

        content = '\n'.join(rows)
        title = f"CSV: {file_path.split('/')[-1]}"

        quality = self.check_quality(content)
        return ParsedDocument(
            title=title,
            content=content,
            metadata={'format': 'csv', 'rows': len(rows)},
            quality_score=quality
        )


class JsonParser(BaseParser):
    """JSON parser (.json)"""
    @classmethod
    def supported_formats(cls) -> List[str]:
        return ['json']

    def parse(self, file_path: str) -> ParsedDocument:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            try:
                data = json.load(f)
                content = json.dumps(data, indent=2, ensure_ascii=False)
                title = f"JSON: {file_path.split('/')[-1]}"
                quality = self.check_quality(content)
                return ParsedDocument(
                    title=title,
                    content=content,
                    metadata={'format': 'json'},
                    quality_score=quality
                )
            except json.JSONDecodeError as e:
                return ParsedDocument(
                    title=f"JSON: {file_path.split('/')[-1]}",
                    content=f.read(),
                    metadata={'format': 'json', 'error': str(e)},
                    quality_score=0.3,
                    parse_errors=[str(e)]
                )
