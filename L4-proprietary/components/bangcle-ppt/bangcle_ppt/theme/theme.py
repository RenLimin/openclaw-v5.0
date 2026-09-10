"""
主题系统 — 浅色/深色主题切换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .design_constants import (
    COLORS, TEXT_COLORS, BG_COLORS, BORDER_COLORS, FONTS, SIZES,
)


class ThemeVariant(str, Enum):
    LIGHT = "light"
    DARK = "dark"


@dataclass
class Theme:
    """
    主题配置 — 根据 variant 提供对应的颜色、字体、尺寸。
    """
    variant: ThemeVariant = ThemeVariant.LIGHT

    # ── 背景色 ────────────────────────────────────────────────────
    @property
    def bg_color(self) -> str:
        return BG_COLORS.light if self.variant == ThemeVariant.LIGHT else BG_COLORS.dark

    # ── 文字色 ────────────────────────────────────────────────────
    @property
    def title_color(self) -> str:
        return TEXT_COLORS.light_title if self.variant == ThemeVariant.LIGHT else TEXT_COLORS.dark_title

    @property
    def subtitle_color(self) -> str:
        return TEXT_COLORS.light_subtitle if self.variant == ThemeVariant.LIGHT else TEXT_COLORS.dark_subtitle

    @property
    def body_color(self) -> str:
        return TEXT_COLORS.light_body if self.variant == ThemeVariant.LIGHT else TEXT_COLORS.dark_body

    @property
    def caption_color(self) -> str:
        return TEXT_COLORS.light_caption if self.variant == ThemeVariant.LIGHT else TEXT_COLORS.dark_caption

    @property
    def accent_color(self) -> str:
        return TEXT_COLORS.light_accent if self.variant == ThemeVariant.LIGHT else TEXT_COLORS.dark_accent

    # ── 主色 / 装饰色 ──────────────────────────────────────────────
    @property
    def primary(self) -> str:
        return COLORS.primary

    @property
    def gold(self) -> str:
        return COLORS.gold

    # ── 分割线 / 边框 ──────────────────────────────────────────────
    @property
    def divider_color(self) -> str:
        return COLORS.light_gray if self.variant == ThemeVariant.LIGHT else COLORS.medium_gray

    @property
    def card_border_color(self) -> str:
        return BORDER_COLORS.light_card if self.variant == ThemeVariant.LIGHT else BORDER_COLORS.dark_card

    @property
    def card_bg_color(self) -> str:
        return COLORS.white if self.variant == ThemeVariant.LIGHT else COLORS.primary

    # ── 字体 ──────────────────────────────────────────────────────
    @property
    def font_family(self) -> str:
        return FONTS.family

    @property
    def font_fallback(self) -> str:
        return FONTS.fallback

    # ── 字号（按主题取对应层级） ────────────────────────────────────
    @property
    def font_size(self):
        """返回对应主题的字号表。"""
        return FONTS.light if self.variant == ThemeVariant.LIGHT else FONTS.dark

    @property
    def sizes(self):
        """布局尺寸常量。"""
        return SIZES

    # ── 工具方法 ──────────────────────────────────────────────────
    def hex_to_tuple(self, hex_color: str) -> tuple[int, int, int]:
        """将十六进制颜色转 RGB 元组。"""
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))  # type: ignore


def get_theme(variant: str | ThemeVariant = "light") -> Theme:
    """获取主题实例。"""
    if isinstance(variant, str):
        variant = ThemeVariant(variant)
    return Theme(variant=variant)
