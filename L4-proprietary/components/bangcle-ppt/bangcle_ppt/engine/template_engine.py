"""
模板引擎 — 加载 YAML 模板 → 校验 schema → 调用对应 renderer 渲染。
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Any

from pptx import Presentation

from ..dsl.schema import SlideTemplate, PresentationSpec
from ..theme.theme import Theme, get_theme
from ..base.renderer_base import RendererBase


class TemplateEngine:
    """
    Bangcle PPT 模板引擎。

    用法：
        engine = TemplateEngine(templates_dir="templates")
        # 单页渲染
        slide = engine.render_slide("cover-light", {"title": "汇报标题"})
        # 多页生成
        prs = engine.render_presentation([
            ("cover-light", {...}),
            ("toc-light", {...}),
        ], output_path="output.pptx")
    """

    def __init__(self, templates_dir: str | None = None, theme: str = "light"):
        """
        Args:
            templates_dir: 模板目录（包含 light/ dark/ shared/）
            theme: 默认主题（light / dark）
        """
        self.templates_dir = templates_dir
        self.default_theme = theme
        self._renderers: dict[str, type[RendererBase]] = {}
        self._template_cache: dict[str, SlideTemplate] = {}

    # ── Renderer 注册 ─────────────────────────────────────────────

    def register_renderer(self, page_type: str, renderer_cls: type[RendererBase]):
        """注册一个页面类型的渲染器。"""
        self._renderers[page_type] = renderer_cls

    def register_renderers(self, mapping: dict[str, type[RendererBase]]):
        """批量注册渲染器。"""
        for pt, cls in mapping.items():
            self.register_renderer(pt, cls)

    def get_renderer(self, page_type: str, theme: Theme | str | None = None) -> RendererBase:
        """获取指定页面类型的 renderer 实例。"""
        if page_type not in self._renderers:
            raise ValueError(
                f"No renderer registered for page_type '{page_type}'. "
                f"Available: {list(self._renderers.keys())}"
            )
        renderer_cls = self._renderers[page_type]
        return renderer_cls(theme=theme or self.default_theme)

    # ── 模板加载 ─────────────────────────────────────────────────

    def load_template(self, page_type: str, theme: str | None = None) -> SlideTemplate:
        """
        加载一个页面模板 YAML 文件并校验。

        Args:
            page_type: 页面类型标识
            theme: 主题（light/dark），默认用 default_theme

        Returns:
            SlideTemplate 实例
        """
        theme = theme or self.default_theme
        cache_key = f"{theme}/{page_type}"

        if cache_key in self._template_cache:
            return self._template_cache[cache_key]

        if not self.templates_dir:
            raise ValueError("templates_dir not set, cannot load template files")

        # 查找模板文件：<templates_dir>/<theme>/<page_type>.yaml
        template_path = os.path.join(self.templates_dir, theme, f"{page_type}.yaml")
        if not os.path.exists(template_path):
            # 尝试 .yml 后缀
            template_path_yml = template_path.replace(".yaml", ".yml")
            if os.path.exists(template_path_yml):
                template_path = template_path_yml
            else:
                raise FileNotFoundError(f"Template not found: {template_path}")

        with open(template_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        template = SlideTemplate(**raw)
        # 按页面类型做精确 layout 校验
        template.validate_layout_against_type()

        self._template_cache[cache_key] = template
        return template

    def list_templates(self, theme: str | None = None) -> list[str]:
        """列出可用的模板名称。"""
        theme = theme or self.default_theme
        if not self.templates_dir:
            return list(self._renderers.keys())
        t_dir = os.path.join(self.templates_dir, theme)
        if not os.path.isdir(t_dir):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(t_dir)
            if f.endswith((".yaml", ".yml"))
        ]

    # ── 渲染：单页 ────────────────────────────────────────────────

    def render_slide(
        self,
        prs: Presentation,
        page_type: str,
        data: dict[str, Any] | None = None,
        theme: str | None = None,
    ):
        """
        在已有的 Presentation 中渲染一页。

        Args:
            prs: python-pptx Presentation 对象
            page_type: 页面类型
            data: 覆盖模板中 data 字段的数据
            theme: 主题覆盖

        Returns:
            渲染后的 Slide 对象
        """
        theme = theme or self.default_theme
        renderer = self.get_renderer(page_type, theme=theme)

        # 优先用模板数据，再用 data 覆盖
        merged_data: dict[str, Any] = {}
        try:
            template = self.load_template(page_type, theme=theme)
            merged_data.update(template.layout)
            merged_data.update(template.data)
        except (ValueError, FileNotFoundError):
            pass  # 没有模板文件，纯用 data

        if data:
            merged_data.update(data)

        return renderer.render(prs, merged_data)

    # ── 渲染：完整 PPT ────────────────────────────────────────────

    def render_presentation(
        self,
        slides: list[tuple[str, dict[str, Any]] | str],
        output_path: str,
        theme: str | None = None,
    ) -> str:
        """
        生成完整 PPT 文件。

        Args:
            slides: 幻灯片列表，每项可以是：
                    - (page_type, data_dict) 元组
                    - page_type 字符串（用模板默认数据）
            output_path: 输出文件路径
            theme: 全局主题覆盖

        Returns:
            输出文件路径
        """
        theme = theme or self.default_theme
        prs = Presentation()
        # 设置 16:9
        prs.slide_width = 12192000  # EMU = 13.333"
        prs.slide_height = 6858000  # EMU = 7.5"

        for slide_spec in slides:
            if isinstance(slide_spec, str):
                page_type = slide_spec
                data = None
            else:
                page_type, data = slide_spec
            self.render_slide(prs, page_type, data=data, theme=theme)

        # 确保输出目录存在
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        prs.save(output_path)
        return output_path

    # ── 从 PresentationSpec 渲染 ──────────────────────────────────

    def render_from_spec(self, spec: PresentationSpec, output_path: str) -> str:
        """从 PresentationSpec 对象生成 PPT。"""
        prs = Presentation()
        prs.slide_width = 12192000
        prs.slide_height = 6858000

        for slide_tpl in spec.slides:
            page_type = slide_tpl.meta.page_type
            theme = slide_tpl.meta.theme
            merged = {**slide_tpl.layout, **slide_tpl.data}
            self.render_slide(prs, page_type, data=merged, theme=theme)

        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        prs.save(output_path)
        return output_path

    def render_from_yaml(self, spec_path: str, output_path: str) -> str:
        """从 YAML 规格文件生成 PPT。"""
        with open(spec_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        spec = PresentationSpec(**raw)
        return self.render_from_spec(spec, output_path)
