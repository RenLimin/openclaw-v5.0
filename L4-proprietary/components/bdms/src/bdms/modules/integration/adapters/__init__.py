"""Adapters package for data integration module.

统一浏览器适配器：BrowserAdapter（Playwright CDP + IAM Cookie 池）
旧适配器（ones_adapter / oa_adapter / timesheet_adapter）已 deprecated。
"""
from .browser_adapter import (
    BrowserAdapter,
    create_browser_adapter,
    browser_session,
    login_iam,
    ensure_logged_in,
    inject_cookies_to_context,
    IAM_BASE,
    ONES_BASE,
    OA_BASE,
    TIMESHEET_BASE,
)
from .wecom_api_adapter import WecomApiAdapter, WecomApiError

# 旧适配器（deprecated，保留导入以兼容现有代码）
from .ones_adapter import OnesAdapter
from .oa_adapter import OaAdapter
from .timesheet_adapter import TimesheetAdapter
from .pipeline import DeliveryReportPipeline, DataSourceError

__all__ = [
    "BrowserAdapter",
    "create_browser_adapter",
    "browser_session",
    "login_iam",
    "ensure_logged_in",
    "inject_cookies_to_context",
    "IAM_BASE",
    "ONES_BASE",
    "OA_BASE",
    "TIMESHEET_BASE",
    "DOWNLOADS_DIR",
    "WecomApiAdapter",
    "WecomApiError",
    # Deprecated
    "OnesAdapter",
    "OaAdapter",
    "TimesheetAdapter",
    "DeliveryReportPipeline",
    "DataSourceError",
]
