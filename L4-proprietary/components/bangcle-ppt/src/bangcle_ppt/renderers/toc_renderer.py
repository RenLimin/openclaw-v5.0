"""
目录页渲染器（浅色 + 深色）。
"""

from __future__ import annotations

from typing import Any

from pptx import Presentation

from ..base.renderer_base import RendererBase


class TocLightRenderer(RendererBase):
    """浅色目录页（2×2 卡片式）。"""
    page_type = "toc-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 左侧竖条装饰
        self.add_rect(
            slide, 0.4, 0.8, 0.12, 5.8,
            fill_color=self.theme.primary,
        )

        # "目录" 大标题
        self.add_text(
            slide, "目  录",
            0.7, 1.0,
            3, 0.9,
            font_size=60,
            bold=True,
            color=self.theme.title_color,
        )

        # "Contents" 英文
        self.add_text(
            slide, "Contents",
            0.75, 2.0,
            3, 0.5,
            font_size=28,
            color=self.theme.subtitle_color,
        )

        # 2x2 目录卡片
        items = data.get("items", [])
        if not items:
            items = [
                {"number": "01", "title": "第一部分标题", "subtitle": "PART ONE", "part": ""},
                {"number": "02", "title": "第二部分标题", "subtitle": "PART TWO", "part": ""},
                {"number": "03", "title": "第三部分标题", "subtitle": "PART THREE", "part": ""},
                {"number": "04", "title": "第四部分标题", "subtitle": "PART FOUR", "part": ""},
            ]

        # 网格位置：右侧 2x2
        grid_x_start = 5.0
        grid_y_start = 1.2
        card_w = 3.6
        card_h = 2.4
        gap_x = 0.5
        gap_y = 0.6

        for i, item in enumerate(items[:4]):
            col = i % 2
            row = i // 2
            x = grid_x_start + col * (card_w + gap_x)
            y = grid_y_start + row * (card_h + gap_y)

            # 卡片底（白色 + 细边）
            self.add_rect(
                slide, x, y, card_w, card_h,
                fill_color="#FFFFFF",
                border_color=self.theme.card_border_color,
                border_width=1,
                corner_radius=0.05,
            )

            # 顶部装饰条
            self.add_rect(
                slide, x, y, card_w, 0.08,
                fill_color=self.theme.primary,
            )

            # 大数字
            num = str(item.get("number", f"0{i+1}"))
            self.add_text(
                slide, num,
                x + 0.3, y + 0.25,
                1.5, 0.9,
                font_size=48,
                bold=True,
                color=self.theme.primary,
            )

            # Part 标签
            subtitle = item.get("subtitle", "")
            if subtitle:
                self.add_text(
                    slide, subtitle.upper(),
                    x + card_w - 1.8, y + 0.5,
                    1.5, 0.3,
                    font_size=10,
                    color=self.theme.caption_color,
                    align="right",
                )

            # 标题
            title = item.get("title", f"目录项 {i+1}")
            self.add_text(
                slide, title,
                x + 0.3, y + 1.3,
                card_w - 0.6, 0.5,
                font_size=self.theme.font_size.h4 if hasattr(self.theme.font_size, 'h4') else 24,
                bold=True,
                color=self.theme.title_color,
            )

            # 分割线
            self.add_line(
                slide,
                x + 0.3, y + 1.9,
                x + 1.0, y + 1.9,
                color=self.theme.primary,
                width=1.5,
            )

            # 说明
            desc = item.get("description", "")
            if desc:
                self.add_text(
                    slide, desc,
                    x + 0.3, y + 2.0,
                    card_w - 0.6, 0.3,
                    font_size=self.theme.font_size.caption if hasattr(self.theme.font_size, 'caption') else 11,
                    color=self.theme.caption_color,
                )

        return slide


class TocDarkRenderer(RendererBase):
    """深色目录页（左右两列 + 圆形数字）。"""
    page_type = "toc-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 左侧目录标签
        self.add_text(
            slide, "CONTENTS",
            s.margins.title_left, 0.8,
            4, 0.4,
            font_size=14,
            color=self.theme.caption_color,
        )
        self.add_text(
            slide, "目  录",
            s.margins.title_left, 1.2,
            4, 0.8,
            font_size=44,
            bold=True,
            color="#FFFFFF",
        )

        # 分割线
        self.add_line(
            slide,
            s.margins.title_left, 2.1,
            s.margins.title_left + 2, 2.1,
            color=self.theme.gold,
            width=2,
        )

        items = data.get("items", [])
        if not items:
            items = [
                {"number": "01", "title": "第一部分", "subtitle": "Overview"},
                {"number": "02", "title": "第二部分", "subtitle": "Solution"},
                {"number": "03", "title": "第三部分", "subtitle": "Features"},
                {"number": "04", "title": "第四部分", "subtitle": "Summary"},
            ]

        # 目录项列表
        start_y = 2.5
        item_h = 0.9
        for i, item in enumerate(items[:6]):
            y = start_y + i * item_h

            # 圆形数字
            self.add_circle(
                slide, s.margins.title_left, y, 0.5,
                fill_color=None,
                border_color=self.theme.primary,
                border_width=2,
            )
            self.add_text(
                slide, str(item.get("number", f"0{i+1}")),
                s.margins.title_left, y + 0.08,
                0.5, 0.35,
                font_size=14,
                bold=True,
                color="#FFFFFF",
                align="center",
            )

            # 标题
            self.add_text(
                slide, item.get("title", f"目录项 {i+1}"),
                s.margins.title_left + 0.8, y - 0.02,
                5, 0.4,
                font_size=20,
                bold=True,
                color="#FFFFFF",
            )

            # 英文副标题
            subtitle = item.get("subtitle", "")
            if subtitle:
                self.add_text(
                    slide, subtitle.upper(),
                    s.margins.title_left + 0.8, y + 0.4,
                    5, 0.3,
                    font_size=11,
                    color=self.theme.caption_color,
                )

        # 右侧装饰
        self.add_rect(
            slide, 10.5, 0, 0.1, s.slide.height,
            fill_color=self.theme.primary,
        )
        # 右侧点缀
        self.add_circle(
            slide, 11.5, 5.5, 1.5,
            fill_color=None,
            border_color=self.theme.primary,
            border_width=1,
        )
        self.add_circle(
            slide, 11.8, 5.8, 0.9,
            fill_color=None,
            border_color=self.theme.gold,
            border_width=1,
        )

        return slide
