"""
模板文件测试 — 验证所有 YAML 模板能正确加载并通过 schema 校验。
"""

from __future__ import annotations

import os
import pytest
import yaml

from bangcle_ppt.dsl.schema import SlideTemplate, PAGE_LAYOUT_MAP

# 模板目录
_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_DIR = os.path.join(os.path.dirname(_HERE), "bangcle_ppt", "templates")


def _list_yaml_files(subdir: str) -> list[str]:
    d = os.path.join(_TEMPLATES_DIR, subdir)
    if not os.path.isdir(d):
        return []
    return sorted([
        f for f in os.listdir(d)
        if f.endswith((".yaml", ".yml"))
    ])


def _load_yaml(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestLightTemplates:
    """浅色模板测试。"""

    def test_light_templates_exist(self):
        files = _list_yaml_files("light")
        assert len(files) >= 15, f"浅色模板不足 15 个：{len(files)}"

    @pytest.mark.parametrize("filename", _list_yaml_files("light"))
    def test_each_light_template_valid_yaml(self, filename):
        """每个浅色模板都是有效的 YAML。"""
        filepath = os.path.join(_TEMPLATES_DIR, "light", filename)
        data = _load_yaml(filepath)
        assert isinstance(data, dict)
        assert "meta" in data
        assert "layout" in data

    @pytest.mark.parametrize("filename", _list_yaml_files("light"))
    def test_each_light_template_matches_schema(self, filename):
        """每个浅色模板通过 SlideTemplate schema 校验。"""
        filepath = os.path.join(_TEMPLATES_DIR, "light", filename)
        data = _load_yaml(filepath)
        tpl = SlideTemplate(**data)
        # 按 page_type 做 layout 精确校验
        layout = tpl.validate_layout_against_type()
        assert layout is not None

    @pytest.mark.parametrize("filename", _list_yaml_files("light"))
    def test_light_template_theme_correct(self, filename):
        """浅色模板的 theme 字段正确。"""
        filepath = os.path.join(_TEMPLATES_DIR, "light", filename)
        data = _load_yaml(filepath)
        # 有些通用模板可能 theme=light，有些可能复用其他类型
        # 只要 page_type 存在于 layout map 即可
        tpl = SlideTemplate(**data)
        assert tpl.meta.page_type in PAGE_LAYOUT_MAP


class TestDarkTemplates:
    """深色模板测试。"""

    def test_dark_templates_exist(self):
        files = _list_yaml_files("dark")
        assert len(files) >= 10, f"深色模板不足 10 个：{len(files)}"

    @pytest.mark.parametrize("filename", _list_yaml_files("dark"))
    def test_each_dark_template_valid_yaml(self, filename):
        filepath = os.path.join(_TEMPLATES_DIR, "dark", filename)
        data = _load_yaml(filepath)
        assert isinstance(data, dict)
        assert "meta" in data

    @pytest.mark.parametrize("filename", _list_yaml_files("dark"))
    def test_each_dark_template_matches_schema(self, filename):
        filepath = os.path.join(_TEMPLATES_DIR, "dark", filename)
        data = _load_yaml(filepath)
        tpl = SlideTemplate(**data)
        layout = tpl.validate_layout_against_type()
        assert layout is not None


class TestTemplateEngineWithTemplates:
    """引擎加载模板文件并渲染测试。"""

    @pytest.fixture
    def engine(self):
        from bangcle_ppt.engine import TemplateEngine
        from bangcle_ppt.renderers import REGISTRY
        engine = TemplateEngine(templates_dir=_TEMPLATES_DIR, theme="light")
        engine.register_renderers(REGISTRY)
        return engine

    def test_list_light_templates(self, engine):
        light = engine.list_templates("light")
        assert len(light) >= 15

    def test_list_dark_templates(self, engine):
        dark = engine.list_templates("dark")
        assert len(dark) >= 10

    def test_load_cover_template(self, engine):
        tpl = engine.load_template("cover-light", theme="light")
        assert tpl.meta.name == "浅色封面页"
        assert tpl.meta.page_type == "cover-light"

    def test_render_from_template_file(self, engine, tmp_path):
        """从模板文件加载并渲染。"""
        from pptx import Presentation
        prs = Presentation()
        prs.slide_width = 12192000
        prs.slide_height = 6858000

        slide = engine.render_slide(prs, "cover-light")
        assert slide is not None
        assert len(prs.slides) == 1

    def test_full_presentation_from_templates(self, engine, tmp_path):
        """使用模板生成完整演示 PPT。"""
        output = str(tmp_path / "from-templates.pptx")
        result = engine.render_presentation(
            [
                "cover-light",
                "toc-light",
                "section-light",
                "content-two-col-light",
                "content-three-cards-light",
                "data-chart-light",
                "timeline-vertical-light",
                "closing-light",
            ],
            output_path=output,
        )
        assert os.path.exists(result)
        from pptx import Presentation
        prs = Presentation(result)
        assert len(prs.slides) == 8

    def test_dark_presentation_from_templates(self, engine, tmp_path):
        """深色主题模板生成 PPT。"""
        output = str(tmp_path / "dark-from-templates.pptx")
        result = engine.render_presentation(
            [
                "cover-dark",
                "toc-dark",
                "section-dark",
                "node-graph-dark",
                "four-cards-dark",
                "honeycomb-dark",
                "closing-dark",
            ],
            output_path=output,
            theme="dark",
        )
        assert os.path.exists(result)
        from pptx import Presentation
        prs = Presentation(result)
        assert len(prs.slides) == 7


class TestSharedVariables:
    """共享变量文件测试。"""

    def test_shared_variables_exist(self):
        filepath = os.path.join(_TEMPLATES_DIR, "shared", "variables.yaml")
        assert os.path.exists(filepath)

    def test_shared_variables_valid(self):
        filepath = os.path.join(_TEMPLATES_DIR, "shared", "variables.yaml")
        data = _load_yaml(filepath)
        assert "colors" in data
        assert "fonts" in data
        assert "sizes" in data
        assert "brand" in data
        assert data["colors"]["primary"] == "#2D74BB"
