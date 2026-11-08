"""P4.2 前置：OA 审批人身份映射单测。

锁定黄金夹具证据（oa_log_882663）：
- 工号目录完整（949/3/364/1625/2032/1313/2038）；
- 节点 ↔ L3 角色语义；
- AI 系统账号排除（is_human_approver）；
- 未收录工号返回 None / 空（不编造）。
"""
from __future__ import annotations

import os
import sys

COMPONENT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if COMPONENT_ROOT not in sys.path:
    sys.path.insert(0, COMPONENT_ROOT)

from services.oa.approval_identity import (  # noqa: E402
    OA_NODE_TO_ROLE,
    OA_PERSON_DIRECTORY,
    approver_roles,
    directory,
    is_human_approver,
    node_roles,
    resolve_approver,
)


# ---------- 工号目录 ----------

def test_directory_contains_golden_persons():
    d = directory()
    assert set(d.keys()) == {"949", "3", "364", "1625", "2032", "1313", "2038"}
    assert d["3"]["name"] == "阚志刚"
    assert d["3"]["dept"] == "高管团队"
    assert d["3"]["node"] == "分管总监"
    assert d["3"]["evidence"] == "oa_log_882663"


def test_resolve_approver_known():
    p = resolve_approver("364")
    assert p["name"] == "王仙仙"
    assert p["node"] == "部门经理"
    assert "退回" in p["action_seen"]


def test_resolve_approver_unknown_returns_none():
    assert resolve_approver("999999") is None
    assert resolve_approver("") is None


def test_resolve_approver_string_coercion():
    # 工号可能是 int（OA base_info.userId 实测 int）
    assert resolve_approver(3)["name"] == "阚志刚"


# ---------- 节点 ↔ L3 角色 ----------

def test_node_roles_golden_nodes():
    assert node_roles("部门经理") == ["销售经理"]
    assert node_roles("分管总监") == ["销售总监", "VP/CEO"]
    assert node_roles("合同评审小组") == ["法务审查员", "财务经理"]
    assert node_roles("申请人") == ["发起人"]
    assert node_roles("商务") == ["商务初审"]


def test_node_roles_unknown():
    assert node_roles("不存在的节点") == []


def test_approver_roles_via_directory():
    # 王仙仙（部门经理）→ 销售经理
    assert approver_roles("364") == ["销售经理"]
    # 阚志刚（分管总监）→ 销售总监 + VP
    assert set(approver_roles("3")) == {"销售总监", "VP/CEO"}
    # 未知工号 → 空
    assert approver_roles("999") == []


# ---------- AI 账号排除 ----------

def test_is_human_approver_excludes_ai():
    assert is_human_approver("3") is True
    assert is_human_approver("364") is True
    # AI 小助手（系统账号）→ False
    assert is_human_approver("2038") is False
    # 未知工号 → False
    assert is_human_approver("999") is False


# ---------- 一致性：节点全集 = 目录节点集合 ----------

def test_directory_nodes_are_covered_by_node_map():
    nodes_in_dir = {p["node"] for p in OA_PERSON_DIRECTORY.values()}
    assert nodes_in_dir <= set(OA_NODE_TO_ROLE.keys())
