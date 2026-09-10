"""
Bangcle PPT 模板系统 — L4 专有业务层组件 (CPT-012)

基于梆梆安全官方 VI 规范的 PPT 模板生成系统。
"""

from .theme import Theme, ThemeVariant, get_theme, COLORS, FONTS, SIZES
from .dsl import SlideTemplate, PresentationSpec
from .engine import TemplateEngine
from .renderers import REGISTRY, get_renderer_class, register_renderer
from .base import RendererBase

__version__ = "1.0.0"
__component_id__ = "CPT-012"

__all__ = [
    "Theme", "ThemeVariant", "get_theme",
    "COLORS", "FONTS", "SIZES",
    "SlideTemplate", "PresentationSpec",
    "TemplateEngine",
    "REGISTRY", "get_renderer_class", "register_renderer",
    "RendererBase",
]
