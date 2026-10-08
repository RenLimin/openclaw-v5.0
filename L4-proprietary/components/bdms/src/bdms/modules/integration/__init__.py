# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""BDMS 数据集成模块（Integration）。

模块编码: integration
层级: L4 BDMS 横切模块
框架: BaseConnector + ConnectorRegistry（插件机制）
连接器: ones / oa / timesheet / wecom_doc / local_import
服务: IntegrationService（编排 + 暂存 + 频率 + 重试 + 死信）

对齐 DESIGN-DETAIL-INTEGRATION-v2.1.md。
"""
from .base import BaseConnector, ConnectorRegistry, SyncResult
from .service import IntegrationService
from .scheduler import SyncScheduler
from .error_handler import RetryHandler, DeadLetterQueue, AlertManager
from .connectors import (
    LocalImportConnector, OnesConnector, OaConnector, TimesheetConnector, WecomDocConnector,
)

__all__ = [
    "BaseConnector", "ConnectorRegistry", "SyncResult",
    "IntegrationService", "SyncScheduler",
    "RetryHandler", "DeadLetterQueue", "AlertManager",
    "LocalImportConnector", "OnesConnector", "OaConnector",
    "TimesheetConnector", "WecomDocConnector",
]
