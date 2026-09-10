"""
封面页渲染器（浅色 + 深色）。
"""

from __future__ import annotations

from typing import Any

from pptx import Presentation
from pptx.util import Inches

from ..base.renderer_base import RendererBase
from ..theme.theme import ThemeVariant


class CoverLightRenderer(RendererBase):
    """浅色封面页。"""
    page_type = "cover-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 左侧装饰竖条（渐变蓝）
        self.add_rect(
            slide, -0.1, 0, 0.35, s.slide.height,
            fill_color=self.theme.primary,
        )

        # 顶部装饰细线
        self.add_line(
            slide,
            s.margins.title_left, 2.2,
            s.margins.title_left + 2.5, 2.2,
            color=self.theme.primary,
            width=3,
        )

        # 主标题
        title = data.get("title", "点击输入主标题")
        self.add_text(
            slide, title,
            s.margins.title_left, 2.35,
            9, 1.2,
            font_size=self.theme.font_size.h1,
            bold=True,
            color=self.theme.title_color,
            line_spacing=1.2,
        )

        # 英文副标题
        subtitle = data.get("subtitle", "CLICK HERE TO ADD TITLE")
        self.add_text(
            slide, subtitle.upper(),
            s.margins.title_left, 3.6,
            9, 0.4,
            font_size=self.theme.font_size.en_sub if hasattr(self.theme.font_size, 'en_sub') else 14,
            color=self.theme.caption_color,
        )

        # 分割线
        self.add_line(
            slide,
            s.margins.title_left, 4.2,
            s.margins.title_left + 3, 4.2,
            color=self.theme.primary,
            width=2,
        )

        # 汇报人信息
        presenter = data.get("presenter", "汇报人")
        company = data.get("company", "梆梆安全")
        date = data.get("date", "2025.01")

        info_text = f"{presenter}  |  {company}"
        if date:
            info_text += f"\n{date}"

        self.add_text(
            slide, info_text,
            s.margins.title_left, 4.5,
            5, 0.8,
            font_size=20,
            color="#0070C0",
            line_spacing=1.5,
        )

        # Slogan（右下角）
        slogan = data.get("slogan", "")
        if slogan:
            self.add_text(
                slide, slogan,
                8, 6.5,
                4.5, 0.4,
                font_size=14,
                color=self.theme.caption_color,
                align="right",
            )

        # 右上角 Logo 占位（矩形示意）
        if data.get("show_logo", True):
            logo_path = data.get("logo_path", "")
            if logo_path:
                try:
                    self.add_image(slide, logo_path, s.logo.left, s.logo.top, s.logo.width, s.logo.height)
                except FileNotFoundError:
                    self._draw_logo_placeholder(slide)
            else:
                self._draw_logo_placeholder(slide)

        return slide

    def _draw_logo_placeholder(self, slide):
        """绘制 Logo 占位符。"""
        s = self.theme.sizes
        self.add_rect(
            slide, s.logo.left, s.logo.top, s.logo.width, s.logo.height,
            fill_color=self.theme.primary,
            corner_radius=0.05,
        )
        self.add_text(
            slide, "Logo",
            s.logo.left, s.logo.top + 0.12,
            s.logo.width, 0.25,
            font_size=12,
            bold=True,
            color="#FFFFFF",
            align="center",
        )


class CoverDarkRenderer(RendererBase):
    """深色封面页。"""
    page_type = "cover-dark"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "dark")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 顶部装饰条
        self.add_rect(
            slide, 0, 0, s.slide.width, 0.08,
            fill_color=self.theme.primary,
        )

        # 主标题
        title = data.get("title", "点击输入主标题")
        self.add_text(
            slide, title,
            s.margins.title_left, 2.5,
            10, 1.2,
            font_size=44,
            bold=True,
            color=self.theme.title_color,
            line_spacing=1.2,
        )

        # 英文副标题
        subtitle = data.get("subtitle", "BANGCLE PRESENTATION")
        self.add_text(
            slide, subtitle.upper(),
            s.margins.title_left, 3.7,
            10, 0.4,
            font_size=16,
            color=self.theme.caption_color,
        )

        # 白色分割线
        self.add_line(
            slide,
            s.margins.title_left, 4.3,
            s.margins.title_left + 4, 4.3,
            color="#FFFFFF",
            width=2,
        )

        # 汇报人 / 日期
        presenter = data.get("presenter", "汇报人")
        company = data.get("company", "梆梆安全")
        date = data.get("date", "2025.01")

        info_text = f"{presenter}\n{date}"
        self.add_text(
            slide, info_text,
            s.margins.title_left, 4.6,
            5, 0.8,
            font_size=16,
            color="#FFFFFF",
            line_spacing=1.6,
        )

        # 右下 Slogan
        slogan = data.get("slogan", "稳如泰山·值得托付")
        if slogan:
            self.add_text(
                slide, slogan,
                7, 6.6,
                5.5, 0.4,
                font_size=14,
                color=self.theme.caption_color,
                align="right",
            )

        # 金色装饰点
        self.add_circle(
            slide, 12.0, 6.6, 0.15,
            fill_color=self.theme.gold,
        )

        return slide
