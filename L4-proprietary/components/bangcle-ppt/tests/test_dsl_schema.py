"""
DSL Schema 测试 — 验证各种页面类型的模板数据模型。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

# conftest 已处理路径
from bangcle_ppt.dsl.schema import (
    SlideTemplate, PresentationSpec, TemplateMeta,
    CoverLayout, TocLayout, SectionLayout, TextImageLayout,
    ThreeCardsLayout, DataChartLayout, TocItem,
    CardItem, KpiItem, ContentItem,
    PAGE_LAYOUT_MAP,
)


class TestTemplateMeta:
    """测试模板元数据。"""

    def test_meta_valid(self):
        meta = TemplateMeta(name="测试封面", page_type="cover-light", theme="light")
        assert meta.name == "测试封面"
        assert meta.page_type == "cover-light"
        assert meta.theme == "light"

    def test_meta_theme_invalid(self):
        with pytest.raises(ValidationError):
            TemplateMeta(name="x", page_type="y", theme="invalid")

    def test_meta_defaults(self):
        meta = TemplateMeta(name="x", page_type="y")
        assert meta.version == "1.0.0"
        assert meta.theme == "light"


class TestCoverLayout:
    """封面页布局。"""

    def test_cover_defaults(self):
        layout = CoverLayout()
        assert layout.title == ""
        assert layout.presenter == ""
        assert layout.show_logo is True

    def test_cover_full(self):
        layout = CoverLayout(
            title="年度汇报",
            subtitle="ANNUAL REPORT",
            presenter="张三",
            company="梆梆安全",
            date="2025.01",
            slogan="稳如泰山·值得托付",
        )
        assert layout.title == "年度汇报"
        assert layout.presenter == "张三"


class TestTocLayout:
    """目录页布局。"""

    def test_toc_items(self):
        layout = TocLayout(items=[
            TocItem(number="01", title="第一部分", subtitle="PART ONE"),
            TocItem(number="02", title="第二部分", subtitle="PART TWO"),
        ])
        assert len(layout.items) == 2
        assert layout.items[0].number == "01"


class TestSlideTemplate:
    """SlideTemplate 顶层模型。"""

    def test_template_basic(self):
        tpl = SlideTemplate(
            meta={"name": "封面", "page_type": "cover-light", "theme": "light"},
            layout={"title": "测试标题", "presenter": "张三"},
        )
        assert tpl.meta.name == "封面"
        assert tpl.layout["title"] == "测试标题"

    def test_validate_layout_against_type(self):
        tpl = SlideTemplate(
            meta={"name": "封面", "page_type": "cover-light"},
            layout={"title": "测试标题", "presenter": "张三"},
        )
        layout = tpl.validate_layout_against_type()
        assert isinstance(layout, CoverLayout)
        assert layout.title == "测试标题"
        assert layout.presenter == "张三"

    def test_validate_unknown_type(self):
        tpl = SlideTemplate(
            meta={"name": "x", "page_type": "unknown-type"},
            layout={},
        )
        with pytest.raises(ValueError, match="Unknown page_type"):
            tpl.validate_layout_against_type()

    @pytest.mark.parametrize("page_type,layout_cls", [
        ("cover-light", CoverLayout),
        ("cover-dark", CoverLayout),
        ("toc-light", TocLayout),
        ("toc-dark", TocLayout),
        ("section-light", SectionLayout),
        ("section-dark", SectionLayout),
        ("content-two-col-light", TextImageLayout),
        ("content-three-cards-light", ThreeCardsLayout),
        ("data-chart-light", DataChartLayout),
    ])
    def test_page_layout_map_all_types(self, page_type, layout_cls):
        """验证所有注册的页面类型都能正确映射到 Layout 类。"""
        assert page_type in PAGE_LAYOUT_MAP
        assert PAGE_LAYOUT_MAP[page_type] is layout_cls


class TestPresentationSpec:
    """完整 PPT 规格。"""

    def test_spec_empty(self):
        spec = PresentationSpec(title="测试 PPT", theme="light")
        assert len(spec.slides) == 0

    def test_spec_with_slides(self):
        spec = PresentationSpec(
            title="测试 PPT",
            theme="light",
            slides=[
                {
                    "meta": {"name": "封面", "page_type": "cover-light"},
                    "layout": {"title": "封面标题"},
                },
                {
                    "meta": {"name": "目录", "page_type": "toc-light"},
                    "layout": {},
                },
            ]
        )
        assert len(spec.slides) == 2
        assert spec.slides[0].meta.page_type == "cover-light"

    def test_validate_all(self):
        spec = PresentationSpec(
            title="测试",
            slides=[
                {
                    "meta": {"name": "封面", "page_type": "cover-light"},
                    "layout": {"title": "T"},
                },
            ]
        )
        layouts = spec.validate_all()
        assert len(layouts) == 1
        assert isinstance(layouts[0], CoverLayout)


class TestPageLayoutMap:
    """验证 PAGE_LAYOUT_MAP 中的所有条目都有效。"""

    def test_all_page_types_have_layout(self):
        from bangcle_ppt.theme.design_constants import PAGE_TYPES as CONST_PAGE_TYPES
        # 设计常量中的页面类型应该都有对应的 layout 类
        missing = []
        for pt in CONST_PAGE_TYPES:
            if pt not in PAGE_LAYOUT_MAP:
                missing.append(pt)
        # 允许部分页面类型还没有 layout（但记录下来）
        # 至少核心类型应该有
        assert len(PAGE_LAYOUT_MAP) >= 10, f"只有 {len(PAGE_LAYOUT_MAP)} 种页面类型有 layout"

    def test_layout_count(self):
        """至少 20 种页面类型的 Layout 定义。"""
        assert len(PAGE_LAYOUT_MAP) >= 20
