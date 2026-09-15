"""
L3 合同审批核心 — 纯逻辑层（零副作用）
========================================

本模块是 L3 通用合同审批能力的**纯计算核心**：
- 不读文件、不写数据库、不调用外部服务
- 所有输入通过参数传入，所有输出通过返回值传出
- 可被 L4 业务层任意编排，也可独立单元测试

调用方向：L4 → L3（L3 绝不依赖 L4）

公开 API（见各子模块）：
    - models:        数据模型（dataclass）
    - state_machine: 审批状态机（状态流转 + 分级规则）
    - risk_engine:   风险扫描引擎（22 条规则 + 综合评级）
    - amount_utils:  金额工具（中文大写等）
"""

from .models import (
    Contract,
    ApprovalRecord,
    AuditLogEntry,
    RiskReport,
    RiskFinding,
    ApprovalConfig,
    CONTRACT_STATUSES,
)
from .state_machine import (
    ApprovalStateMachine,
    get_approval_config,
    can_transition,
    next_approval_status,
)
from .risk_engine import scan_text, RiskRule, CHECK_RULES
from .amount_utils import amount_to_chinese

__all__ = [
    # models
    "Contract",
    "ApprovalRecord",
    "AuditLogEntry",
    "RiskReport",
    "RiskFinding",
    "ApprovalConfig",
    "CONTRACT_STATUSES",
    # state_machine
    "ApprovalStateMachine",
    "get_approval_config",
    "can_transition",
    "next_approval_status",
    # risk_engine
    "scan_text",
    "RiskRule",
    "CHECK_RULES",
    # amount_utils
    "amount_to_chinese",
]
