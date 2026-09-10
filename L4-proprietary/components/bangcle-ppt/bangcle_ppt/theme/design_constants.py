"""
Bangcle PPT 设计系统常量
从官方模板提取的标准化设计常量
组件 ID: CPT-012
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── 色彩体系 ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ColorPalette:
    """VI 标准色 + 辅助色。"""
    # VI 标准色 (C-01 ~ C-07)
    primary: str = "#2D74BB"        # C-01 主色（梆梆蓝）
    light_blue: str = "#3FA1DA"     # C-02 浅蓝
    cyan: str = "#27AABF"           # C-03 青色
    green: str = "#33ADA0"          # C-04 青绿
    gold: str = "#EFBA20"           # C-05 金色
    dark_blue: str = "#00122B"      # C-06 深藏青
    dark_gray: str = "#595757"      # C-07 深灰

    # 辅助色
    very_light_blue: str = "#BEE3FA"
    light_gray: str = "#E7E6E6"
    bright_blue: str = "#649CEF"
    medium_blue: str = "#5B9BD5"
    pure_blue: str = "#0081FF"
    gray_blue: str = "#387BBE"
    dark_gray_blue: str = "#4073B5"
    gold_brown: str = "#DCBA84"
    medium_gray: str = "#BFBFBF"
    light_caption_gray: str = "#A7A7A7"

    white: str = "#FFFFFF"
    black: str = "#000000"


# ── 文字色 ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TextColors:
    """浅色/深色模板文字色。"""
    # 浅色模板
    light_title: str = "#2D74BB"
    light_subtitle: str = "#387BBE"
    light_body: str = "#595757"
    light_caption: str = "#A7A7A7"
    light_accent: str = "#2D74BB"

    # 深色模板
    dark_title: str = "#FFFFFF"
    dark_subtitle: str = "#FFFFFF"
    dark_body: str = "#FFFFFF"
    dark_caption: str = "#BEE3FA"
    dark_accent: str = "#EFBA20"


# ── 背景色 ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BgColors:
    light: str = "#FFFFFF"
    dark: str = "#00122B"


# ── 边框色 ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BorderColors:
    light_card: str = "#E7E6E6"
    dark_card: str = "#2D74BB"


# ── 字体系统 ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FontSpec:
    family: str = "Source Han Sans"
    fallback: str = "Microsoft YaHei"

    # 字重
    heavy: int = 900
    medium: int = 500
    bold: int = 700
    normal: int = 400

    # 字号层级（浅色模板，单位 pt）
    @dataclass(frozen=True)
    class LightSizes:
        h0: float = 138.0      # 封面大标题 / 巨大编号
        h1: float = 36.0       # 页面主标题
        h2: float = 32.0       # 章节副标题
        h3: float = 28.0       # 目录标题
        h4: float = 24.0       # 内容小标题 / 目录项标题
        h5: float = 20.0       # 卡片标题
        body: float = 14.0     # 正文
        body_sm: float = 12.0  # 小字正文
        caption: float = 11.0  # 辅助文字
        en_sub: float = 14.0   # 英文副标题
        number: float = 28.0   # 编号数字

    # 字号层级（深色模板，单位 pt）
    @dataclass(frozen=True)
    class DarkSizes:
        h1: float = 28.0
        h3: float = 20.0
        h5: float = 18.0
        body: float = 12.0

    light: LightSizes = field(default_factory=LightSizes)
    dark: DarkSizes = field(default_factory=DarkSizes)


# ── 尺寸常量（单位：英寸） ──────────────────────────────────────────

@dataclass(frozen=True)
class SlideSize:
    width: float = 13.333
    height: float = 7.5


@dataclass(frozen=True)
class Margins:
    title_left: float = 0.54     # 标题左距
    title_top: float = 0.47      # 标题顶距
    content_left: float = 0.76   # 内容左边界
    content_right: float = 12.33  # 内容右边界
    bottom_safe: float = 0.3     # 底部安全区


@dataclass(frozen=True)
class LogoSize:
    width: float = 1.34
    height: float = 0.49
    left: float = 11.56   # 右上角位置
    top: float = 0.32


@dataclass(frozen=True)
class CardSize:
    standard_width: float = 3.18
    standard_height: float = 2.90
    two_col_width: float = 5.57
    two_col_height: float = 2.39
    corner_radius: float = 0.1   # 圆角半径（约 9pt）


@dataclass(frozen=True)
class LayoutSizes:
    slide: SlideSize = field(default_factory=SlideSize)
    margins: Margins = field(default_factory=Margins)
    logo: LogoSize = field(default_factory=LogoSize)
    card: CardSize = field(default_factory=CardSize)


# ── 全局常量实例 ────────────────────────────────────────────────────

COLORS = ColorPalette()
TEXT_COLORS = TextColors()
BG_COLORS = BgColors()
BORDER_COLORS = BorderColors()
FONTS = FontSpec()
SIZES = LayoutSizes()


# ── 页面类型枚举 ────────────────────────────────────────────────────

PAGE_TYPES = [
    # 通用 - 浅色
    "cover-light",
    "toc-light",
    "section-light",
    "content-two-col-light",
    "content-three-cards-light",
    "timeline-three-cards-light",
    "data-chart-light",
    "timeline-vertical-light",
    "radial-structure-light",
    "phase-timeline-light",
    "team-cards-light",
    "closing-qrcode-light",
    "blank-light",
    "text-only-light",
    "list-light",
    "kpi-cards-light",
    "compare-two-col-light",
    "table-light",
    # 通用 - 深色
    "cover-dark",
    "toc-dark",
    "section-dark",
    "node-graph-dark",
    "phase-timeline-dark",
    "four-cards-dark",
    "list-image-dark",
    "honeycomb-dark",
    "pyramid-compare-dark",
    "closing-dark",
]
