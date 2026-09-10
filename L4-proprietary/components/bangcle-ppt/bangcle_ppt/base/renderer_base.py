"""
Renderer 基类 — 所有页面渲染器的公共父类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree

from ..theme.theme import Theme, get_theme


class RendererBase(ABC):
    """
    页面渲染器基类。

    子类需要实现：
    - page_type: 类属性，标识页面类型（如 "cover-light"）
    - render(): 具体渲染逻辑
    """

    page_type: str = "base"

    def __init__(self, theme: Theme | str | None = None):
        """
        Args:
            theme: 主题。str 自动转 Theme 对象。None 用默认浅色。
        """
        if isinstance(theme, str):
            self.theme = get_theme(theme)
        elif isinstance(theme, Theme):
            self.theme = theme
        else:
            self.theme = get_theme("light")

    # ── 公共渲染入口 ──────────────────────────────────────────────

    @abstractmethod
    def render(self, prs: Presentation, data: dict[str, Any] | None = None) -> Any:
        """
        渲染一页幻灯片到 Presentation 中。

        Args:
            prs: python-pptx Presentation 对象
            data: 页面数据（标题、正文等）

        Returns:
            渲染后的 Slide 对象
        """
        ...

    # ── 工具方法 ──────────────────────────────────────────────────

    def add_blank_slide(self, prs: Presentation):
        """添加空白幻灯片（使用第6个布局：空白）。"""
        blank_layout = prs.slide_layouts[6]  # 空白布局
        slide = prs.slides.add_slide(blank_layout)
        # 设置背景色
        self._set_slide_bg(slide, self.theme.bg_color)
        return slide

    def _set_slide_bg(self, slide, color_hex: str):
        """设置幻灯片背景色。"""
        background = slide.background
        fill = background.fill
        fill.solid()
        r, g, b = self.theme.hex_to_tuple(color_hex)
        fill.fore_color.rgb = RGBColor(r, g, b)

    def add_text(
        self,
        slide,
        text: str,
        x: float, y: float, w: float, h: float,
        *,
        font_size: float = 14,
        bold: bool = False,
        color: str | None = None,
        align: str = "left",
        font_family: str | None = None,
        anchor: str = "top",
        line_spacing: float = 1.3,
    ):
        """
        添加文本框（自动设置中英文字体）。

        Args:
            slide: 幻灯片对象
            text: 文本内容（支持 \n 换行）
            x, y, w, h: 位置尺寸（英寸）
            font_size: 字号（pt）
            bold: 是否粗体
            color: 文字颜色（hex）
            align: left / center / right
            font_family: 字体族（默认用主题字体）
            anchor: top / middle / bottom
            line_spacing: 行高倍数
        """
        font_family = font_family or self.theme.font_family
        txBox = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = txBox.text_frame
        tf.word_wrap = True

        # vertical anchor
        anchor_map = {
            "top": MSO_ANCHOR.TOP,
            "middle": MSO_ANCHOR.MIDDLE,
            "bottom": MSO_ANCHOR.BOTTOM,
        }
        if anchor in anchor_map:
            tf.vertical_anchor = anchor_map[anchor]

        align_map = {
            "left": PP_ALIGN.LEFT,
            "center": PP_ALIGN.CENTER,
            "right": PP_ALIGN.RIGHT,
            "justify": PP_ALIGN.JUSTIFY,
        }

        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            p.alignment = align_map.get(align, PP_ALIGN.LEFT)
            p.line_spacing = line_spacing
            run = p.add_run()
            run.text = line
            self._set_run_font(run, font_size=font_size, bold=bold, color=color, font_family=font_family)

        return txBox

    def _set_run_font(
        self,
        run,
        *,
        font_size: float = 14,
        bold: bool = False,
        color: str | None = None,
        font_family: str | None = None,
    ):
        """设置 run 的字体（含 eastAsia 中文字体）。"""
        font_family = font_family or self.theme.font_family
        run.font.name = font_family
        run.font.size = Pt(font_size)
        run.font.bold = bold
        if color:
            r, g, b = self.theme.hex_to_tuple(color)
            run.font.color.rgb = RGBColor(r, g, b)
        # 设置 eastAsia 字体
        rPr = run._r.get_or_add_rPr()
        eastAsia = rPr.find(qn('a:ea'))
        if eastAsia is None:
            eastAsia = etree.SubElement(rPr, qn('a:ea'))
        eastAsia.set('typeface', font_family)
        # 同时设置 latin 字体
        latin = rPr.find(qn('a:latin'))
        if latin is None:
            latin = etree.SubElement(rPr, qn('a:latin'))
        latin.set('typeface', font_family)

    def add_rect(
        self,
        slide,
        x: float, y: float, w: float, h: float,
        *,
        fill_color: str | None = None,
        border_color: str | None = None,
        border_width: float = 1.0,  # pt
        corner_radius: float = 0,   # 英寸，>0 用圆角矩形
        shadow: bool = False,
    ):
        """
        添加矩形（或圆角矩形）。

        注：python-pptx 原生不支持圆角半径的精确控制，
        corner_radius > 0 时使用圆角矩形形状，半径由形状预设。
        """
        from pptx.enum.shapes import MSO_SHAPE

        if corner_radius > 0:
            shape_type = MSO_SHAPE.ROUNDED_RECTANGLE
        else:
            shape_type = MSO_SHAPE.RECTANGLE

        shape = slide.shapes.add_shape(
            shape_type,
            Inches(x), Inches(y), Inches(w), Inches(h),
        )

        # 填充
        if fill_color:
            shape.fill.solid()
            r, g, b = self.theme.hex_to_tuple(fill_color)
            shape.fill.fore_color.rgb = RGBColor(r, g, b)
        else:
            shape.fill.background()  # 透明

        # 边框
        if border_color:
            shape.line.color.rgb = RGBColor(*self.theme.hex_to_tuple(border_color))
            shape.line.width = Pt(border_width)
        else:
            shape.line.fill.background()  # 无边框

        return shape

    def add_line(
        self,
        slide,
        x1: float, y1: float, x2: float, y2: float,
        *,
        color: str = "#000000",
        width: float = 1.0,  # pt
    ):
        """添加直线。"""
        from pptx.enum.shapes import MSO_SHAPE

        line = slide.shapes.add_connector(
            1,  # msoConnectorStraight
            Inches(x1), Inches(y1), Inches(x2), Inches(y2),
        )
        r, g, b = self.theme.hex_to_tuple(color)
        line.line.color.rgb = RGBColor(r, g, b)
        line.line.width = Pt(width)
        return line

    def add_circle(
        self,
        slide,
        x: float, y: float, size: float,
        *,
        fill_color: str | None = None,
        border_color: str | None = None,
        border_width: float = 1.0,
    ):
        """添加圆形（正圆）。x, y 为左上角。"""
        from pptx.enum.shapes import MSO_SHAPE

        shape = slide.shapes.add_shape(
            MSO_SHAPE.OVAL,
            Inches(x), Inches(y), Inches(size), Inches(size),
        )
        if fill_color:
            shape.fill.solid()
            r, g, b = self.theme.hex_to_tuple(fill_color)
            shape.fill.fore_color.rgb = RGBColor(r, g, b)
        else:
            shape.fill.background()

        if border_color:
            shape.line.color.rgb = RGBColor(*self.theme.hex_to_tuple(border_color))
            shape.line.width = Pt(border_width)
        else:
            shape.line.fill.background()

        return shape

    def add_image(
        self,
        slide,
        image_path: str,
        x: float, y: float,
        w: float | None = None,
        h: float | None = None,
    ):
        """添加图片。"""
        import os
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        return slide.shapes.add_picture(
            image_path,
            Inches(x), Inches(y),
            width=Inches(w) if w else None,
            height=Inches(h) if h else None,
        )

    def add_table(
        self,
        slide,
        x: float, y: float, w: float, h: float,
        rows: int, cols: int,
        data: list[list] | None = None,
        *,
        header: bool = True,
        header_bg: str | None = None,
        font_size: float = 12,
        header_font_size: float = 14,
        border_color: str | None = None,
    ):
        """添加表格。"""
        table_shape = slide.shapes.add_table(
            rows, cols,
            Inches(x), Inches(y), Inches(w), Inches(h),
        )
        table = table_shape.table

        if data:
            for r in range(min(rows, len(data))):
                row_data = data[r]
                for c in range(min(cols, len(row_data))):
                    cell = table.cell(r, c)
                    cell.text = ""
                    tf = cell.text_frame
                    tf.word_wrap = True
                    p = tf.paragraphs[0]
                    run = p.add_run()
                    run.text = str(row_data[c])
                    is_header = header and r == 0
                    fs = header_font_size if is_header else font_size
                    self._set_run_font(run, font_size=fs, bold=is_header,
                                       color=self.theme.title_color if is_header else self.theme.body_color)
                    if is_header and header_bg:
                        cell.fill.solid()
                        r_, g_, b_ = self.theme.hex_to_tuple(header_bg)
                        cell.fill.fore_color.rgb = RGBColor(r_, g_, b_)

        if border_color:
            # 简单处理：通过单元格边框 XML 设置（较复杂，此处留接口）
            pass

        return table_shape

    # ── 装饰元素 ──────────────────────────────────────────────────

    def add_left_accent_line(self, slide, x: float, y: float, height: float, *, color: str | None = None, width: float = 3):
        """左侧装饰竖线。"""
        return self.add_line(slide, x, y, x, y + height, color=color or self.theme.primary, width=width)

    def add_page_header(self, slide, title: str, subtitle: str = ""):
        """
        添加页面标准标题区（主标题 + 英文副标题）。

        Returns:
            标题底部 y 坐标，用于后续内容定位参考。
        """
        s = self.theme.sizes
        # 左侧装饰线
        self.add_left_accent_line(
            slide,
            s.margins.title_left,
            s.margins.title_top,
            0.5,
            width=3,
        )
        # 主标题
        self.add_text(
            slide, title,
            s.margins.title_left + 0.15, s.margins.title_top - 0.05,
            10, 0.55,
            font_size=self.theme.font_size.h1,
            bold=True,
            color=self.theme.title_color,
        )
        # 英文副标题（全大写）
        sub_y = s.margins.title_top + 0.55
        if subtitle:
            self.add_text(
                slide, subtitle.upper(),
                s.margins.title_left + 0.15, sub_y,
                10, 0.25,
                font_size=self.theme.font_size.en_sub if hasattr(self.theme.font_size, 'en_sub') else 14,
                color=self.theme.caption_color,
            )
            sub_y += 0.25

        # 底部分割线
        line_y = sub_y + 0.1
        self.add_line(
            slide,
            s.margins.title_left, line_y,
            s.margins.content_right, line_y,
            color=self.theme.divider_color,
            width=0.75,
        )
        return line_y + 0.15  # 内容起始 y
