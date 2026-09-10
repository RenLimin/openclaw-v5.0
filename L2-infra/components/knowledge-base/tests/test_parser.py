"""测试：文档解析器"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from knowledge_base.parser import MarkdownParser, PlainTextParser, CodeParser


def test_markdown_parser_basic():
    content = "# 标题\n\n这是正文内容。"
    parser = MarkdownParser()
    doc = parser.parse(content)
    assert doc.title == "标题"
    assert doc.doc_type == "markdown"
    assert "这是正文内容" in doc.content


def test_markdown_parser_frontmatter():
    content = """---
title: 测试文档
id: test-001
tags: [python, 测试]
category: tech
---

# 一级标题

正文内容。
"""
    parser = MarkdownParser()
    doc = parser.parse(content)
    assert doc.title == "测试文档"
    assert doc.doc_id == "test-001"
    assert "python" in doc.tags
    assert doc.category == "tech"
    assert "一级标题" in doc.content
    assert "正文内容" in doc.content


def test_markdown_parser_no_frontmatter():
    content = "# 没有元数据\n\n只有正文。"
    parser = MarkdownParser()
    doc = parser.parse(content)
    assert doc.title == "没有元数据"
    assert doc.metadata == {}
    assert len(doc.tags) == 0


def test_plain_text_parser():
    content = "这是第一行\n这是第二行\n第三行内容"
    parser = PlainTextParser()
    doc = parser.parse(content)
    assert doc.title == "这是第一行"
    assert doc.doc_type == "plaintext"
    assert "第三行" in doc.content


def test_code_parser():
    content = '''#!/usr/bin/env python3
"""模块说明：这是一个测试模块"""

def hello():
    print("hello")
'''
    parser = CodeParser()
    doc = parser.parse(content, source="test.py")
    assert doc.doc_type == "code"
    assert doc.category == "py"
    assert doc.metadata["line_count"] > 0
    assert "description" in doc.metadata
