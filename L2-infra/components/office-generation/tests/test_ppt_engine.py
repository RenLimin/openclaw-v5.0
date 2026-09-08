"""
PPT SDK 测试 — 至少 7 个用例。
"""

import os
import sys
import pytest

# 将 src 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from office_engine.ppt_engine import PPTDocument, SlideProxy
from office_engine.exceptions import OfficeFormatError

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def test_create_and_save():
    """测试：创建新 PPT 并保存。"""
    ppt = PPTDocument()
    assert ppt.format == "pptx"
    assert ppt.slide_count() == 0  # 默认空白模板 0 页

    # 添加一页
    slide = ppt.add_slide("blank")
    assert isinstance(slide, SlideProxy)
    assert ppt.slide_count() == 1

    out = os.path.join(OUTPUT_DIR, "test_create.pptx")
    saved = ppt.save(out)
    assert saved == out
    assert os.path.exists(out)
    assert os.path.getsize(out) > 0
    ppt.close()


def test_multiple_slides_various_layouts():
    """测试：多页幻灯片，多种布局。"""
    ppt = PPTDocument()
    # 先删掉默认的一页

    layouts = ["title", "title_content", "two_content", "section_header", "blank"]
    for layout in layouts:
        s = ppt.add_slide(layout)
        assert isinstance(s, SlideProxy)

    assert ppt.slide_count() == len(layouts)

    out = os.path.join(OUTPUT_DIR, "test_multi_layout.pptx")
    ppt.save(out)
    ppt.close()

    # 重新打开验证
    ppt2 = PPTDocument(out)
    assert ppt2.slide_count() == len(layouts)
    ppt2.close()


def test_text_box_with_chinese():
    """测试：文本框 + 中文字体。"""
    ppt = PPTDocument()

    slide = ppt.add_slide("blank")
    ppt.add_text_box(
        slide, 1, 1, 8, 2,
        "你好，世界！\nHello World",
        font_size=24,
        bold=True,
        color="#FF0000",
        align="center",
    )

    # 验证文本在 slide 里
    assert len(slide.raw.shapes) >= 1
    shape = slide.raw.shapes[0]
    assert shape.has_text_frame
    assert "你好，世界" in shape.text_frame.text

    out = os.path.join(OUTPUT_DIR, "test_textbox_chinese.pptx")
    ppt.save(out)
    ppt.close()


def test_table():
    """测试：表格（带头样式）。"""
    ppt = PPTDocument()

    slide = ppt.add_slide("blank")
    data = [
        ["名称", "数值", "备注"],
        ["项目A", 100, "完成"],
        ["项目B", 200, "进行中"],
        ["项目C", 150, "待启动"],
    ]
    ppt.add_table(slide, 1, 1.5, 8, 3, 4, 3, data=data, header=True)

    out = os.path.join(OUTPUT_DIR, "test_table.pptx")
    ppt.save(out)

    # round-trip 验证
    ppt2 = PPTDocument(out)
    parsed = ppt2.parse()
    assert len(parsed["slides"]) == 1
    tables = parsed["slides"][0]["tables"]
    assert len(tables) == 1
    assert tables[0]["rows"] == 4
    assert tables[0]["cols"] == 3
    assert tables[0]["data"][0][0] == "名称"
    assert tables[0]["data"][2][1] == "200"
    ppt2.close()
    ppt.close()


def test_chart_column_and_pie():
    """测试：柱状图 + 饼图。"""
    ppt = PPTDocument()

    slide = ppt.add_slide("blank")

    # 柱状图
    ppt.add_chart(
        slide,
        0.5, 1, 4.5, 3.5,
        chart_type="column",
        data={"销售额": [100, 200, 150, 300]},
        categories=["Q1", "Q2", "Q3", "Q4"],
        title="季度销售额",
    )

    # 饼图
    ppt.add_chart(
        slide,
        5.5, 1, 4, 3.5,
        chart_type="pie",
        data={"占比": [30, 25, 20, 25]},
        categories=["A", "B", "C", "D"],
        title="市场占比",
    )

    out = os.path.join(OUTPUT_DIR, "test_chart.pptx")
    ppt.save(out)

    # 解析验证
    ppt2 = PPTDocument(out)
    parsed = ppt2.parse()
    charts = parsed["slides"][0]["charts"]
    assert len(charts) == 2
    # chart_type 在 python-pptx 中是枚举值
    assert any(c["title"] == "季度销售额" for c in charts)
    assert any(c["title"] == "市场占比" for c in charts)
    ppt2.close()
    ppt.close()


def test_notes():
    """测试：备注功能。"""
    ppt = PPTDocument()

    slide = ppt.add_slide("blank")
    ppt.add_notes(slide, "这是一页备注，包含中文内容。Speaker notes here.")

    out = os.path.join(OUTPUT_DIR, "test_notes.pptx")
    ppt.save(out)

    # 解析验证
    ppt2 = PPTDocument(out)
    parsed = ppt2.parse()
    assert parsed["slides"][0]["notes"] == "这是一页备注，包含中文内容。Speaker notes here."
    ppt2.close()
    ppt.close()


def test_parse_and_to_markdown():
    """测试：parse + to_markdown + round-trip。"""
    ppt = PPTDocument()

    # 第 1 页：标题 + 文本
    s1 = ppt.add_slide("title")
    ppt.set_slide_title(s1, "演示标题")
    ppt.add_text_box(s1, 1, 3, 8, 1, "副标题文本")
    ppt.add_notes(s1, "第 1 页备注")

    # 第 2 页：表格
    s2 = ppt.add_slide("title_content")
    ppt.set_slide_title(s2, "数据表格")
    data = [["指标", "数值"], ["收入", "1000"], ["成本", "600"]]
    ppt.add_table(s2, 1, 2, 6, 2, 3, 2, data=data)

    out = os.path.join(OUTPUT_DIR, "test_parse_md.pptx")
    ppt.save(out)
    ppt.close()

    # 打开解析
    ppt2 = PPTDocument(out)
    parsed = ppt2.parse()
    assert parsed["slide_count"] == 2
    assert len(parsed["slides"]) == 2
    assert parsed["slides"][0]["title"] == "演示标题"
    assert parsed["slides"][0]["notes"] == "第 1 页备注"
    assert len(parsed["slides"][1]["tables"]) == 1
    assert parsed["slides"][1]["tables"][0]["data"][0][0] == "指标"

    # to_markdown
    md = ppt2.to_markdown()
    assert "## 演示标题" in md
    assert "副标题文本" in md
    assert "## 数据表格" in md
    assert "| 指标 | 数值 |" in md
    assert "**备注**" in md
    assert "第 1 页备注" in md

    ppt2.close()


def test_find_replace():
    """测试：全局查找替换。"""
    ppt = PPTDocument()

    s1 = ppt.add_slide("blank")
    ppt.add_text_box(s1, 1, 1, 8, 1, "产品名：OLD_NAME，版本：OLD_NAME v1.0")

    s2 = ppt.add_slide("blank")
    data = [["项目", "名称"], ["A", "OLD_NAME"]]
    ppt.add_table(s2, 1, 1, 6, 1.5, 2, 2, data=data)
    ppt.add_notes(s2, "备注里的 OLD_NAME 也要被替换")

    count = ppt.find_replace("OLD_NAME", "NEW_NAME")
    assert count >= 3  # 文本框里 2 次 + 表格 1 次 + 备注 1 次

    out = os.path.join(OUTPUT_DIR, "test_find_replace.pptx")
    ppt.save(out)

    # 验证
    ppt2 = PPTDocument(out)
    parsed = ppt2.parse()
    slide0_text = "\n".join(tb["text"] for tb in parsed["slides"][0]["text_boxes"])
    assert "NEW_NAME" in slide0_text
    assert "OLD_NAME" not in slide0_text

    table_data = parsed["slides"][1]["tables"][0]["data"]
    assert "NEW_NAME" in table_data[1][1]
    assert "OLD_NAME" not in parsed["slides"][1]["notes"]
    assert "NEW_NAME" in parsed["slides"][1]["notes"]

    ppt2.close()
    ppt.close()


def test_duplicate_and_delete_slide():
    """测试：复制 + 删除幻灯片。"""
    ppt = PPTDocument()

    s1 = ppt.add_slide("blank")
    ppt.add_text_box(s1, 1, 1, 4, 1, "原始页面")
    ppt.add_notes(s1, "原始备注")

    assert ppt.slide_count() == 1

    # 复制
    new_slide = ppt.duplicate_slide(0)
    assert ppt.slide_count() == 2
    assert isinstance(new_slide, SlideProxy)

    # 验证内容被复制
    parsed = ppt.parse()
    assert parsed["slides"][0]["text_boxes"][0]["text"] == "原始页面"
    assert parsed["slides"][1]["text_boxes"][0]["text"] == "原始页面"
    assert parsed["slides"][1]["notes"] == "原始备注"

    # 删除第一页
    ppt.delete_slide(0)
    assert ppt.slide_count() == 1

    out = os.path.join(OUTPUT_DIR, "test_dup_delete.pptx")
    ppt.save(out)
    ppt.close()


def test_metadata():
    """测试：metadata 属性。"""
    ppt = PPTDocument()
    meta = ppt.metadata
    assert meta["slide_count"] == 0
    assert meta["path"] is None
    assert meta["width"] > 0
    assert meta["height"] > 0
    ppt.close()


def test_unknown_layout_raises():
    """测试：未知布局抛异常。"""
    ppt = PPTDocument()
    with pytest.raises(OfficeFormatError):
        ppt.add_slide("nonexistent")
    ppt.close()
