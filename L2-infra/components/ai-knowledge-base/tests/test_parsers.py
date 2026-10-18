"""
Tests for parsers
"""
import os
from ai_kb.parsers.text import TextParser, MarkdownParser
from ai_kb.parsers.base import ParsedDocument


def test_text_parser():
    """Test plain text parser"""
    parser = TextParser()
    content = """Hello World
This is a test document for the AI knowledge base system.
It contains enough content to pass the quality score check.
The parser should extract the title and keep the full body.
"""
    with open("/tmp/test.txt", "w") as f:
        f.write(content)

    result = parser.parse("/tmp/test.txt")
    assert isinstance(result, ParsedDocument)
    assert result.title == "Hello World"
    assert "Hello World" in result.content
    assert result.quality_score > 0.5
    os.unlink("/tmp/test.txt")


def test_markdown_parser():
    """Test markdown parser"""
    parser = MarkdownParser()
    content = """# Test Title

## Section 1

This is some content that is long enough to pass quality checks.
It has multiple sections and meaningful text body for parsing.
"""
    with open("/tmp/test.md", "w") as f:
        f.write(content)

    result = parser.parse("/tmp/test.md")
    assert result.title == "Test Title"
    assert "Section 1" in result.content
    assert "content" in result.content
    os.unlink("/tmp/test.md")
