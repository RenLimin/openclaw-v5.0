"""合同管理数据模型 — L4 持久化层 dataclass。

🔒 NO_TOKEN — 纯代码，零 AI 依赖。

与 schemas_v21.py CR_SCHEMA 表结构对齐。
L3 的 models.py 是纯逻辑层，本文件是 L4 的持久化模型（字段更多）。
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


# ─── 合同状态枚举 ───

CONTRACT_STATUSES = {
    "draft": "起草",
    "review1": "一级审批",
    "review2": "二级审批",
    "review3": "三级审批",
    "review4": "四级审批",
    "approved": "审批通过",
    "signed": "已签署",
    "archived": "已归档",
    "rejected": "已驳回",
}

# 状态流转规则（与 L3 state_machine 保持一致）
VALID_TRANSITIONS = {
    "draft": {"review1"},
    "review1": {"draft", "review2", "approved"},
    "review2": {"draft", "review3", "approved"},
    "review3": {"draft", "review4", "approved"},
    "review4": {"draft", "approved"},
    "approved": {"signed"},
    "signed": {"archived"},
    "archived": set(),
    "rejected": {"draft"},
}


@dataclass
class Contract:
    """合同主表（cr_contracts 对应的内存模型）。"""
    contract_no: str
    title: str
    party_a: str = ""
    party_b: str = ""
    amount: float = 0.0
    currency: str = "CNY"
    contract_type: str = ""
    effective_date: str = ""
    expiry_date: str = ""
    status: str = "draft"
    approval_level: int = 1
    signed_date: str = ""
    archive_date: str = ""
    # 审计字段
    created_by: str = ""
    updated_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    # 软删除
    deleted_at: Optional[str] = None
    # 内部
    id: Optional[int] = None


@dataclass
class ContractDocument:
    """合同文件（cr_contract_documents）。"""
    contract_id: int = 0
    version: int = 1
    file_path: str = ""
    file_hash: str = ""
    watermark: str = ""          # draft / approved / signed
    created_by: str = ""
    created_at: str = ""
    id: Optional[int] = None


@dataclass
class ContractClause:
    """合同条款（cr_contract_clauses）。"""
    contract_id: int = 0
    clause_type: str = ""
    clause_title: str = ""
    clause_content: str = ""
    sort_order: int = 0
    created_at: str = ""
    deleted_at: Optional[str] = None
    id: Optional[int] = None


@dataclass
class RiskScanResult:
    """风险扫描结果（cr_risk_scan_results）。"""
    contract_id: int = 0
    scan_batch: str = ""
    risk_category: str = ""
    risk_level: str = ""         # high / medium / low
    issue_summary: str = ""
    suggestion: str = ""
    status: str = "open"         # open / resolved / ignored
    created_at: str = ""
    deleted_at: Optional[str] = None
    id: Optional[int] = None


@dataclass
class ApprovalNode:
    """审批节点（从审批日志 + 审批配置推导）。"""
    contract_id: int = 0
    from_status: str = ""
    to_status: str = ""
    action: str = ""             # submit / approve / reject / sign / archive
    approver_name: str = ""
    approver_role: str = ""
    comment: str = ""
    created_at: str = ""
    id: Optional[int] = None


@dataclass
class AuditTrailEntry:
    """审计追踪条目（cr_audit_trail）。"""
    contract_id: int = 0
    operation: str = ""
    field_name: str = ""
    old_value: str = ""
    new_value: str = ""
    operator: str = ""
    created_at: str = ""
    id: Optional[int] = None


# ─── 合同关系类型 ───

class ContractRelationType:
    """合同关系类型常量。"""
    MASTER_SLAVE = "master_slave"       # 主从合同
    RELATED = "related"                 # 关联合同
    SUPPLEMENTARY = "supplementary"     # 补充协议
    SUPPLEMENT = "supplement"           # （旧）补充协议，兼容
    TERMINATION = "termination"         # 终止协议
    ORDER = "order"                     # 订单
    AMENDMENT = "amendment"             # 修正案


VALID_RELATION_TYPES = {
    ContractRelationType.MASTER_SLAVE,
    ContractRelationType.RELATED,
    ContractRelationType.SUPPLEMENTARY,
    ContractRelationType.SUPPLEMENT,
    ContractRelationType.TERMINATION,
    ContractRelationType.ORDER,
    ContractRelationType.AMENDMENT,
}

RELATION_TYPE_LABELS = {
    ContractRelationType.MASTER_SLAVE: "主从合同",
    ContractRelationType.RELATED: "关联合同",
    ContractRelationType.SUPPLEMENTARY: "补充协议",
    ContractRelationType.SUPPLEMENT: "补充协议(旧)",
    ContractRelationType.TERMINATION: "终止协议",
    ContractRelationType.ORDER: "订单",
    ContractRelationType.AMENDMENT: "修正案",
}


# ─── 实施状态 ───

class ImplStatus:
    """实施状态常量。"""
    NOT_STARTED = "not_started"     # 未开始
    IN_PROGRESS = "in_progress"     # 实施中
    COMPLETED = "completed"         # 已完成
    SUSPENDED = "suspended"         # 暂停
    CANCELLED = "cancelled"         # 取消


VALID_IMPL_STATUSES = {
    ImplStatus.NOT_STARTED,
    ImplStatus.IN_PROGRESS,
    ImplStatus.COMPLETED,
    ImplStatus.SUSPENDED,
    ImplStatus.CANCELLED,
}

IMPL_STATUS_LABELS = {
    ImplStatus.NOT_STARTED: "未开始",
    ImplStatus.IN_PROGRESS: "实施中",
    ImplStatus.COMPLETED: "已完成",
    ImplStatus.SUSPENDED: "暂停",
    ImplStatus.CANCELLED: "取消",
}


@dataclass
class ContractRelation:
    """合同关系（cr_contract_relations）。"""
    source_contract_id: int = 0
    target_contract_id: int = 0
    relation_type: str = ""
    match_rule: str = "manual"
    created_at: str = ""
    id: Optional[int] = None
