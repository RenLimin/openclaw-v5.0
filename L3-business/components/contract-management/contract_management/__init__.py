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
    VALID_TRANSITIONS,
)
from .state_machine import (
    ApprovalStateMachine,
    get_approval_config,
    can_transition,
    next_approval_status,
)
from .risk_engine import scan_text, scan_text_dict, RiskRule, CHECK_RULES
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
    # P2: 条款解析 / 审核标准 / 审核引擎 / 适配器
    "ContractClause",
    "ParsedContract",
    "parse_contract",
    "format_parsed_contract",
    "CLAUSE_CATEGORIES",
    "AuditCriterion",
    "AUDIT_CRITERIA",
    "get_criterion_by_id",
    "get_criteria_by_category",
    "get_all_categories",
    "AuditResult",
    "AuditReport",
    "audit_contract",
    "format_audit_report",
    "HANDLERS",
    # oa
    "OaProvider",
]

# --- P2: 条款解析 / 审核标准 / 审核引擎（CLM-GEN-001） ---
from .contract_parser import (
    ContractClause,
    ParsedContract,
    parse_contract,
    format_parsed_contract,
    CLAUSE_CATEGORIES,
)
from .audit_standard import (
    AuditCriterion,
    AUDIT_CRITERIA,
    get_criterion_by_id,
    get_criteria_by_category,
    get_all_categories,
)
from .contract_auditor import (
    AuditResult,
    AuditReport,
    audit_contract,
    format_audit_report,
)
from .risk_scanner import scan_text as scan_text_fast  # 兼容 shim（去重，逻辑同 risk_engine）
from .ontology_adapter import HANDLERS
from .oa import OaProvider
