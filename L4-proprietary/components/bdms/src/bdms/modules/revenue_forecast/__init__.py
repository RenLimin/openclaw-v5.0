"""revenue_forecast — 实时动态确认收入预估（Phase 1+2 纯内核）。

双口径（Bangcle 专属，见 DESIGN-DETAIL-REVENUE-FORECAST-v1.0）：
  - 锁定口径 Locked：预算执行表 col27=Σcol15..26（已提交公司，本年不可调）
  - 动态口径 Dynamic：底稿 col2「交付预计完成时间」按十类分类，金额取 col42

本包仅含纯内核：
  - classifier:    底稿 col2 十类分类（关键词/年份为配置常量）
  - report_parser: Excel 两 Sheet → ObligationRow，含恒等式校验
  - engine:        双口径纯计算（不读文件/DB、不取系统时间、无随机）
"""

from .classifier import (
    DUE_2026, FUTURE_YEAR, IN_PIPELINE, ALREADY_DONE, EXCEPTION,
    TERMINATED, ADJUSTED, NOT_STARTED, ZERO_AMOUNT, MISSING_DATE,
    CATEGORIES, classify_due, parse_due_date,
)
from .report_parser import (
    ObligationRow, ParseReport, ValidationIssue, parse_report,
)
from .engine import ForecastResult, forecast

__all__ = [
    "DUE_2026", "FUTURE_YEAR", "IN_PIPELINE", "ALREADY_DONE", "EXCEPTION",
    "TERMINATED", "ADJUSTED", "NOT_STARTED", "ZERO_AMOUNT", "MISSING_DATE",
    "CATEGORIES", "classify_due", "parse_due_date",
    "ObligationRow", "ParseReport", "ValidationIssue", "parse_report",
    "ForecastResult", "forecast",
]
