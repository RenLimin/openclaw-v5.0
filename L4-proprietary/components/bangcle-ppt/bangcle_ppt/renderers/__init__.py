"""
页面渲染器注册中心。

新增页面类型：
1. 创建新的 Renderer 类（继承 RendererBase）
2. 在 REGISTRY 中注册：page_type -> RendererClass
"""

from .cover_renderer import CoverLightRenderer, CoverDarkRenderer
from .toc_renderer import TocLightRenderer, TocDarkRenderer
from .section_renderer import SectionLightRenderer, SectionDarkRenderer
from .content_renderer import (
    ContentTwoColLightRenderer,
    ThreeCardsLightRenderer,
    TimelineThreeCardsLightRenderer,
    DataChartLightRenderer,
    ListLightRenderer,
    TextOnlyLightRenderer,
    KpiCardsLightRenderer,
)
from .advanced_renderers import (
    VTimelineLightRenderer,
    RadialStructureLightRenderer,
    PhaseTimelineLightRenderer,
    TeamCardsLightRenderer,
    CompareTwoColLightRenderer,
    TableLightRenderer,
    FlowLightRenderer,
    ClosingLightRenderer,
    BlankLightRenderer,
    # 深色特有
    NodeGraphDarkRenderer,
    FourCardsDarkRenderer,
    ListImageDarkRenderer,
    HoneycombDarkRenderer,
    PyramidCompareDarkRenderer,
    ClosingDarkRenderer,
)

# 页面类型 → Renderer 类 映射
REGISTRY: dict[str, type] = {
    # ── 封面 ──
    "cover-light": CoverLightRenderer,
    "cover-dark": CoverDarkRenderer,
    # ── 目录 ──
    "toc-light": TocLightRenderer,
    "toc-dark": TocDarkRenderer,
    # ── 章节过渡 ──
    "section-light": SectionLightRenderer,
    "section-dark": SectionDarkRenderer,
    # ── 内容页（浅色） ──
    "content-two-col-light": ContentTwoColLightRenderer,
    "content-three-cards-light": ThreeCardsLightRenderer,
    "timeline-three-cards-light": TimelineThreeCardsLightRenderer,
    "data-chart-light": DataChartLightRenderer,
    "list-light": ListLightRenderer,
    "text-only-light": TextOnlyLightRenderer,
    "kpi-cards-light": KpiCardsLightRenderer,
    "timeline-vertical-light": VTimelineLightRenderer,
    "radial-structure-light": RadialStructureLightRenderer,
    "phase-timeline-light": PhaseTimelineLightRenderer,
    "team-cards-light": TeamCardsLightRenderer,
    "compare-two-col-light": CompareTwoColLightRenderer,
    "table-light": TableLightRenderer,
    "flow-light": FlowLightRenderer,
    "closing-light": ClosingLightRenderer,
    "blank-light": BlankLightRenderer,
    # ── 深色特有 ──
    "node-graph-dark": NodeGraphDarkRenderer,
    "four-cards-dark": FourCardsDarkRenderer,
    "list-image-dark": ListImageDarkRenderer,
    "honeycomb-dark": HoneycombDarkRenderer,
    "pyramid-compare-dark": PyramidCompareDarkRenderer,
    "closing-dark": ClosingDarkRenderer,
    # 共用（深色）
    "phase-timeline-dark": PhaseTimelineLightRenderer,  # 深色用同一款
}


def get_renderer_class(page_type: str) -> type:
    """获取指定页面类型的渲染器类。"""
    if page_type not in REGISTRY:
        raise ValueError(
            f"Unknown page type: {page_type}. "
            f"Available: {list(REGISTRY.keys())}"
        )
    return REGISTRY[page_type]


def register_renderer(page_type: str, renderer_cls: type) -> None:
    """注册一个新的渲染器。"""
    REGISTRY[page_type] = renderer_cls


__all__ = [
    "REGISTRY", "get_renderer_class", "register_renderer",
    # Cover
    "CoverLightRenderer", "CoverDarkRenderer",
    # TOC
    "TocLightRenderer", "TocDarkRenderer",
    # Section
    "SectionLightRenderer", "SectionDarkRenderer",
    # Content
    "ContentTwoColLightRenderer", "ThreeCardsLightRenderer",
    "TimelineThreeCardsLightRenderer", "DataChartLightRenderer",
    "ListLightRenderer", "TextOnlyLightRenderer", "KpiCardsLightRenderer",
    # Advanced
    "VTimelineLightRenderer", "RadialStructureLightRenderer",
    "PhaseTimelineLightRenderer", "TeamCardsLightRenderer",
    "CompareTwoColLightRenderer", "TableLightRenderer",
    "FlowLightRenderer", "ClosingLightRenderer", "BlankLightRenderer",
    # Dark
    "NodeGraphDarkRenderer", "FourCardsDarkRenderer",
    "ListImageDarkRenderer", "HoneycombDarkRenderer",
    "PyramidCompareDarkRenderer", "ClosingDarkRenderer",
]
