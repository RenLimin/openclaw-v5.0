"""
DSL Schema — PPT 模板 YAML 文件的数据模型。
使用 Pydantic v2 进行校验。

模板 YAML 结构：
```yaml
meta:
  name: 模板名称
  page_type: cover-light    # 页面类型标识
  theme: light              # light / dark
  description: 模板描述
  version: "1.0.0"

layout:
  # 布局配置（不同 page_type 有不同字段）
  title: "主标题"
  subtitle: "英文副标题"
  ...

data:
  # 示例数据（用于预览和测试）
  title: "示例标题"
  ...
```
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ── Meta ────────────────────────────────────────────────────────────

class TemplateMeta(BaseModel):
    """模板元数据。"""
    name: str = Field(..., min_length=1, description="模板名称")
    page_type: str = Field(..., min_length=1, description="页面类型标识")
    theme: str = Field("light", pattern="^(light|dark)$", description="主题：light / dark")
    description: str = ""
    version: str = "1.0.0"
    author: str = "Bangcle PPT System"
    category: str = "general"


# ── 通用布局字段 ────────────────────────────────────────────────────

class BaseLayout(BaseModel):
    """所有页面共享的布局字段。"""
    title: str = ""
    subtitle: str = ""  # 英文副标题

    class Config:
        extra = "allow"  # 允许额外字段（各页面类型自己扩展）


# ── 封面页布局 ──────────────────────────────────────────────────────

class CoverLayout(BaseLayout):
    """封面页布局。"""
    presenter: str = ""          # 汇报人
    company: str = ""            # 公司名
    date: str = ""               # 日期
    slogan: str = ""             # Slogan
    show_logo: bool = True


# ── 目录页布局 ──────────────────────────────────────────────────────

class TocItem(BaseModel):
    """目录项。"""
    number: str = "01"
    title: str = ""
    subtitle: str = ""  # 英文
    part: str = ""      # Part One 等


class TocLayout(BaseLayout):
    """目录页布局。"""
    items: list[TocItem] = Field(default_factory=list)


# ── 章节过渡页布局 ──────────────────────────────────────────────────

class SectionLayout(BaseLayout):
    """章节过渡页布局。"""
    part_label: str = "Part One"
    chapter_number: str = "01"
    show_silhouette: bool = True
    show_logo: bool = True


# ── 图文混排页布局 ──────────────────────────────────────────────────

class ContentItem(BaseModel):
    """要点项。"""
    icon: str = "●"
    title: str = ""
    description: str = ""


class TextImageLayout(BaseLayout):
    """左文右图（图文混排）布局。"""
    highlights: list[ContentItem] = Field(default_factory=list, max_length=4)
    card_title: str = ""
    card_body: str = ""
    image_path: str = ""
    image_position: str = Field("right", pattern="^(left|right)$")


# ── 三卡片布局 ──────────────────────────────────────────────────────

class CardItem(BaseModel):
    """卡片项。"""
    number: str = "01"
    title: str = ""
    body: str = ""
    icon: str = ""


class ThreeCardsLayout(BaseLayout):
    """三卡片 + 横幅图布局。"""
    banner_image: str = ""
    cards: list[CardItem] = Field(default_factory=list, max_length=3)


# ── 时间轴+三卡片布局 ───────────────────────────────────────────────

class TimelineCardItem(BaseModel):
    """时间轴卡片项。"""
    step: str = "01"
    title: str = ""
    body: str = ""
    icon: str = ""


class TimelineThreeCardsLayout(BaseLayout):
    """横向时间轴 + 三卡片。"""
    items: list[TimelineCardItem] = Field(default_factory=list, max_length=3)


# ── 数据图表页布局 ──────────────────────────────────────────────────

class KpiItem(BaseModel):
    """KPI 指标。"""
    value: str = "0"
    label: str = ""
    suffix: str = ""


class DataChartLayout(BaseLayout):
    """数据 + 图表页。"""
    kpis: list[KpiItem] = Field(default_factory=list, max_length=4)
    chart_type: str = Field("column", pattern="^(column|bar|line|pie)$")
    chart_title: str = ""
    chart_categories: list[str] = Field(default_factory=list)
    chart_data: dict[str, list[float]] = Field(default_factory=dict)
    right_title: str = ""
    right_body: str = ""


# ── 纵向时间轴布局 ──────────────────────────────────────────────────

class VTimelineItem(BaseModel):
    """纵向时间轴节点。"""
    date: str = ""
    title: str = ""
    body: str = ""


class VTimelineLayout(BaseLayout):
    """纵向时间轴布局。"""
    items: list[VTimelineItem] = Field(default_factory=list, max_length=5)
    image_path: str = ""


# ── 放射结构布局 ────────────────────────────────────────────────────

class RadialNode(BaseModel):
    """放射节点。"""
    label: str = ""
    icon: str = ""


class RadialLayout(BaseLayout):
    """放射结构图。"""
    center_title: str = ""
    center_subtitle: str = ""
    nodes: list[RadialNode] = Field(default_factory=list, max_length=6)


# ── 阶段时间轴布局 ──────────────────────────────────────────────────

class PhaseItem(BaseModel):
    """阶段节点。"""
    phase: str = ""
    title: str = ""
    body: str = ""


class PhaseTimelineLayout(BaseLayout):
    """6阶段时间轴（上下交错）。"""
    items: list[PhaseItem] = Field(default_factory=list, max_length=6)


# ── 团队卡片布局 ────────────────────────────────────────────────────

class TeamMember(BaseModel):
    """团队成员。"""
    name: str = ""
    role: str = ""
    avatar: str = ""
    description: str = ""


class TeamLayout(BaseLayout):
    """团队介绍页。"""
    members: list[TeamMember] = Field(default_factory=list, max_length=4)


# ── 对比页布局 ──────────────────────────────────────────────────────

class CompareColumn(BaseModel):
    """对比栏。"""
    title: str = ""
    items: list[str] = Field(default_factory=list)
    highlight: bool = False


class CompareLayout(BaseLayout):
    """两栏/三栏对比页。"""
    columns: list[CompareColumn] = Field(default_factory=list, max_length=3)


# ── 列表页布局 ──────────────────────────────────────────────────────

class ListLayout(BaseLayout):
    """列表页（要点列表）。"""
    items: list[str] = Field(default_factory=list)
    numbered: bool = False
    icon: str = "●"


# ── 纯文本/引文页布局 ───────────────────────────────────────────────

class TextOnlyLayout(BaseLayout):
    """纯文本页/引文页。"""
    body: str = ""
    is_quote: bool = False
    author: str = ""


# ── KPI 卡片页布局 ──────────────────────────────────────────────────

class KpiCardsLayout(BaseLayout):
    """KPI 数据卡片页。"""
    cards: list[KpiItem] = Field(default_factory=list, max_length=4)


# ── 表格页布局 ──────────────────────────────────────────────────────

class TableLayout(BaseLayout):
    """数据表格页。"""
    table_data: list[list[str]] = Field(default_factory=list)
    has_header: bool = True


# ── 流程图布局 ──────────────────────────────────────────────────────

class FlowStep(BaseModel):
    """流程步骤。"""
    step: str = ""
    title: str = ""
    body: str = ""


class FlowLayout(BaseLayout):
    """流程图页。"""
    steps: list[FlowStep] = Field(default_factory=list, max_length=5)


# ── 结束页布局 ──────────────────────────────────────────────────────

class ClosingLayout(BaseLayout):
    """结束/感谢页。"""
    main_text: str = "谢谢观看"
    subtitle: str = "THANK YOU"
    qr_code: str = ""
    contact: str = ""
    slogan: str = ""


# ── 空白页布局 ──────────────────────────────────────────────────────

class BlankLayout(BaseLayout):
    """空白模板页。"""
    show_left_bar: bool = True


# ── 节点关系图布局（深色特有） ────────────────────────────────────────

class NodeGraphLayout(BaseLayout):
    """节点关系图。"""
    nodes: list[RadialNode] = Field(default_factory=list, max_length=4)
    center_text: str = ""


# ── 蜂巢布局（深色特有） ─────────────────────────────────────────────

class HoneycombLayout(BaseLayout):
    """蜂巢/六边形布局。"""
    center_title: str = ""
    nodes: list[RadialNode] = Field(default_factory=list, max_length=6)


# ── 金字塔对比布局（深色特有） ────────────────────────────────────────

class PyramidCompareLayout(BaseLayout):
    """金字塔 + 对比卡片。"""
    pyramid_levels: list[str] = Field(default_factory=list, max_length=4)
    compare_title: str = ""
    compare_items: list[str] = Field(default_factory=list)


# ── 四卡片布局（深色特有） ────────────────────────────────────────────

class FourCardsLayout(BaseLayout):
    """四卡片图文（深色）。"""
    cards: list[CardItem] = Field(default_factory=list, max_length=4)
    chart_placeholder: bool = True


# ── 左图右列表布局（深色特有） ─────────────────────────────────────────

class ListImageLayout(BaseLayout):
    """左图 + 右列表项（深色）。"""
    image_path: str = ""
    items: list[str] = Field(default_factory=list)


# ── 页面类型 → Layout 类映射 ─────────────────────────────────────────

PAGE_LAYOUT_MAP: dict[str, type[BaseModel]] = {
    # 通用（浅色为主）
    "cover-light": CoverLayout,
    "cover-dark": CoverLayout,
    "toc-light": TocLayout,
    "toc-dark": TocLayout,
    "section-light": SectionLayout,
    "section-dark": SectionLayout,
    "content-two-col-light": TextImageLayout,
    "content-three-cards-light": ThreeCardsLayout,
    "timeline-three-cards-light": TimelineThreeCardsLayout,
    "data-chart-light": DataChartLayout,
    "timeline-vertical-light": VTimelineLayout,
    "radial-structure-light": RadialLayout,
    "phase-timeline-light": PhaseTimelineLayout,
    "phase-timeline-dark": PhaseTimelineLayout,
    "team-cards-light": TeamLayout,
    "compare-two-col-light": CompareLayout,
    "list-light": ListLayout,
    "text-only-light": TextOnlyLayout,
    "kpi-cards-light": KpiCardsLayout,
    "table-light": TableLayout,
    "flow-light": FlowLayout,
    "closing-light": ClosingLayout,
    "closing-dark": ClosingLayout,
    "blank-light": BlankLayout,
    # 深色特有
    "node-graph-dark": NodeGraphLayout,
    "four-cards-dark": FourCardsLayout,
    "list-image-dark": ListImageLayout,
    "honeycomb-dark": HoneycombLayout,
    "pyramid-compare-dark": PyramidCompareLayout,
}


# ── 顶层模板模型 ────────────────────────────────────────────────────

class SlideTemplate(BaseModel):
    """
    单页模板 DSL 模型。
    """
    meta: TemplateMeta
    layout: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("layout")
    @classmethod
    def validate_layout_by_type(cls, v: dict[str, Any], info) -> dict[str, Any]:
        """根据 meta.page_type 校验 layout 字段。"""
        # 注意：这里需要访问 meta，但 validator 先于完整模型校验
        # 所以 layout 的精确校验在 validate_layout_by_page_type 中做
        return v

    def validate_layout_against_type(self) -> BaseModel:
        """
        根据 meta.page_type 对 layout 做精确校验，返回对应 Layout 模型实例。
        """
        page_type = self.meta.page_type
        layout_cls = PAGE_LAYOUT_MAP.get(page_type)
        if layout_cls is None:
            raise ValueError(f"Unknown page_type: {page_type}")
        return layout_cls(**self.layout)


# ── 多页 PPT 组合模型 ───────────────────────────────────────────────

class PresentationSpec(BaseModel):
    """
    完整 PPT 规格（多页组合）。
    """
    title: str = "Bangcle PPT"
    theme: str = Field("light", pattern="^(light|dark)$")
    slides: list[SlideTemplate] = Field(default_factory=list)

    def validate_all(self) -> list[BaseModel]:
        """校验所有幻灯片的 layout，返回 layout 模型列表。"""
        return [s.validate_layout_against_type() for s in self.slides]
