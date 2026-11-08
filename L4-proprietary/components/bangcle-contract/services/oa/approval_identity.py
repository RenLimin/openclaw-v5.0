"""P4.2 前置：OA 审批人身份映射（证据驱动，只读）。

数据来源：黄金夹具 `tests/fixtures/oa_log_882663.json`（10 条真实审批链，
2026-11-04 录制脱敏）。全部记录标注证据，未确认的映射显式标记待确认，
不编造权威对应关系。

两层映射：
1. OA 节点（log_nodename）↔ L3 审批角色语义（DEFAULT_APPROVAL_LEVELS 角色）；
2. OA 工号（displayid）↔ 人/部门/节点（审批人目录）。

用途：P4.2 真实写回落地时，校验调用者是否为 OA 流程当前节点的合法审批人
（human 审批身份绑定）；对账报告亦可展示「OA 节点 → L3 角色」可读语义。

铁律：本模块只读、无网络、无依赖；映射全部可审计溯源。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------
# 一、OA 节点 ↔ L3 审批角色语义（证据：oa_log_882663 节点全集）
#    L3 角色来自 contract_management/state_machine.py
#    DEFAULT_APPROVAL_LEVELS（销售经理/法务审查员/销售总监/财务经理/
#    VP-CEO/法务总监/财务总监）
# ---------------------------------------------------------------
OA_NODE_TO_ROLE: Dict[str, List[str]] = {
    # 申请人：流程发起者（何钰其提交）。L3 无对应审批角色 → 发起人身份
    "申请人": ["发起人"],
    # 部门经理：一级审批（王仙仙，上海分公司-金融）→ 对应 L3 销售经理
    "部门经理": ["销售经理"],
    # 分管总监：二级/三级审批（阚志刚，高管团队）→ 对应 L3 销售总监/VP
    "分管总监": ["销售总监", "VP/CEO"],
    # 合同评审小组：会签节点（任立民/张火平，交付中心/财务部）→
    #   对应 L3 法务审查员 + 财务经理（评审小组为角色组合）
    "合同评审小组": ["法务审查员", "财务经理"],
    # 商务：商务初审（佟鑫，行政部）。L3 审批链无对应 → 商务前置角色
    "商务": ["商务初审"],
}

# 未在黄金夹具出现、但 L3 审批链含的角色 → 待 OA 流程图确认对应节点
L3_ROLE_TO_OA_NODE_UNCONFIRMED: Dict[str, List[str]] = {
    "法务总监": [],   # 待确认：OA 中是否独立节点（或并入合同评审小组）
    "财务总监": [],   # 待确认
    "财务经理": [],   # 合同评审小组含财务部成员，节点归属待确认
}

# ---------------------------------------------------------------
# 二、OA 工号目录（证据：oa_log_882663 10 条记录逐人提取）
# ---------------------------------------------------------------
OA_PERSON_DIRECTORY: Dict[str, Dict[str, Any]] = {
    "949": {
        "name": "佟鑫",
        "dept": "行政部",
        "node": "商务",
        "action_seen": ["抄送", "批准"],
        "evidence": "oa_log_882663",
    },
    "3": {
        "name": "阚志刚",
        "dept": "高管团队",
        "node": "分管总监",
        "action_seen": ["批准"],
        "evidence": "oa_log_882663",
    },
    "364": {
        "name": "王仙仙",
        "dept": "上海分公司-金融",
        "node": "部门经理",
        "action_seen": ["批准", "退回"],
        "evidence": "oa_log_882663",
    },
    "1625": {
        "name": "何钰其",
        "dept": "上海分公司-金融",
        "node": "申请人",
        "action_seen": ["提交"],
        "evidence": "oa_log_882663",
    },
    "2032": {
        "name": "张火平",
        "dept": "财务部",
        "node": "合同评审小组",
        "action_seen": ["提交"],
        "evidence": "oa_log_882663",
    },
    "1313": {
        "name": "任立民",
        "dept": "交付中心",
        "node": "合同评审小组",
        "action_seen": ["提交"],
        "evidence": "oa_log_882663",
    },
    "2038": {
        "name": "AI小助手",
        "dept": "信息管理部",
        "node": "申请人",
        "action_seen": ["批注"],
        "evidence": "oa_log_882663",
        "note": "系统账号（AI 批注），非人工审批人",
    },
}


class ApprovalIdentityError(KeyError):
    """身份查找失败。"""


def resolve_approver(operator_id: str) -> Optional[Dict[str, Any]]:
    """工号 → 审批人信息（目录条目），未收录返回 None。"""
    return OA_PERSON_DIRECTORY.get(str(operator_id).strip())


def node_roles(node: str) -> List[str]:
    """OA 节点名 → L3 角色语义（未收录返回 []）。"""
    return OA_NODE_TO_ROLE.get(node, [])


def approver_roles(operator_id: str) -> List[str]:
    """工号 → 其所在节点的 L3 角色（目录无此人 → 空列表）。"""
    person = resolve_approver(operator_id)
    if not person:
        return []
    return OA_NODE_TO_ROLE.get(person.get("node", ""), [])


def is_human_approver(operator_id: str) -> bool:
    """是否为人工审批人（排除 AI 系统账号）。"""
    person = resolve_approver(operator_id)
    if not person:
        return False
    return person.get("name") != "AI小助手" and "AI" not in person.get("name", "")


def directory() -> Dict[str, Dict[str, Any]]:
    """全量目录（审计用，含证据字段）。"""
    return OA_PERSON_DIRECTORY
