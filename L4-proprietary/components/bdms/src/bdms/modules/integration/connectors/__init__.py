"""Connectors package for data integration module.

All connectors auto-register via ConnectorRegistry.register.
Legacy adapters (oa_adapter.py / ones_adapter.py) are deprecated.
Use the unified Playwright browser_adapter.py instead.
"""
from .ones_connector import OnesConnector
from .oa_connector import OaConnector
from .timesheet_connector import TimesheetConnector
from .wecom_doc_connector import WecomDocConnector
from .local_import_connector import LocalImportConnector

__all__ = [
    "OnesConnector",
    "OaConnector",
    "TimesheetConnector",
    "WecomDocConnector",
    "LocalImportConnector",
]
