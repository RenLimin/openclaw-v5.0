"""revenue_analysis — 确收分析报告（Revenue Analysis）模块。

链路：importer → validator → engine → builders → exporter → service/CLI。
以 DESIGN-DETAIL-REVENUE-ANALYSIS-v1.0 为实施基线；202609 实测表头为准。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。
"""

from .config import (
    ALL_SHEETS, SHEET_BUDGET, SHEET_DRAFT, SHEET_TREND,
    CATEGORIES, FILL_STATUS, TREND_STATUS, TREND_CATEGORY_MAP,
)
from .importer import RevenueAnalysisImporter
from .validator import RevenueAnalysisValidator
from .caliber_builder import CaliberBuilder
from .trend_builder import TrendBuilder
from .engine import RevenueAnalysisEngine
from .service import RevenueAnalysisService
from .exporter import RevenueAnalysisExporter

__all__ = [
    "ALL_SHEETS", "SHEET_BUDGET", "SHEET_DRAFT", "SHEET_TREND",
    "CATEGORIES", "FILL_STATUS", "TREND_STATUS", "TREND_CATEGORY_MAP",
    "RevenueAnalysisImporter", "RevenueAnalysisValidator",
    "CaliberBuilder", "TrendBuilder",
    "RevenueAnalysisEngine", "RevenueAnalysisService",
    "RevenueAnalysisExporter",
]
