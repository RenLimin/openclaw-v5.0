"""
PPT SDK — 基于 python-pptx 的统一封装。

与 Word/Excel 保持一致的接口规范：
- OfficeDocumentBase 隐式契约：__init__ / save / close / format / metadata / parse / to_markdown
- Create/Edit 能力：add_slide / add_text_box / add_table / add_chart / add_image / add_notes /
  set_slide_title / find_replace / duplicate_slide / delete_slide
- Parse 能力：parse / to_markdown / slide_count
- 中文支持：默认 Microsoft YaHei，同时设置 eastAsia 字体
"""

from __future__ import annotations

import copy
import os
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import CategoryChartData

from .exceptions import OfficeParseError, OfficeFormatError


# ── 常量 ────────────────────────────────────────────────────────────

DEFAULT_FONT = "Microsoft YaHei"

LAYOUT_MAP = {
    "blank": 6,           # 空白
    "title": 0,           # 标题幻灯片
    "title_content": 1,   # 标题和内容
    "two_content": 3,     # 两栏内容
    "section_header": 2,  # 节标题
}

CHART_TYPE_MAP = {
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE,
    "pie": XL_CHART_TYPE.PIE,
}

ALIGN_MAP = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}


# ── 辅助 ────────────────────────────────────────────────────────────

def _set_run_font(run, font_size: float = 18, bold: bool = False,
                   color: str | None = None, font_name: str = DEFAULT_FONT) -> None:
    """统一设置 run 的字体（含 eastAsia 中文字体）。"""
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color.lstrip("#"))
    # 同时设置 eastAsia 字体，保证中文显示正常
    from pptx.oxml.ns import qn
    rPr = run._r.get_or_add_rPr()
    eastAsia = rPr.find(qn('a:ea'))
    if eastAsia is None:
        from lxml import etree
        eastAsia = etree.SubElement(rPr, qn('a:ea'))
    eastAsia.set('typeface', font_name)


def _inches(val: float | int | None) -> Emu | None:
    if val is None:
        return None
    return Inches(val)


# ── SlideProxy ──────────────────────────────────────────────────────

class SlideProxy:
    """幻灯片代理，包装 python-pptx Slide 对象，方便链式操作。"""

    def __init__(self, slide, engine: "PPTDocument"):
        self._slide = slide
        self._engine = engine

    @property
    def raw(self):
        """返回原始 python-pptx Slide 对象。"""
        return self._slide


# ── PPTDocument ─────────────────────────────────────────────────────

class PPTDocument:
    """PPT 文档 — 基于 python-pptx 的统一 SDK。"""

    def __init__(self, path: str | None = None):
        """
        创建新 PPT 或打开已有 PPT。

        Args:
            path: 已有 pptx 文件路径；None 则创建空白文档。
        """
        self._path = path
        if path and os.path.exists(path):
            self._prs = Presentation(path)
        else:
            self._prs = Presentation()
        self._closed = False

    # ── 基础契约 ────────────────────────────────────────────────────

    @property
    def format(self) -> str:
        """文档格式标识。"""
        return "pptx"

    @property
    def metadata(self) -> dict:
        """核心属性（页数、尺寸等）。"""
        self._ensure_open()
        return {
            "slide_count": len(self._prs.slides),
            "width": self._prs.slide_width,
            "height": self._prs.slide_height,
            "path": self._path,
        }

    def save(self, path: str | None = None) -> str:
        """保存文档，返回最终路径。"""
        self._ensure_open()
        out = path or self._path
        if not out:
            raise ValueError("path is required for a new document")
        # 确保目录存在
        d = os.path.dirname(out)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        self._prs.save(out)
        self._path = out
        return out

    def close(self) -> None:
        """关闭文档（标记已关闭，释放引用）。"""
        self._closed = True
        self._prs = None  # type: ignore

    def _ensure_open(self) -> None:
        if self._closed:
            raise OfficeParseError("Document is already closed")

    # ── 查询 ────────────────────────────────────────────────────────

    def slide_count(self) -> int:
        """返回幻灯片页数。"""
        self._ensure_open()
        return len(self._prs.slides)

    # ── Create / Edit ───────────────────────────────────────────────

    def add_slide(self, layout: str = "blank") -> SlideProxy:
        """
        添加幻灯片。

        Args:
            layout: blank | title | title_content | two_content | section_header
        """
        self._ensure_open()
        if layout not in LAYOUT_MAP:
            raise OfficeFormatError(
                f"Unknown layout '{layout}'. Available: {list(LAYOUT_MAP.keys())}"
            )
        idx = LAYOUT_MAP[layout]
        # 防御：layout 索引可能超过实际可用数量
        slide_layouts = self._prs.slide_layouts
        if idx >= len(slide_layouts):
            # 回退到空白布局
            idx = min(6, len(slide_layouts) - 1)
        slide = self._prs.slides.add_slide(slide_layouts[idx])
        return SlideProxy(slide, self)

    def add_text_box(
        self,
        slide,
        x: float, y: float, w: float, h: float,
        text: str,
        font_size: float = 18,
        bold: bool = False,
        color: str | None = None,
        align: str | None = None,
    ):
        """
        添加文本框。坐标单位：英寸。

        Args:
            slide: SlideProxy 或原始 slide 对象
            x, y, w, h: 位置与尺寸（英寸）
            text: 文本内容，支持 \n 换行
            font_size: 字号（pt）
            bold: 是否粗体
            color: 十六进制颜色，如 "#FF0000"
            align: left | center | right | justify
        """
        self._ensure_open()
        s = slide._slide if isinstance(slide, SlideProxy) else slide
        txBox = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = txBox.text_frame
        tf.word_wrap = True

        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            if align and align in ALIGN_MAP:
                p.alignment = ALIGN_MAP[align]
            run = p.add_run()
            run.text = line
            _set_run_font(run, font_size=font_size, bold=bold, color=color)
        return txBox

    def add_table(
        self,
        slide,
        x: float, y: float, w: float, h: float,
        rows: int, cols: int,
        data: list[list] | None = None,
        header: bool = True,
    ):
        """
        添加表格。坐标单位：英寸。

        Args:
            slide: SlideProxy 或原始 slide 对象
            x, y, w, h: 位置与尺寸
            rows, cols: 行列数
            data: 二维数据列表
            header: 第一行是否作为表头（加粗 + 灰色背景）
        """
        self._ensure_open()
        s = slide._slide if isinstance(slide, SlideProxy) else slide
        table_shape = s.shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(h))
        table = table_shape.table

        if data:
            for r in range(min(rows, len(data))):
                row_data = data[r]
                for c in range(min(cols, len(row_data))):
                    cell = table.cell(r, c)
                    cell.text = ""
                    tf = cell.text_frame
                    p = tf.paragraphs[0]
                    run = p.add_run()
                    run.text = str(row_data[c])
                    is_header_row = header and r == 0
                    _set_run_font(
                        run,
                        font_size=14 if is_header_row else 12,
                        bold=is_header_row,
                    )
                    if is_header_row:
                        # 表头背景色
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = RGBColor(0xD9, 0xE2, 0xF3)
        return table_shape

    def add_chart(
        self,
        slide,
        x: float, y: float, w: float, h: float,
        chart_type: str,
        data: dict[str, list[float]],
        categories: list[str],
        title: str | None = None,
    ):
        """
        添加图表。

        Args:
            slide: SlideProxy 或原始 slide 对象
            x, y, w, h: 位置与尺寸（英寸）
            chart_type: column | bar | line | pie
            data: { series_name: [value, ...] }
            categories: 类别标签
            title: 图表标题
        """
        self._ensure_open()
        if chart_type not in CHART_TYPE_MAP:
            raise OfficeFormatError(
                f"Unknown chart_type '{chart_type}'. Available: {list(CHART_TYPE_MAP.keys())}"
            )
        s = slide._slide if isinstance(slide, SlideProxy) else slide

        chart_data = CategoryChartData()
        chart_data.categories = categories
        for name, values in data.items():
            chart_data.add_series(name, values)

        xl_type = CHART_TYPE_MAP[chart_type]
        chart_shape = s.shapes.add_chart(
            xl_type, Inches(x), Inches(y), Inches(w), Inches(h), chart_data
        )
        chart = chart_shape.chart
        if title:
            chart.has_title = True
            chart.chart_title.text_frame.text = title
            # 标题字体
            for p in chart.chart_title.text_frame.paragraphs:
                for run in p.runs:
                    _set_run_font(run, font_size=14, bold=True)
        return chart_shape

    def add_image(
        self,
        slide,
        path: str,
        x: float, y: float,
        w: float | None = None,
        h: float | None = None,
    ):
        """添加图片。坐标单位：英寸。"""
        self._ensure_open()
        s = slide._slide if isinstance(slide, SlideProxy) else slide
        if not os.path.exists(path):
            raise FileNotFoundError(f"Image not found: {path}")
        return s.shapes.add_picture(
            path, Inches(x), Inches(y),
            width=_inches(w), height=_inches(h),
        )

    def add_notes(self, slide, text: str) -> None:
        """添加幻灯片备注。"""
        self._ensure_open()
        s = slide._slide if isinstance(slide, SlideProxy) else slide
        notes_slide = s.notes_slide
        tf = notes_slide.notes_text_frame
        tf.text = text
        # 备注字体
        for p in tf.paragraphs:
            for run in p.runs:
                _set_run_font(run, font_size=12)

    def set_slide_title(self, slide, text: str) -> None:
        """设置幻灯片标题（查找 title 占位符或第一个文本框）。"""
        self._ensure_open()
        s = slide._slide if isinstance(slide, SlideProxy) else slide
        # 优先用占位符 title
        if s.shapes.title is not None:
            tf = s.shapes.title.text_frame
            tf.text = text
            for p in tf.paragraphs:
                for run in p.runs:
                    _set_run_font(run, font_size=32, bold=True)
            return
        # 退而求其次：找第一个文本框
        for shape in s.shapes:
            if shape.has_text_frame:
                tf = shape.text_frame
                tf.text = text
                for p in tf.paragraphs:
                    for run in p.runs:
                        _set_run_font(run, font_size=32, bold=True)
                return

    def find_replace(self, find_text: str, replace_text: str) -> int:
        """
        全局查找替换（所有幻灯片的所有文本框 + 备注）。
        返回替换次数。
        """
        self._ensure_open()
        count = 0
        for slide in self._prs.slides:
            # 幻灯片主体
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            if find_text in run.text:
                                run.text = run.text.replace(find_text, replace_text)
                                count += 1
                # 表格内文本
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            for para in cell.text_frame.paragraphs:
                                for run in para.runs:
                                    if find_text in run.text:
                                        run.text = run.text.replace(find_text, replace_text)
                                        count += 1
            # 备注
            if slide.has_notes_slide:
                tf = slide.notes_slide.notes_text_frame
                for para in tf.paragraphs:
                    for run in para.runs:
                        if find_text in run.text:
                            run.text = run.text.replace(find_text, replace_text)
                            count += 1
        return count

    def duplicate_slide(self, slide_index: int) -> SlideProxy:
        """
        复制指定索引的幻灯片，追加到末尾。
        基于 python-pptx 的 XML 复制方案。
        """
        self._ensure_open()
        slides = self._prs.slides
        if slide_index < 0 or slide_index >= len(slides):
            raise IndexError(f"slide_index {slide_index} out of range (0-{len(slides)-1})")

        source = slides[slide_index]
        # 使用空白布局添加新 slide
        blank_layout = self._prs.slide_layouts[LAYOUT_MAP["blank"]]
        new_slide = slides.add_slide(blank_layout)

        # 删除新 slide 的所有占位符
        for shape in list(new_slide.shapes):
            sp = shape._element
            sp.getparent().remove(sp)

        # 复制所有 shape
        for shape in source.shapes:
            new_el = copy.deepcopy(shape._element)
            new_slide.shapes._spTree.insert_element_before(new_el, 'p:extLst')

        # 复制备注
        if source.has_notes_slide:
            notes_text = source.notes_slide.notes_text_frame.text
            if notes_text.strip():
                new_slide.notes_slide.notes_text_frame.text = notes_text

        return SlideProxy(new_slide, self)

    def delete_slide(self, slide_index: int) -> None:
        """删除指定索引的幻灯片。"""
        self._ensure_open()
        slides = self._prs.slides
        if slide_index < 0 or slide_index >= len(slides):
            raise IndexError(f"slide_index {slide_index} out of range (0-{len(slides)-1})")

        # python-pptx 没有直接 delete，需要操作 XML
        xml_slides = slides._sldIdLst
        slides_list = list(xml_slides)
        xml_slides.remove(slides_list[slide_index])

    # ── Parse ───────────────────────────────────────────────────────

    def parse(self) -> dict:
        """
        解析整份 PPT，返回结构化数据。

        返回结构：
        {
            "slide_count": int,
            "slides": [
                {
                    "index": int,
                    "title": str | None,
                    "text_boxes": [{"text": str, "left": int, "top": int, "width": int, "height": int}],
                    "tables": [{"rows": int, "cols": int, "data": [[...]]}],
                    "images": [{"left": int, "top": int, "width": int, "height": int}],
                    "charts": [{"chart_type": str, "title": str | None}],
                    "notes": str | None,
                },
                ...
            ]
        }
        """
        self._ensure_open()
        result: dict[str, Any] = {
            "slide_count": len(self._prs.slides),
            "slides": [],
        }

        for idx, slide in enumerate(self._prs.slides):
            slide_data: dict[str, Any] = {
                "index": idx,
                "title": None,
                "text_boxes": [],
                "tables": [],
                "images": [],
                "charts": [],
                "notes": None,
            }

            # 标题
            if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
                slide_data["title"] = slide.shapes.title.text_frame.text.strip()

            for shape in slide.shapes:
                # 文本框（排除占位符标题，避免重复）
                if shape.has_text_frame and not shape.has_table and not self._is_placeholder_title(shape, slide):
                    text = shape.text_frame.text
                    slide_data["text_boxes"].append({
                        "text": text,
                        "left": shape.left,
                        "top": shape.top,
                        "width": shape.width,
                        "height": shape.height,
                    })

                # 表格
                if shape.has_table:
                    table = shape.table
                    rows = len(table.rows)
                    cols = len(table.columns)
                    data = []
                    for r in range(rows):
                        row_data = []
                        for c in range(cols):
                            row_data.append(table.cell(r, c).text)
                        data.append(row_data)
                    slide_data["tables"].append({
                        "rows": rows,
                        "cols": cols,
                        "data": data,
                    })

                # 图片
                if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
                    slide_data["images"].append({
                        "left": shape.left,
                        "top": shape.top,
                        "width": shape.width,
                        "height": shape.height,
                    })

                # 图表
                if shape.has_chart:
                    chart = shape.chart
                    chart_type = str(chart.chart_type) if chart.chart_type else "unknown"
                    chart_title = None
                    if chart.has_title:
                        chart_title = chart.chart_title.text_frame.text
                    slide_data["charts"].append({
                        "chart_type": chart_type,
                        "title": chart_title,
                    })

            # 备注
            if slide.has_notes_slide:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()
                if notes_text:
                    slide_data["notes"] = notes_text

            result["slides"].append(slide_data)

        return result

    @staticmethod
    def _is_placeholder_title(shape, slide) -> bool:
        """判断 shape 是否为幻灯片的标题占位符。"""
        if slide.shapes.title is shape:
            return True
        return False

    def to_markdown(self) -> str:
        """
        转 Markdown 大纲。
        每页一个 ## 标题 + 内容列表（文本框/表格/备注）。
        """
        self._ensure_open()
        parsed = self.parse()
        lines: list[str] = []

        for slide in parsed["slides"]:
            title = slide["title"] or f"Slide {slide['index'] + 1}"
            lines.append(f"## {title}")
            lines.append("")

            # 文本框内容
            for tb in slide["text_boxes"]:
                text = tb["text"].strip()
                if text:
                    # 多行文本逐行加 bullet
                    for line in text.split("\n"):
                        line = line.strip()
                        if line:
                            lines.append(f"- {line}")

            # 表格
            for t in slide["tables"]:
                lines.append("")
                data = t["data"]
                if data:
                    # 表头
                    header = data[0]
                    lines.append("| " + " | ".join(str(c) for c in header) + " |")
                    lines.append("| " + " | ".join("---" for _ in header) + " |")
                    for row in data[1:]:
                        lines.append("| " + " | ".join(str(c) for c in row) + " |")
                lines.append("")

            # 备注
            if slide["notes"]:
                lines.append("")
                lines.append(f"> **备注**: {slide['notes']}")

            lines.append("")

        return "\n".join(lines).rstrip() + "\n"
