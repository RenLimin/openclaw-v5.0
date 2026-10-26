"""
审批状态机 — L3 纯逻辑核心
============================

纯函数式状态机：输入当前状态 + 操作 + 配置 → 输出下一状态 + 审批记录。
不碰数据库、不写日志、不产生副作用。

L4 负责：
  - 从数据库读取合同当前状态
  - 调用本模块计算下一状态
  - 将结果写回数据库 + 审计日志
"""

from typing import Optional, Tuple, List
from .models import (
    Contract,
    ApprovalConfig,
    ApprovalRecord,
    AuditLogEntry,
    VALID_TRANSITIONS,
)
from datetime import datetime


# ============================================================
# 分级审批阈值（通用默认值，L4 可覆盖）
# ============================================================

DEFAULT_APPROVAL_LEVELS: List[Tuple[float, float, int, List[str]]] = [
    (0,          100_000,     1, ["销售经理"]),
    (100_000,    500_000,     2, ["销售经理", "法务审查员"]),
    (500_000,  2_000_000,     3, ["销售总监", "法务审查员", "财务经理"]),
    (2_000_000, float("inf"), 4, ["VP/CEO", "法务总监", "财务总监"]),
]


def get_approval_config(amount: float,
                        level_table: Optional[List[Tuple[float, float, int, List[str]]]] = None
                        ) -> ApprovalConfig:
    """根据金额获取审批配置

    Args:
        amount: 合同金额
        level_table: 可选，自定义分级表（L4 注入）。格式同 DEFAULT_APPROVAL_LEVELS。

    Returns:
        ApprovalConfig
    """
    table = level_table or DEFAULT_APPROVAL_LEVELS
    for min_amt, max_amt, level, roles in table:
        if min_amt <= amount < max_amt:
            return ApprovalConfig(level=level, roles=list(roles))
    # fallback：最低级
    return ApprovalConfig(level=1, roles=list(table[0][3]))


def can_transition(from_status: str, to_status: str) -> bool:
    """检查状态流转是否合法"""
    return to_status in VALID_TRANSITIONS.get(from_status, set())


def _current_level(status: str) -> int:
    """从状态名提取当前审批级别，如 review2 → 2"""
    if status.startswith("review"):
        return int(status.replace("review", ""))
    return 0


def next_approval_status(amount: float, current_status: str, action: str,
                         level_table: Optional[List[Tuple[float, float, int, List[str]]]] = None
                         ) -> Tuple[str, Optional[str], int]:
    """计算审批操作后的下一状态

    Args:
        amount: 合同金额（用于确定审批层级）
        current_status: 当前状态
        action: 操作类型 — "submit" / "approve" / "reject" / "sign" / "archive"
        level_table: 可选，自定义分级表

    Returns:
        (next_status, next_approver_role, current_level)
        - next_status: 下一状态
        - next_approver_role: 下一审批角色（None 表示终态或无）
        - current_level: 当前审批级别（用于记录）

    Raises:
        ValueError: 操作不合法时
    """
    config = get_approval_config(amount, level_table)
    level = config.level

    if action == "submit":
        if current_status != "draft":
            raise ValueError(f"当前状态 {current_status} 不能提交审批")
        next_status = "review1"
        next_role = config.roles[0] if config.roles else None
        return next_status, next_role, 0

    if action == "approve":
        cur_lvl = _current_level(current_status)
        if cur_lvl == 0:
            raise ValueError(f"当前状态 {current_status} 不能审批通过")
        if cur_lvl >= level:
            # 已经是最后一级，审批全部通过
            return "approved", None, cur_lvl
        else:
            next_status = f"review{cur_lvl + 1}"
            next_role = config.roles[cur_lvl] if cur_lvl < len(config.roles) else None
            return next_status, next_role, cur_lvl

    if action == "reject":
        cur_lvl = _current_level(current_status)
        if cur_lvl == 0:
            raise ValueError(f"当前状态 {current_status} 不能驳回")
        return "draft", None, cur_lvl

    if action == "sign":
        if current_status != "approved":
            raise ValueError(f"当前状态 {current_status} 不能签署")
        return "signed", None, 0

    if action == "archive":
        if current_status != "signed":
            raise ValueError(f"当前状态 {current_status} 不能归档")
        return "archived", None, 0

    raise ValueError(f"未知操作: {action}")


class ApprovalStateMachine:
    """
    面向对象的状态机包装 — 持有合同对象 + 配置，提供业务语义方法。

    注意：本类不修改传入的 contract，只返回计算结果。
    所有状态变更由 L4 持久化层执行。
    """

    def __init__(self, contract: Contract,
                 level_table: Optional[List[Tuple[float, float, int, List[str]]]] = None):
        self.contract = contract
        self.level_table = level_table
        self.config = get_approval_config(contract.amount, level_table)

    @property
    def level(self) -> int:
        return self.config.level

    @property
    def roles(self) -> List[str]:
        return self.config.roles

    def can_submit(self) -> bool:
        return self.contract.status == "draft"

    def can_approve(self) -> bool:
        return self.contract.status.startswith("review")

    def can_reject(self) -> bool:
        return self.contract.status.startswith("review")

    def can_sign(self) -> bool:
        return self.contract.status == "approved"

    def can_archive(self) -> bool:
        return self.contract.status == "signed"

    # --- 动作方法 ---

    def submit(self, operator: str) -> dict:
        """提交审批

        Returns:
            dict: {"next_status", "next_approver_role", "audit_log", "detail"}
        """
        next_status, next_role, _ = next_approval_status(
            self.contract.amount, self.contract.status, "submit", self.level_table
        )
        detail = {
            "approval_level": self.level,
            "first_approver": next_role,
        }
        audit = AuditLogEntry(
            contract_id=self.contract.id or 0,
            action="submit",
            operator=operator,
            from_status=self.contract.status,
            to_status=next_status,
            detail=detail,
            created_at=datetime.now().isoformat(),
        )
        return {
            "next_status": next_status,
            "next_approver_role": next_role,
            "audit_log": audit,
            "detail": detail,
            "total_steps": self.level,
        }

    def approve(self, approver_name: str, approver_role: str,
                comment: str = "") -> dict:
        """审批通过

        Returns:
            dict: {next_status, next_approver_role, approval_record, audit_log, step, total_steps}
        """
        next_status, next_role, cur_lvl = next_approval_status(
            self.contract.amount, self.contract.status, "approve", self.level_table
        )
        record = ApprovalRecord(
            contract_id=self.contract.id or 0,
            approval_level=cur_lvl,
            approver_role=approver_role,
            approver_name=approver_name,
            action="approve",
            comment=comment,
            created_at=datetime.now().isoformat(),
        )
        detail = {
            "level": cur_lvl,
            "comment": comment,
        }
        audit = AuditLogEntry(
            contract_id=self.contract.id or 0,
            action="approve",
            operator=approver_name,
            from_status=self.contract.status,
            to_status=next_status,
            detail=detail,
            created_at=datetime.now().isoformat(),
        )
        return {
            "next_status": next_status,
            "next_approver_role": next_role,
            "approval_record": record,
            "audit_log": audit,
            "step": cur_lvl,
            "total_steps": self.level,
        }

    def reject(self, approver_name: str, approver_role: str,
               comment: str) -> dict:
        """审批驳回

        Returns:
            dict: {next_status, approval_record, audit_log, rejected_at_level}
        """
        next_status, _, cur_lvl = next_approval_status(
            self.contract.amount, self.contract.status, "reject", self.level_table
        )
        record = ApprovalRecord(
            contract_id=self.contract.id or 0,
            approval_level=cur_lvl,
            approver_role=approver_role,
            approver_name=approver_name,
            action="reject",
            comment=comment,
            created_at=datetime.now().isoformat(),
        )
        detail = {
            "level": cur_lvl,
            "comment": comment,
        }
        audit = AuditLogEntry(
            contract_id=self.contract.id or 0,
            action="reject",
            operator=approver_name,
            from_status=self.contract.status,
            to_status=next_status,
            detail=detail,
            created_at=datetime.now().isoformat(),
        )
        return {
            "next_status": next_status,
            "approval_record": record,
            "audit_log": audit,
            "rejected_at_level": cur_lvl,
        }

    def sign(self, operator: str) -> dict:
        """签署合同"""
        next_status, _, _ = next_approval_status(
            self.contract.amount, self.contract.status, "sign", self.level_table
        )
        audit = AuditLogEntry(
            contract_id=self.contract.id or 0,
            action="sign",
            operator=operator,
            from_status=self.contract.status,
            to_status=next_status,
            created_at=datetime.now().isoformat(),
        )
        return {
            "next_status": next_status,
            "audit_log": audit,
        }

    def archive(self, operator: str) -> dict:
        """归档合同"""
        next_status, _, _ = next_approval_status(
            self.contract.amount, self.contract.status, "archive", self.level_table
        )
        audit = AuditLogEntry(
            contract_id=self.contract.id or 0,
            action="archive",
            operator=operator,
            from_status=self.contract.status,
            to_status=next_status,
            created_at=datetime.now().isoformat(),
        )
        return {
            "next_status": next_status,
            "audit_log": audit,
        }
