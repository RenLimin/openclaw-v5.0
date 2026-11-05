"""审查管线数据类。"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class LoadedFile:
    path: str
    fmt: str
    size: int


@dataclass
class DigitizedText:
    text: str
    parser_used: str
    parse_errors: List[str] = field(default_factory=list)
    quality: float = 1.0


@dataclass
class LineItem:
    raw_name: str
    model: Optional[str] = None
    price: Optional[float] = None
    source_line: str = ""


@dataclass
class ItemMatchResult:
    raw_name: str
    input_model: Optional[str]
    input_price: Optional[float]
    matched: bool
    score: float
    matched_product: Optional[str]
    matched_sku: Optional[str]
    standard_price: Optional[float]
    alert: Optional[str]
    satisfaction: str          # satisfied | partial | unsatisfied
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewReport:
    review_id: str
    loaded: LoadedFile
    digitized: DigitizedText
    clauses: List[Any] = field(default_factory=list)
    party_a: Dict[str, Any] = field(default_factory=dict)
    party_b: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    matches: List[ItemMatchResult] = field(default_factory=list)
    no_line_items: bool = False
    satisfaction: str = "partial"
    created_at: str = ""
    report_md_path: str = ""
    report_xlsx_path: str = ""
    repo_review_id: int = 0   # 主仓库 Repository 持久化后的整型 id
