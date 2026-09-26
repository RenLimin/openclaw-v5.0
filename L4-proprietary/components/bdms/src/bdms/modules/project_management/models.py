# 🔒 NO_TOKEN — 纯代码，零 AI 依赖
"""项目管理模块数据契约：枚举 + 状态机 + 阶段模板。

对齐 DESIGN-DETAIL-PROJECT-MANAGEMENT-v2.1.md §5（状态机）/ §3.2.8（售后）/ §3.2.1（7 阶段模板）。
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Set


# ============================================================
# 项目状态机（§5.2 合法状态转换矩阵）
# ============================================================

class ProjectStatus(str, Enum):
    INITIATING = "initiating"    # 立项中
    PLANNING = "planning"        # 规划中
    EXECUTING = "executing"      # 执行中
    DELIVERING = "delivering"    # 交付中
    ACCEPTING = "accepting"      # 验收中
    AFTER_SALES = "after_sales"  # 售后服务期（v2.1 新增）
    CLOSING = "closing"          # 结项中
    CLOSED = "closed"            # 已结项
    CANCELLED = "cancelled"      # 已取消


VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "initiating": {"planning", "cancelled"},
    "planning": {"executing", "cancelled"},
    "executing": {"delivering", "cancelled"},
    "delivering": {"accepting", "cancelled"},
    "accepting": {"after_sales", "closing", "cancelled"},   # 验收通过：转售后 / 直接结项
    "after_sales": {"closing", "cancelled"},                 # 售后结束 → 结项
    "closing": {"closed", "cancelled"},
    "closed": set(),                                          # 终态
    "cancelled": {"initiating"},                              # 重新激活
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    """判断项目状态转换是否合法。

    规则（§5.4）：
    - 任意非 closed 状态可转 cancelled（需权限校验，此处只管状态合法性）
    - 其余按 VALID_TRANSITIONS 白名单
    """
    if from_state not in VALID_TRANSITIONS:
        return False
    if from_state == "cancelled":
        return to_state in VALID_TRANSITIONS[from_state]
    if to_state == "cancelled":
        return from_state != "closed"
    return to_state in VALID_TRANSITIONS[from_state]


# ============================================================
# 7 阶段默认模板（§3.2.1）
# ============================================================

DEFAULT_PHASES_V21: List[Dict] = [
    {"phase_name": "立项阶段", "phase_order": 10},
    {"phase_name": "规划阶段", "phase_order": 20},
    {"phase_name": "执行阶段", "phase_order": 30},
    {"phase_name": "交付阶段", "phase_order": 40},
    {"phase_name": "验收阶段", "phase_order": 50},
    {"phase_name": "售后阶段", "phase_order": 55},   # 插在验收与结项之间
    {"phase_name": "结项阶段", "phase_order": 60},
]


# ============================================================
# 实施状态（impl_status 字段枚举）
# ============================================================

class ImplStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    DELAYED = "delayed"
    COMPLETED = "completed"


VALID_IMPL_STATUSES = {s.value for s in ImplStatus}


# ============================================================
# 售后工单状态机（§3.2.8.2~8.5）
# ============================================================

class TicketState(str, Enum):
    OPEN = "open"                # 待受理
    ASSIGNED = "assigned"        # 已分派
    IN_PROGRESS = "in_progress"  # 处理中
    RESOLVED = "resolved"        # 已解决（待客户确认）
    CLOSED = "closed"            # 已关闭


TICKET_VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "open": {"assigned", "closed"},          # 直接收工单误报
    "assigned": {"in_progress", "open", "resolved"},  # 退回 / 直接解决（§3.2.8.4）
    "in_progress": {"resolved"},
    "resolved": {"closed", "in_progress"},   # 客户不确认，重新打开
    "closed": set(),                          # 终态
}


def is_valid_ticket_transition(from_state: str, to_state: str) -> bool:
    """判断工单状态转换是否合法。"""
    if from_state not in TICKET_VALID_TRANSITIONS:
        return False
    return to_state in TICKET_VALID_TRANSITIONS[from_state]


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ServiceLevel(str, Enum):
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"


# SLA 时限（小时）——对齐设计文档 §3.2.8.6
# 注意：设计文档的 SLA 按优先级（critical 2h/24h ... low 24h/10d），
# 引擎按 service_level 查表；priority=critical 时引擎自动提升一级。
SLA_HOURS: Dict[str, Dict[str, int]] = {
    "gold":   {"response": 2,  "resolution": 24},   # critical 级
    "silver": {"response": 4,  "resolution": 48},   # high 级
    "bronze": {"response": 8,  "resolution": 120},  # medium/low 级（120h=5工作日）
}


# ============================================================
# 风险等级矩阵（§6.4）
# ============================================================

RISK_LEVEL_MATRIX: Dict[tuple, str] = {
    ("high", "high"): "critical",
    ("high", "medium"): "high",
    ("high", "low"): "medium",
    ("medium", "high"): "high",
    ("medium", "medium"): "medium",
    ("medium", "low"): "low",
    ("low", "high"): "medium",
    ("low", "medium"): "low",
    ("low", "low"): "low",
}


def calculate_risk_level(probability: str, impact: str) -> str:
    """按概率×影响矩阵计算风险等级。"""
    key = (probability.lower(), impact.lower())
    if key not in RISK_LEVEL_MATRIX:
        raise ValueError(f"Invalid probability/impact: {probability}/{impact}")
    return RISK_LEVEL_MATRIX[key]


class RiskStatus(str, Enum):
    OPEN = "open"
    ASSESSING = "assessing"
    MITIGATING = "mitigating"
    ACCEPTED = "accepted"
    TRANSFERRED = "transferred"
    AVOIDED = "avoided"
    CLOSED = "closed"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ============================================================
# 变更请求状态（§4.4）
# ============================================================

class ChangeStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    ASSESSING = "assessing"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ============================================================
# 成本相关枚举（§7）
# ============================================================

class TimesheetStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
