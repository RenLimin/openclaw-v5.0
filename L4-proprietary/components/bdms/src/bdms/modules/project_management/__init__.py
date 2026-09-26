# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""BDMS 项目管理模块（Project Management Module）。

模块编码: project_management
层级: L4 BDMS 核心域
子引擎: ProjectEngine / CostEngine / RiskEngine / ChangeManagementEngine / AfterSalesEngine
编排层: ProjectManagementService / ProjectFinancialService
校验器: ProjectValidator
导出器: ProjectExporter / AfterSalesExporter
安全: RBAC（security.py / rbac_service.py）

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md。
"""
from .models import (
    ProjectStatus,
    ImplStatus,
    TicketState,
    TicketPriority,
    ServiceLevel,
    RiskStatus,
    RiskLevel,
    ChangeStatus,
    TimesheetStatus,
    VALID_TRANSITIONS,
    TICKET_VALID_TRANSITIONS,
    SLA_HOURS,
    RISK_LEVEL_MATRIX,
    DEFAULT_PHASES_V21,
    is_valid_transition,
    is_valid_ticket_transition,
    calculate_risk_level,
)
from .engine import ProjectEngine
from .service import ProjectManagementService
from .financial_service import ProjectFinancialService
from .cost import CostEngine
from .risk import RiskEngine
from .change import ChangeManagementEngine
from .after_sales import AfterSalesEngine

__all__ = [
    # 数据契约
    "ProjectStatus", "ImplStatus", "TicketState", "TicketPriority",
    "ServiceLevel", "RiskStatus", "RiskLevel", "ChangeStatus", "TimesheetStatus",
    "VALID_TRANSITIONS", "TICKET_VALID_TRANSITIONS", "SLA_HOURS",
    "RISK_LEVEL_MATRIX", "DEFAULT_PHASES_V21",
    "is_valid_transition", "is_valid_ticket_transition", "calculate_risk_level",
    # 引擎
    "ProjectEngine", "CostEngine", "RiskEngine",
    "ChangeManagementEngine", "AfterSalesEngine",
    # 服务
    "ProjectManagementService", "ProjectFinancialService",
]
