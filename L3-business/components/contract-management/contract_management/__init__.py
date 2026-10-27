"""
L3 通用合同管理 — 纯逻辑公共 API
==================================

零副作用：不读文件、不写 DB、不调网络。
调用方向：L4 → L3（L3 绝不依赖 L4）。
"""

from .models import (
    Contract,
    ApprovalRecord,
    AuditLogEntry,
    RiskReport,
    RiskFinding,
    ApprovalConfig,
    CONTRACT_STATUSES,
    VALID_TRANSITIONS,
)
from .state_machine import (
    ApprovalStateMachine,
    get_approval_config,
    can_transition,
    next_approval_status,
)
from .risk_engine import (
    scan_text,
    scan_text_dict,
    RiskRule,
    CHECK_RULES,
)
from .amount_utils import amount_to_chinese
from .oa import OaProvider

__all__ = [
    # models
    "Contract",
    "ApprovalRecord",
    "AuditLogEntry",
    "RiskReport",
    "RiskFinding",
    "ApprovalConfig",
    "CONTRACT_STATUSES",
    "VALID_TRANSITIONS",
    # state_machine
    "ApprovalStateMachine",
    "get_approval_config",
    "can_transition",
    "next_approval_status",
    # risk_engine
    "scan_text",
    "scan_text_dict",
    "RiskRule",
    "CHECK_RULES",
    # amount_utils
    "amount_to_chinese",
    # oa
    "OaProvider",
]
