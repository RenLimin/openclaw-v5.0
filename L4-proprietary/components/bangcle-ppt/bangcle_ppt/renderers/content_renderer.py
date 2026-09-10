"""
内容页渲染器：图文混排、三卡片、时间轴等多种内容页面。
"""

from __future__ import annotations

from typing import Any

from pptx import Presentation

from ..base.renderer_base import RendererBase


class ContentTwoColLightRenderer(RendererBase):
    """
    图文混排页（浅色）：
    - 顶部 4 个要点（竖线装饰 + 标题 + 说明）
    - 下方：左卡片（标题 + 正文）+ 右图片
    """
    page_type = "content-two-col-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        # 页面标题
        content_top = self.add_page_header(
            slide,
            data.get("title", "图文混排标题"),
            data.get("subtitle", "CONTENT SUBTITLE"),
        )

        # 上方 4 个要点
        highlights = data.get("highlights", [])
        if not highlights:
            highlights = [
                {"icon": "●", "title": "要点一", "description": "简要说明文字"},
                {"icon": "●", "title": "要点二", "description": "简要说明文字"},
                {"icon": "●", "title": "要点三", "description": "简要说明文字"},
                {"icon": "●", "title": "要点四", "description": "简要说明文字"},
            ]

        hl_top = content_top + 0.1
        hl_width = 3.0
        hl_height = 1.0
        hl_gap = 0.2
        hl_start_x = self.theme.sizes.margins.content_left

        for i, item in enumerate(highlights[:4]):
            col = i % 2
            row = i // 2
            x = hl_start_x + col * (hl_width + hl_gap + 0.3)
            y = hl_top + row * (hl_height + 0.1)

            # 左侧竖线
            self.add_left_accent_line(slide, x, y, 0.4, width=3)

            # 标题
            self.add_text(
                slide, item.get("title", f"要点 {i+1}"),
                x + 0.2, y - 0.05,
                hl_width - 0.2, 0.35,
                font_size=self.theme.font_size.h5 if hasattr(self.theme.font_size, 'h5') else 20,
                bold=True,
                color=self.theme.title_color,
            )

            # 说明
            desc = item.get("description", "")
            self.add_text(
                slide, desc,
                x + 0.2, y + 0.35,
                hl_width - 0.2, 0.5,
                font_size=self.theme.font_size.body if hasattr(self.theme.font_size, 'body') else 14,
                color=self.theme.body_color,
                line_spacing=1.3,
            )

        # 下方：左卡片 + 右图片
        bottom_y = hl_top + 2.2
        card_w = self.theme.sizes.card.two_col_width
        card_h = self.theme.sizes.card.two_col_height

        # 左侧卡片
        self.add_rect(
            slide, hl_start_x, bottom_y, card_w, card_h,
            fill_color="#FFFFFF",
            border_color=self.theme.card_border_color,
            border_width=1,
            corner_radius=0.08,
        )

        # 卡片标题
        self.add_text(
            slide, data.get("card_title", "内容卡片标题"),
            hl_start_x + 0.3, bottom_y + 0.25,
            card_w - 0.6, 0.4,
            font_size=self.theme.font_size.h5 if hasattr(self.theme.font_size, 'h5') else 20,
            bold=True,
            color=self.theme.title_color,
        )

        # 卡片分割线
        self.add_line(
            slide,
            hl_start_x + 0.3, bottom_y + 0.75,
            hl_start_x + 1.0, bottom_y + 0.75,
            color=self.theme.primary,
            width=2,
        )

        # 卡片正文
        card_body = data.get("card_body", "在这里输入你的正文阐述，\n支持多行文字内容展示。")
        self.add_text(
            slide, card_body,
            hl_start_x + 0.3, bottom_y + 0.9,
            card_w - 0.6, card_h - 1.1,
            font_size=self.theme.font_size.body if hasattr(self.theme.font_size, 'body') else 14,
            color=self.theme.body_color,
            line_spacing=1.4,
        )

        # 右侧图片占位
        img_x = hl_start_x + card_w + 0.5
        img_w = self.theme.sizes.slide.width - img_x - self.theme.sizes.margins.content_right + 0.2
        img_path = data.get("image_path", "")
        if img_path:
            try:
                self.add_image(slide, img_path, img_x, bottom_y, img_w, card_h)
            except FileNotFoundError:
                self._draw_image_placeholder(slide, img_x, bottom_y, img_w, card_h)
        else:
            self._draw_image_placeholder(slide, img_x, bottom_y, img_w, card_h)

        return slide

    def _draw_image_placeholder(self, slide, x, y, w, h):
        """图片占位符。"""
        self.add_rect(
            slide, x, y, w, h,
            fill_color="#F0F4F8",
            border_color="#D0D8E0",
            border_width=1,
            corner_radius=0.08,
        )
        self.add_text(
            slide, "📷\n图片占位",
            x, y + h / 2 - 0.5,
            w, 1,
            font_size=14,
            color="#99AABB",
            align="center",
            anchor="middle",
        )


class ThreeCardsLightRenderer(RendererBase):
    """
    三卡片 + 横幅图（浅色）。
    - 顶部：标题 + 横幅图
    - 底部：3 张浮动卡片（错开排列）
    """
    page_type = "content-three-cards-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 页面标题
        content_top = self.add_page_header(
            slide,
            data.get("title", "三卡片标题"),
            data.get("subtitle", "THREE CARDS"),
        )

        # 横幅图占位
        banner_h = 2.2
        banner_y = content_top + 0.1
        banner_img = data.get("banner_image", "")
        if banner_img:
            try:
                self.add_image(slide, banner_img, 0, banner_y, s.slide.width, banner_h)
            except FileNotFoundError:
                self._draw_banner(slide, banner_y, banner_h)
        else:
            self._draw_banner(slide, banner_y, banner_h)

        # 三张浮动卡片（错开高度）
        cards = data.get("cards", [])
        if not cards:
            cards = [
                {"number": "01", "title": "能力一", "body": "描述能力一的具体内容和优势特点。"},
                {"number": "02", "title": "能力二", "body": "描述能力二的具体内容和优势特点。"},
                {"number": "03", "title": "能力三", "body": "描述能力三的具体内容和优势特点。"},
            ]

        card_w = 3.5
        card_h = 2.4
        card_y_base = banner_y + banner_h - 0.6  # 浮在横幅底部
        gap = (s.slide.width - s.margins.content_left - 0.8 - 3 * card_w) / 2
        offsets_y = [0, 0.2, 0]  # 中间卡片略低，形成错落感

        for i, card in enumerate(cards[:3]):
            x = s.margins.content_left + i * (card_w + gap)
            y = card_y_base + offsets_y[i]

            # 卡片底
            self.add_rect(
                slide, x, y, card_w, card_h,
                fill_color="#FFFFFF",
                border_color=self.theme.card_border_color,
                border_width=1,
                corner_radius=0.1,
            )

            # 圆形编号
            self.add_circle(
                slide, x + 0.3, y + 0.25, 0.5,
                fill_color=self.theme.primary,
            )
            self.add_text(
                slide, str(card.get("number", f"0{i+1}")),
                x + 0.3, y + 0.33,
                0.5, 0.35,
                font_size=14,
                bold=True,
                color="#FFFFFF",
                align="center",
            )

            # 标题
            self.add_text(
                slide, card.get("title", f"卡片 {i+1}"),
                x + 0.95, y + 0.3,
                card_w - 1.2, 0.4,
                font_size=self.theme.font_size.h5 if hasattr(self.theme.font_size, 'h5') else 20,
                bold=True,
                color=self.theme.title_color,
            )

            # 分割线
            self.add_line(
                slide,
                x + 0.3, y + 0.95,
                x + card_w - 0.3, y + 0.95,
                color=self.theme.divider_color,
                width=0.5,
            )

            # 正文
            body = card.get("body", "")
            self.add_text(
                slide, body,
                x + 0.3, y + 1.1,
                card_w - 0.6, card_h - 1.3,
                font_size=self.theme.font_size.body_sm if hasattr(self.theme.font_size, 'body_sm') else 12,
                color=self.theme.body_color,
                line_spacing=1.4,
            )

        return slide

    def _draw_banner(self, slide, y, h):
        """横幅图占位（渐变蓝色块）。"""
        s = self.theme.sizes
        self.add_rect(
            slide, 0, y, s.slide.width, h,
            fill_color=self.theme.primary,
        )
        # 装饰文字
        self.add_text(
            slide, "BANNER IMAGE",
            0, y + h / 2 - 0.2,
            s.slide.width, 0.4,
            font_size=14,
            color="#FFFFFF",
            align="center",
        )


class TimelineThreeCardsLightRenderer(RendererBase):
    """
    时间轴 + 三卡片（浅色）。
    - 顶部：横向箭头时间轴 + 3 个节点
    - 下方：3 张圆角卡片
    """
    page_type = "timeline-three-cards-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 页面标题
        content_top = self.add_page_header(
            slide,
            data.get("title", "发展历程"),
            data.get("subtitle", "TIMELINE"),
        )

        items = data.get("items", [])
        if not items:
            items = [
                {"step": "01", "title": "阶段一", "body": "阶段一的详细描述和里程碑成果。"},
                {"step": "02", "title": "阶段二", "body": "阶段二的详细描述和里程碑成果。"},
                {"step": "03", "title": "阶段三", "body": "阶段三的详细描述和里程碑成果。"},
            ]

        # 横向时间轴
        timeline_y = content_top + 0.4
        timeline_left = s.margins.content_left + 0.5
        timeline_right = s.slide.width - s.margins.content_right - 0.3
        self.add_line(
            slide,
            timeline_left, timeline_y,
            timeline_right, timeline_y,
            color=self.theme.primary,
            width=2.5,
        )

        # 3 个节点 + 上方圆形 icon
        card_w = 3.5
        card_h = 2.6
        gap = (timeline_right - timeline_left - 3 * card_w) / 2

        for i, item in enumerate(items[:3]):
            x_center = timeline_left + card_w / 2 + i * (card_w + gap)

            # 节点圆
            self.add_circle(
                slide, x_center - 0.12, timeline_y - 0.12, 0.24,
                fill_color=self.theme.primary,
                border_color="#FFFFFF",
                border_width=2,
            )

            # 上方 icon 圆
            icon_circle_size = 0.7
            self.add_circle(
                slide, x_center - icon_circle_size / 2, timeline_y - 0.95, icon_circle_size,
                fill_color="#FFFFFF",
                border_color=self.theme.primary,
                border_width=2,
            )
            self.add_text(
                slide, str(item.get("step", f"0{i+1}")),
                x_center - icon_circle_size / 2, timeline_y - 0.87,
                icon_circle_size, 0.5,
                font_size=14,
                bold=True,
                color=self.theme.primary,
                align="center",
            )

            # 下方卡片
            card_y = timeline_y + 0.4
            card_x = x_center - card_w / 2
            self.add_rect(
                slide, card_x, card_y, card_w, card_h,
                fill_color="#FFFFFF",
                border_color="#BEE3FA",
                border_width=1,
                corner_radius=0.1,
            )

            # 卡片标题
            self.add_text(
                slide, item.get("title", f"阶段 {i+1}"),
                card_x + 0.3, card_y + 0.25,
                card_w - 0.6, 0.4,
                font_size=self.theme.font_size.h5 if hasattr(self.theme.font_size, 'h5') else 20,
                bold=True,
                color=self.theme.title_color,
            )

            # 标题下方装饰线
            self.add_line(
                slide,
                card_x + 0.3, card_y + 0.75,
                card_x + 1.0, card_y + 0.75,
                color=self.theme.primary,
                width=2,
            )

            # 卡片正文
            body = item.get("body", "")
            self.add_text(
                slide, body,
                card_x + 0.3, card_y + 0.9,
                card_w - 0.6, card_h - 1.1,
                font_size=self.theme.font_size.body_sm if hasattr(self.theme.font_size, 'body_sm') else 12,
                color=self.theme.body_color,
                line_spacing=1.4,
            )

        return slide


class DataChartLightRenderer(RendererBase):
    """
    数据 + 图表页（浅色）。
    - 顶部：4 个 KPI 指标
    - 下方：左图表 + 右说明
    """
    page_type = "data-chart-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)
        s = self.theme.sizes

        # 页面标题
        content_top = self.add_page_header(
            slide,
            data.get("title", "数据分析"),
            data.get("subtitle", "DATA ANALYTICS"),
        )

        # 4 个 KPI 指标
        kpis = data.get("kpis", [])
        if not kpis:
            kpis = [
                {"value": "99.9%", "label": "安全防护率", "suffix": ""},
                {"value": "1000+", "label": "服务客户", "suffix": ""},
                {"value": "50亿", "label": "日检测量", "suffix": "次"},
                {"value": "24/7", "label": "全天候监控", "suffix": ""},
            ]

        kpi_y = content_top + 0.1
        kpi_h = 1.1
        kpi_w = 2.8
        kpi_gap = 0.15
        kpi_start_x = s.margins.content_left

        for i, kpi in enumerate(kpis[:4]):
            x = kpi_start_x + i * (kpi_w + kpi_gap)

            # KPI 卡片底
            self.add_rect(
                slide, x, kpi_y, kpi_w, kpi_h,
                fill_color="#F8FAFD",
                border_color="#E0EAF5",
                border_width=1,
                corner_radius=0.08,
            )

            # 左侧竖线装饰
            self.add_rect(
                slide, x, kpi_y + 0.15, 0.06, kpi_h - 0.3,
                fill_color=self.theme.primary,
            )

            # 大数字
            value = str(kpi.get("value", "0"))
            suffix = kpi.get("suffix", "")
            self.add_text(
                slide, f"{value}{suffix}",
                x + 0.25, kpi_y + 0.1,
                kpi_w - 0.35, 0.55,
                font_size=26,
                bold=True,
                color=self.theme.primary,
            )

            # 标签
            label = kpi.get("label", "")
            self.add_text(
                slide, label,
                x + 0.25, kpi_y + 0.65,
                kpi_w - 0.35, 0.35,
                font_size=self.theme.font_size.body if hasattr(self.theme.font_size, 'body') else 14,
                color=self.theme.body_color,
            )

        # 下方：左图表 + 右说明
        chart_y = kpi_y + kpi_h + 0.3
        chart_w = 6.5
        chart_h = 3.2

        # 图表占位（用蓝色渐变块 + 假柱状图）
        self._draw_chart_placeholder(slide, kpi_start_x, chart_y, chart_w, chart_h, data)

        # 右侧说明卡片
        right_x = kpi_start_x + chart_w + 0.4
        right_w = s.slide.width - right_x - s.margins.content_right + 0.2
        self.add_rect(
            slide, right_x, chart_y, right_w, chart_h,
            fill_color="#FFFFFF",
            border_color=self.theme.card_border_color,
            border_width=1,
            corner_radius=0.08,
        )

        # 右侧标题
        right_title = data.get("right_title", "关键发现")
        self.add_text(
            slide, right_title,
            right_x + 0.3, chart_y + 0.25,
            right_w - 0.6, 0.4,
            font_size=self.theme.font_size.h5 if hasattr(self.theme.font_size, 'h5') else 20,
            bold=True,
            color=self.theme.title_color,
        )
        self.add_line(
            slide,
            right_x + 0.3, chart_y + 0.75,
            right_x + 1.0, chart_y + 0.75,
            color=self.theme.primary,
            width=2,
        )

        # 右侧正文
        right_body = data.get("right_body", "数据分析的核心结论和关键发现摘要。\n\n• 趋势分析\n• 同比增长\n• 关键指标解读")
        self.add_text(
            slide, right_body,
            right_x + 0.3, chart_y + 0.9,
            right_w - 0.6, chart_h - 1.1,
            font_size=self.theme.font_size.body_sm if hasattr(self.theme.font_size, 'body_sm') else 12,
            color=self.theme.body_color,
            line_spacing=1.5,
        )

        return slide

    def _draw_chart_placeholder(self, slide, x, y, w, h, data):
        """图表占位（简易柱状图示意）。"""
        # 背景
        self.add_rect(
            slide, x, y, w, h,
            fill_color="#F8FAFD",
            border_color="#E0EAF5",
            border_width=1,
            corner_radius=0.08,
        )
        # 图表标题
        chart_title = data.get("chart_title", "数据趋势图")
        self.add_text(
            slide, chart_title,
            x + 0.3, y + 0.15,
            w - 0.6, 0.35,
            font_size=14,
            bold=True,
            color=self.theme.title_color,
        )
        # 假柱状图（5 个柱子，高度递增）
        bar_count = 5
        bar_w = 0.4
        gap = (w - 1.0 - bar_count * bar_w) / (bar_count - 1)
        chart_bottom = y + h - 0.4
        bar_start_x = x + 0.5

        for i in range(bar_count):
            bx = bar_start_x + i * (bar_w + gap)
            bar_h_ratio = 0.2 + i * 0.15  # 20% ~ 80%
            bh = (h - 1.2) * min(bar_h_ratio, 0.9)
            by = chart_bottom - bh

            self.add_rect(
                slide, bx, by, bar_w, bh,
                fill_color=self.theme.primary if i % 2 == 0 else "#5B9BD5",
                corner_radius=0.03,
            )

        # 底部基线
        self.add_line(
            slide,
            bar_start_x - 0.2, chart_bottom,
            bar_start_x + bar_count * (bar_w + gap) - gap + 0.2, chart_bottom,
            color="#D0D8E0",
            width=0.75,
        )


class ListLightRenderer(RendererBase):
    """
    列表页（浅色）：要点列表/编号列表。
    """
    page_type = "list-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        # 页面标题
        content_top = self.add_page_header(
            slide,
            data.get("title", "要点列表"),
            data.get("subtitle", "KEY POINTS"),
        )

        items = data.get("items", [])
        if not items:
            items = [
                "第一点：核心要点说明文字",
                "第二点：核心要点说明文字",
                "第三点：核心要点说明文字",
                "第四点：核心要点说明文字",
                "第五点：核心要点说明文字",
                "第六点：核心要点说明文字",
            ]

        numbered = data.get("numbered", False)
        icon = data.get("icon", "●")

        s = self.theme.sizes
        list_x = s.margins.content_left
        list_y = content_top + 0.3
        item_h = 0.55

        for i, item_text in enumerate(items[:8]):
            y = list_y + i * item_h

            # 编号或 bullet
            if numbered:
                bullet = f"{i+1:02d}"
                self.add_circle(
                    slide, list_x, y + 0.08, 0.4,
                    fill_color=self.theme.primary,
                )
                self.add_text(
                    slide, bullet,
                    list_x, y + 0.14,
                    0.4, 0.3,
                    font_size=12,
                    bold=True,
                    color="#FFFFFF",
                    align="center",
                )
                text_x = list_x + 0.6
            else:
                self.add_text(
                    slide, icon,
                    list_x, y + 0.08,
                    0.4, 0.35,
                    font_size=14,
                    color=self.theme.primary,
                )
                text_x = list_x + 0.4

            # 列表项文字
            self.add_text(
                slide, item_text,
                text_x, y + 0.02,
                11, 0.5,
                font_size=self.theme.font_size.body if hasattr(self.theme.font_size, 'body') else 14,
                color=self.theme.body_color,
                line_spacing=1.4,
            )

        return slide


class TextOnlyLightRenderer(RendererBase):
    """
    纯文本/引文页（浅色）。
    """
    page_type = "text-only-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        # 页面标题
        content_top = self.add_page_header(
            slide,
            data.get("title", "大段文字标题"),
            data.get("subtitle", "DETAILS"),
        )

        s = self.theme.sizes
        is_quote = data.get("is_quote", False)
        body = data.get("body", "这里是大段文字内容。\n\n支持多行文字展示，适合详细说明、方案阐述、数据解读等场景。\n\n文字排版清晰，行高适中，确保可读性。")

        text_x = s.margins.content_left
        text_y = content_top + 0.3
        text_w = s.slide.width - s.margins.content_right - text_x + 0.2
        text_h = s.slide.height - text_y - s.margins.bottom_safe - 0.2

        if is_quote:
            # 引文样式：左侧大引号 + 缩进
            self.add_text(
                slide, "「",
                text_x, text_y,
                0.8, 0.8,
                font_size=48,
                color=self.theme.primary,
            )
            self.add_text(
                slide, body,
                text_x + 0.8, text_y + 0.3,
                text_w - 1.0, text_h - 0.5,
                font_size=18,
                color=self.theme.body_color,
                line_spacing=1.6,
            )
            # 引文作者
            author = data.get("author", "")
            if author:
                self.add_text(
                    slide, f"— {author}",
                    text_x + text_w - 3, text_y + text_h - 0.5,
                    3, 0.35,
                    font_size=14,
                    color=self.theme.caption_color,
                    align="right",
                )
        else:
            # 普通纯文本
            self.add_text(
                slide, body,
                text_x, text_y,
                text_w, text_h,
                font_size=self.theme.font_size.body if hasattr(self.theme.font_size, 'body') else 14,
                color=self.theme.body_color,
                line_spacing=1.6,
            )

        return slide


class KpiCardsLightRenderer(RendererBase):
    """
    KPI 数据卡片页（浅色）：4 个核心指标大卡片。
    """
    page_type = "kpi-cards-light"

    def __init__(self, theme=None):
        super().__init__(theme=theme or "light")

    def render(self, prs: Presentation, data: dict[str, Any] | None = None):
        data = data or {}
        slide = self.add_blank_slide(prs)

        # 页面标题
        content_top = self.add_page_header(
            slide,
            data.get("title", "关键指标"),
            data.get("subtitle", "KEY METRICS"),
        )

        cards = data.get("cards", [])
        if not cards:
            cards = [
                {"value": "99.9%", "label": "系统可用性", "suffix": ""},
                {"value": "500", "label": "企业客户", "suffix": "+"},
                {"value": "10", "label": "年行业经验", "suffix": "年"},
                {"value": "2000", "label": "专业团队", "suffix": "人"},
            ]

        s = self.theme.sizes
        card_w = 2.8
        card_h = 2.8
        gap = 0.3
        start_x = s.margins.content_left + 0.2
        start_y = content_top + 0.6

        for i, card in enumerate(cards[:4]):
            col = i % 4
            x = start_x + col * (card_w + gap)
            y = start_y

            # 卡片底
            self.add_rect(
                slide, x, y, card_w, card_h,
                fill_color="#FFFFFF",
                border_color="#BEE3FA",
                border_width=1.5,
                corner_radius=0.12,
            )

            # 顶部装饰条
            self.add_rect(
                slide, x, y, card_w, 0.08,
                fill_color=self.theme.primary,
            )

            # 大数字
            value = str(card.get("value", "0"))
            suffix = card.get("suffix", "")
            self.add_text(
                slide, f"{value}{suffix}",
                x, y + 0.5,
                card_w, 1.0,
                font_size=36,
                bold=True,
                color=self.theme.primary,
                align="center",
            )

            # 分割线
            self.add_line(
                slide,
                x + card_w / 2 - 0.5, y + 1.6,
                x + card_w / 2 + 0.5, y + 1.6,
                color=self.theme.divider_color,
                width=1,
            )

            # 标签
            label = card.get("label", "")
            self.add_text(
                slide, label,
                x + 0.2, y + 1.8,
                card_w - 0.4, 0.5,
                font_size=16,
                color=self.theme.body_color,
                align="center",
                line_spacing=1.3,
            )

        return slide
