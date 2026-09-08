"""Word SDK 单元测试"""

import os
import sys
import tempfile

import pytest


from office_engine import WordDocument
from office_engine import OfficeEngineError


OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


class TestWordCreate:
    """创建文档"""

    def test_create_and_save(self):
        doc = WordDocument()
        out = os.path.join(OUTPUT_DIR, "test_create.docx")
        path = doc.save(out)
        assert os.path.exists(path)
        assert path == out
        doc.close()

    def test_format_property(self):
        doc = WordDocument()
        assert doc.format == "docx"
        doc.close()

    def test_metadata_defaults(self):
        doc = WordDocument()
        meta = doc.metadata
        assert "author" in meta
        assert "created" in meta
        doc.close()


class TestWordHeadings:
    """标题"""

    def test_add_heading_level_1(self):
        doc = WordDocument()
        doc.add_heading("一级标题", level=1)
        out = os.path.join(OUTPUT_DIR, "test_heading.docx")
        doc.save(out)
        # round-trip: parse
        doc2 = WordDocument(out)
        result = doc2.parse()
        assert len(result["headings"]) >= 1
        assert result["headings"][0]["text"] == "一级标题"
        assert result["headings"][0]["level"] == 1
        doc.close()
        doc2.close()

    def test_heading_level_range(self):
        doc = WordDocument()
        with pytest.raises(OfficeEngineError):
            doc.add_heading("坏标题", level=10)
        doc.close()


class TestWordParagraph:
    """段落"""

    def test_add_paragraph_basic(self):
        doc = WordDocument()
        doc.add_paragraph("这是一个普通段落。")
        out = os.path.join(OUTPUT_DIR, "test_paragraph.docx")
        doc.save(out)
        doc2 = WordDocument(out)
        result = doc2.parse()
        assert any("这是一个普通段落" in p["text"] for p in result["paragraphs"])
        doc.close()
        doc2.close()

    def test_add_paragraph_styled(self):
        doc = WordDocument()
        doc.add_paragraph("加粗红色文字", bold=True, color="FF0000", font_size=14)
        out = os.path.join(OUTPUT_DIR, "test_paragraph_style.docx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()

    def test_add_paragraph_align(self):
        doc = WordDocument()
        doc.add_paragraph("居中文字", align="center")
        out = os.path.join(OUTPUT_DIR, "test_paragraph_align.docx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestWordTable:
    """表格"""

    def test_add_table_with_data(self):
        doc = WordDocument()
        data = [
            ["姓名", "年龄", "城市"],
            ["张三", "30", "北京"],
            ["李四", "25", "上海"],
        ]
        doc.add_table(rows=3, cols=3, data=data)
        out = os.path.join(OUTPUT_DIR, "test_table.docx")
        doc.save(out)
        # round-trip
        doc2 = WordDocument(out)
        result = doc2.parse()
        assert len(result["tables"]) == 1
        assert result["tables"][0]["rows"] == 3
        assert result["tables"][0]["data"][0][0] == "姓名"
        assert result["tables"][0]["data"][1][1] == "30"
        doc.close()
        doc2.close()


class TestWordHeaderFooter:
    """页眉页脚"""

    def test_set_header_and_footer(self):
        doc = WordDocument()
        doc.add_paragraph("正文内容")
        doc.set_header("机密文档")
        doc.set_footer("版权所有", page_number=True)
        out = os.path.join(OUTPUT_DIR, "test_header_footer.docx")
        doc.save(out)
        # round-trip
        doc2 = WordDocument(out)
        result = doc2.parse()
        assert "机密文档" in result["sections"][0]["header_text"]
        doc.close()
        doc2.close()


class TestWordList:
    """列表"""

    def test_add_unordered_list(self):
        doc = WordDocument()
        doc.add_list(["苹果", "香蕉", "橙子"], ordered=False)
        out = os.path.join(OUTPUT_DIR, "test_list.docx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()

    def test_add_ordered_list(self):
        doc = WordDocument()
        doc.add_list(["第一步", "第二步", "第三步"], ordered=True)
        out = os.path.join(OUTPUT_DIR, "test_ordered_list.docx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestWordFindReplace:
    """查找替换"""

    def test_find_replace_in_paragraph(self):
        doc = WordDocument()
        doc.add_paragraph("今天的天气真不错，明天的天气也不错。")
        count = doc.find_replace("天气", "心情")
        assert count == 2
        out = os.path.join(OUTPUT_DIR, "test_replace.docx")
        doc.save(out)
        doc2 = WordDocument(out)
        result = doc2.parse()
        assert "心情" in result["paragraphs"][0]["text"]
        assert "天气" not in result["paragraphs"][0]["text"]
        doc.close()
        doc2.close()


class TestWordParse:
    """解析能力"""

    def test_parse_structure(self):
        doc = WordDocument()
        doc.add_heading("报告标题", level=1)
        doc.add_paragraph("第一段内容")
        doc.add_paragraph("第二段内容")
        doc.add_table(2, 2, data=[["A", "B"], ["C", "D"]])
        out = os.path.join(OUTPUT_DIR, "test_parse.docx")
        doc.save(out)

        doc2 = WordDocument(out)
        result = doc2.parse()
        assert result["format"] == "docx"
        assert len(result["headings"]) == 1
        assert len(result["paragraphs"]) >= 2
        assert len(result["tables"]) == 1
        doc.close()
        doc2.close()


class TestWordToMarkdown:
    """转 Markdown"""

    def test_to_markdown(self):
        doc = WordDocument()
        doc.add_heading("Hello", level=1)
        doc.add_paragraph("World")
        doc.add_table(2, 2, data=[["Name", "Age"], ["Alice", "30"]])
        out = os.path.join(OUTPUT_DIR, "test_md.docx")
        doc.save(out)

        doc2 = WordDocument(out)
        md = doc2.to_markdown()
        assert "# Hello" in md
        assert "World" in md
        assert "| Name | Age |" in md
        doc.close()
        doc2.close()


class TestWordPageBreak:
    """分页符"""

    def test_add_page_break(self):
        doc = WordDocument()
        doc.add_paragraph("第一页")
        doc.add_page_break()
        doc.add_paragraph("第二页")
        out = os.path.join(OUTPUT_DIR, "test_page_break.docx")
        doc.save(out)
        assert os.path.exists(out)
        doc.close()


class TestWordChineseFont:
    """中文字体"""

    def test_chinese_font_set(self):
        doc = WordDocument()
        doc.add_heading("中文标题", level=1)
        doc.add_paragraph("中文段落内容")
        out = os.path.join(OUTPUT_DIR, "test_chinese.docx")
        doc.save(out)
        # 验证文件非空且能被重新打开
        doc2 = WordDocument(out)
        result = doc2.parse()
        assert result["headings"][0]["text"] == "中文标题"
        doc.close()
        doc2.close()
