"""
OCR 数据模型定义

所有结果对象都是 dataclass，支持：
- to_dict() / from_dict() 序列化
- to_json() / from_json()  JSON 序列化
- 类型注解齐全
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional, Dict, Any


# ============================================================
# 基础类型
# ============================================================

BBox = Tuple[float, float, float, float]  # x1, y1, x2, y2


# ============================================================
# 行级结果
# ============================================================

@dataclass
class OCRLine:
    """单行 OCR 识别结果"""
    text: str
    bbox: BBox  # (x1, y1, x2, y2)
    confidence: float = 0.9
    source: str = "ocr"  # ocr / native / hybrid

    @property
    def x1(self) -> float: return self.bbox[0]
    @property
    def y1(self) -> float: return self.bbox[1]
    @property
    def x2(self) -> float: return self.bbox[2]
    @property
    def y2(self) -> float: return self.bbox[3]

    @property
    def width(self) -> float: return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float: return self.bbox[3] - self.bbox[1]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bbox"] = list(d["bbox"])
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OCRLine":
        return cls(
            text=d["text"],
            bbox=tuple(d["bbox"]),  # type: ignore
            confidence=d.get("confidence", 0.9),
            source=d.get("source", "ocr"),
        )


# ============================================================
# 质量评分
# ============================================================

@dataclass
class QualityScore:
    """OCR 结果质量综合评分（0-100）"""
    overall: float = 0.0          # 综合得分
    confidence: float = 0.0       # 平均置信度得分（0-100）
    clarity: float = 0.0          # 图像清晰度得分（0-100）
    text_density: float = 0.0     # 文本密度得分（0-100）
    layout_completeness: float = 0.0  # 布局完整性得分（0-100）
    details: Dict[str, Any] = field(default_factory=dict)  # 详细指标

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QualityScore":
        return cls(
            overall=d.get("overall", 0.0),
            confidence=d.get("confidence", 0.0),
            clarity=d.get("clarity", 0.0),
            text_density=d.get("text_density", 0.0),
            layout_completeness=d.get("layout_completeness", 0.0),
            details=d.get("details", {}),
        )

    @property
    def grade(self) -> str:
        """评级：A/B/C/D/F"""
        if self.overall >= 90: return "A"
        if self.overall >= 75: return "B"
        if self.overall >= 60: return "C"
        if self.overall >= 40: return "D"
        return "F"


# ============================================================
# 页级结果
# ============================================================

@dataclass
class OCRPage:
    """单页 OCR 结果"""
    page_num: int
    lines: List[OCRLine] = field(default_factory=list)
    width: int = 0
    height: int = 0
    is_scanned: bool = True       # 是否扫描件（原生提取失败时为 True）
    source: str = "ocr"          # ocr / native / hybrid
    quality: QualityScore = field(default_factory=QualityScore)

    @property
    def text(self) -> str:
        """纯文本（按阅读顺序拼接）"""
        return "\n".join(line.text for line in self.lines)

    @property
    def confidence(self) -> float:
        """平均置信度（0-1）"""
        if not self.lines:
            return 0.0
        return sum(l.confidence for l in self.lines) / len(self.lines)

    @property
    def total_chars(self) -> int:
        return sum(len(l.text) for l in self.lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_num": self.page_num,
            "lines": [l.to_dict() for l in self.lines],
            "width": self.width,
            "height": self.height,
            "is_scanned": self.is_scanned,
            "source": self.source,
            "quality": self.quality.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OCRPage":
        return cls(
            page_num=d["page_num"],
            lines=[OCRLine.from_dict(l) for l in d.get("lines", [])],
            width=d.get("width", 0),
            height=d.get("height", 0),
            is_scanned=d.get("is_scanned", True),
            source=d.get("source", "ocr"),
            quality=QualityScore.from_dict(d.get("quality", {})),
        )


# ============================================================
# 文档级结果
# ============================================================

@dataclass
class OCRResult:
    """OCR 完整结果（单图或多页文档）"""
    pages: List[OCRPage] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    # ---- 便捷属性 ----

    @property
    def text(self) -> str:
        """纯文本全文"""
        return "\n\n".join(
            f"{'='*50}\n第 {p.page_num} 页\n{'='*50}\n{p.text}"
            for p in self.pages
        ) if len(self.pages) > 1 else (self.pages[0].text if self.pages else "")

    @property
    def lines(self) -> List[OCRLine]:
        """所有行（扁平化）"""
        all_lines = []
        for p in self.pages:
            all_lines.extend(p.lines)
        return all_lines

    @property
    def confidence(self) -> float:
        """平均置信度（0-1）"""
        all_lines = self.lines
        if not all_lines:
            return 0.0
        return sum(l.confidence for l in all_lines) / len(all_lines)

    @property
    def quality_score(self) -> QualityScore:
        """综合质量评分（各页平均）"""
        if not self.pages:
            return QualityScore()
        avg_conf = sum(p.quality.confidence for p in self.pages) / len(self.pages)
        avg_clarity = sum(p.quality.clarity for p in self.pages) / len(self.pages)
        avg_density = sum(p.quality.text_density for p in self.pages) / len(self.pages)
        avg_layout = sum(p.quality.layout_completeness for p in self.pages) / len(self.pages)
        overall = 0.35 * avg_conf + 0.25 * avg_clarity + 0.20 * avg_density + 0.20 * avg_layout
        return QualityScore(
            overall=overall,
            confidence=avg_conf,
            clarity=avg_clarity,
            text_density=avg_density,
            layout_completeness=avg_layout,
        )

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_lines(self) -> int:
        return sum(len(p.lines) for p in self.pages)

    @property
    def total_chars(self) -> int:
        return sum(p.total_chars for p in self.pages)

    # ---- 导出 ----

    def to_text(self) -> str:
        """导出纯文本"""
        return self.text

    def to_markdown(self) -> str:
        """导出 Markdown 格式"""
        parts = ["# OCR 识别结果\n"]
        for page in self.pages:
            parts.append(f"\n## 第 {page.page_num} 页\n")
            parts.append(f"*置信度 {page.confidence:.2f} · {len(page.lines)} 行 · "
                        f"质量 {page.quality.grade}*\n")
            parts.append("```text\n")
            parts.append(page.text + "\n")
            parts.append("```\n")
        return "\n".join(parts)

    def to_json(self, indent: int = 2) -> str:
        """导出 JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pages": [p.to_dict() for p in self.pages],
            "meta": self.meta,
            "summary": {
                "total_pages": self.total_pages,
                "total_lines": self.total_lines,
                "total_chars": self.total_chars,
                "confidence": self.confidence,
                "quality": self.quality_score.to_dict(),
            },
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OCRResult":
        return cls(
            pages=[OCRPage.from_dict(p) for p in d.get("pages", [])],
            meta=d.get("meta", {}),
        )

    @classmethod
    def from_json(cls, s: str) -> "OCRResult":
        return cls.from_dict(json.loads(s))
