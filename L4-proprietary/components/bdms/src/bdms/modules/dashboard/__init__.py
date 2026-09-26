# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""BDMS 驾驶舱模块（Dashboard）。

模块编码: dashboard
层级: L4 BDMS 展示层
引擎: DashboardEngine（KPI 计算）
服务: DashboardService（默认视图 + 下钻 + 快照）
     DashboardCustomizationService（多看板视图管理）
     DashboardEditService（明细编辑 + 权限 + 历史 + 撤销）
     DashboardDataSourceService（数据源注册 + SQL 辅助）
连接器: DeliveryReportConnector（交付月报统计聚合）

对齐 DESIGN-DETAIL-DASHBOARD-v2.1.md。
"""

from .engine import DashboardEngine
from .service import DashboardService
from .customization_service import DashboardCustomizationService
from .edit_service import DashboardEditService
from .data_source_service import (
    DashboardDataSourceService, SqlValidationError,
)
from .delivery_report_connector import DeliveryReportConnector

__all__ = [
    "DashboardEngine",
    "DashboardService",
    "DashboardCustomizationService",
    "DashboardEditService",
    "DashboardDataSourceService",
    "SqlValidationError",
    "DeliveryReportConnector",
]
