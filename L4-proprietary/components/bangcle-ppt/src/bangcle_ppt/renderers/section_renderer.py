"""
章节过渡页渲染器（浅色 + 深色）。
"""

from __future__ import annotations

from typing import Any

from pptx import Presentation

from ..base.renderer_base import RendererBase


class SectionLightRenderer(RendererBase):
    """浅色章节过渡页（左标题 + 右人物剪影 + Part N）。"""
    page_type = "section-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 左侧装饰线
        self.add_left_accent_line(slide, s.margins.title_left, 2.0, 1.2, width=4)

        # Part 标签
        part_label = data.get("part_label", "Part One")
        self.add_text(
            slide, part_label.upper(),
            s.margins.title_left + 0.15, 1.8,
            4, 0.35,
            font_size=14,
            color=self.theme.caption_color,
        )

        # 章节号
        chapter_num = data.get("chapter_number", "01")
        self.add_text(
            slide, chapter_num,
            s.margins.title_left, 2.2,
            3, 1.5,
            font_size=96,
            bold=True,
            color=self.theme.primary,
        )

        # 主标题
        title = data.get("title", "章节标题")
        self.add_text(
            slide, title,
            s.margins.title_left + 0.2, 3.5,
            5.5, 0.7,
            font_size=self.theme.font_size.h1,
            bold=True,
            color=self.theme.title_color,
        )

        # 英文副标题
        subtitle = data.get("subtitle", "CHAPTER SUBTITLE")
        self.add_text(
            slide, subtitle.upper(),
            s.margins.title_left + 0.2, 4.2,
            5, 0.35,
            font_size=self.theme.font_size.en_sub if hasattr(self.theme.font_size, 'en_sub') else 14,
            color=self.theme.caption_color,
        )

        # 底部装饰条
        self.add_rect(
            slide, 0, s.slide.height - 0.08, s.slide.width, 0.08,
            fill_color=self.theme.primary,
        )

        # 右侧人物剪影占位（圆形 + 装饰）
        if data.get("show_silhouette", True):
            # 人物剪影区域：右中侧
            avatar_x = 8.5
            avatar_y = 1.5
            avatar_size = 4.5

            # 装饰圆（背景）
            self.add_circle(
                slide, avatar_x - 0.3, avatar_y - 0.3, avatar_size + 0.6,
                fill_color=None,
                border_color="#E7E6E6",
                border_width=1,
            )
            # 主圆形
            self.add_circle(
                slide, avatar_x, avatar_y, avatar_size,
                fill_color="#F5F9FF",
                border_color=self.theme.primary,
                border_width=2,
            )
            # 人物图标占位
            self.add_text(
                slide, "👤",
                avatar_x, avatar_y + 1.2,
                avatar_size, 2,
                font_size=120,
                color=self.theme.primary,
                align="center",
            )

        # 右上角 Logo
        if data.get("show_logo", True):
            logo_path = data.get("logo_path", "")
            if logo_path:
                try:
                    self.add_image(slide, logo_path, s.logo.left, s.logo.top, s.logo.width, s.logo.height)
                except FileNotFoundError:
                    pass

        return slide


class SectionDarkRenderer(RendererBase):
    """深色章节过渡页（中心大数字 + 标题）。"""
    page_type = "section-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 背景装饰：半透明圆
        self.add_circle(
            slide, 9.5, -1.5, 6,
            fill_color=None,
            border_color=self.theme.primary,
            border_width=1,
        )
        self.add_circle(
            slide, 10.0, -1.0, 5,
            fill_color=None,
            border_color="#1a3a5c",
            border_width=1,
        )

        # 大数字编号
        chapter_num = data.get("chapter_number", "01")
        self.add_text(
            slide, chapter_num,
            s.margins.title_left, 1.5,
            5, 2.5,
            font_size=150,
            bold=True,
            color=self.theme.primary,
        )

        # Part 标签
        part_label = data.get("part_label", "PART ONE")
        self.add_text(
            slide, part_label.upper(),
            s.margins.title_left + 0.2, 4.0,
            4, 0.4,
            font_size=18,
            color=self.theme.gold,
        )

        # 主标题
        title = data.get("title", "章节标题")
        self.add_text(
            slide, title,
            s.margins.title_left + 0.2, 4.4,
            8, 0.8,
            font_size=36,
            bold=True,
            color="#FFFFFF",
        )

        # 分割线
        self.add_line(
            slide,
            s.margins.title_left, 5.4,
            s.margins.title_left + 2, 5.4,
            color=self.theme.gold,
            width=2,
        )

        # 副标题/说明
        subtitle = data.get("subtitle", "")
        if subtitle:
            self.add_text(
                slide, subtitle,
                s.margins.title_left, 5.6,
                8, 0.5,
                font_size=14,
                color=self.theme.caption_color,
            )

        # 底部装饰条
        self.add_rect(
            slide, 0, s.slide.height - 0.06, s.slide.width, 0.06,
            fill_color=self.theme.primary,
        )

        return slide
