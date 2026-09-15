"""
数据模型 — L3 纯逻辑层使用的内存数据结构
============================================

所有模型都是不可变语义的 dataclass，L4 负责与数据库/ORM 映射。

设计原则：
- 纯数据，不包含任何业务逻辑（业务逻辑在 state_machine / risk_engine 中）
- 不依赖任何外部库（仅 stdlib dataclasses）
- 字段命名与数据库列名一致，方便 L4 做 dict 互转
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============================================================
# 状态枚举（用 dict 代替 enum，方便 JSON 序列化）
# ============================================================

CONTRACT_STATUSES = {
    "draft": "起草",
    "review1": "一级审批",
    "review2": "二级审批",
    "review3": "三级审批",
    "approved": "审批通过",
    "signed": "已签署",
    "archived": "已归档",
    "rejected": "已驳回",
}

# 状态流转图（状态机的静态配置）
VALID_TRANSITIONS = {
    "draft": {"review1"},           # 提交审批
    "review1": {"draft", "review2", "approved"},   # 驳回 / 通过进入下一级 / 末级通过
    "review2": {"draft", "review3", "approved"},
    "review3": {"draft", "approved"},
    "approved": {"signed"},         # 签署
    "signed": {"archived"},         # 归档
    "archived": set(),              # 终态
    "rejected": {"draft"},          # 驳回后可修改重提
}


@dataclass
class ApprovalConfig:
    """审批配置（由金额决定）"""
    level: int                    # 审批层级 1~4
    roles: List[str]              # 各层级审批角色（按顺序）
    sla_days: Optional[int] = None  # SLA 工作日数（L4 可注入）


@dataclass
class Contract:
    """
    合同内存模型
    L3 只用到审批流转需要的字段；L4 持久化层可扩展更多字段。
    """
    id: Optional[int] = None
    contract_no: str = ""
    title: str = ""
    contract_type: str = "tech_service"
    party_a: str = ""
    party_b: str = ""
    amount: float = 0.0
    status: str = "draft"
    current_approver: Optional[str] = None
    created_by: str = ""
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None
    # 扩展字段（L4 用 dict 透传，L3 不感知）
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRecord:
    """审批记录"""
    id: Optional[int] = None
    contract_id: int = 0
    approval_level: int = 0
    approver_role: str = ""
    approver_name: str = ""
    action: str = ""               # approve / reject / delegate
    comment: str = ""
    created_at: str = ""


@dataclass
class AuditLogEntry:
    """审计日志条目"""
    id: Optional[int] = None
    contract_id: int = 0
    action: str = ""
    operator: str = ""
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    created_at: str = ""


@dataclass
class RiskFinding:
    """单条风险检查结果"""
    id: str
    category: str
    item: str
    status: str          # pass / warning / fail
    risk: str            # high / medium / low
    law: str             # 法条依据，如 "§470"


@dataclass
class RiskReport:
    """风险扫描报告"""
    overall_risk: str          # high / medium / low
    summary: Dict[str, int]    # {"pass": N, "warning": N, "fail": N}
    findings: List[RiskFinding]
    scan_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_risk": self.overall_risk,
            "summary": self.summary,
            "scan_time": self.scan_time,
            "findings": [
                {
                    "id": f.id,
                    "category": f.category,
                    "item": f.item,
                    "status": f.status,
                    "risk": f.risk,
                    "law": f.law,
                }
                for f in self.findings
            ],
        }
