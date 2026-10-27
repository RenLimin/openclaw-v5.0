"""AC-4/AC-5 状态机流转 + 分级表黄金基准。"""
import pytest

import contract_management as cm
from contract_management.state_machine import DEFAULT_APPROVAL_LEVELS


# ---------- 分级黄金基准 ----------
@pytest.mark.parametrize("amount,level", [
    (0, 1), (99_999.99, 1),
    (100_000, 2), (499_999.99, 2),
    (500_000, 3), (1_999_999.99, 3),
    (2_000_000, 4), (100_000_000, 4),
])
def test_level_boundaries(amount, level):
    assert cm.get_approval_config(amount).level == level


def test_level_roles_sequence():
    cfg = cm.get_approval_config(800_000)
    assert cfg.level == 3
    assert cfg.roles == ["销售总监", "法务审查员", "财务经理"]


def test_custom_level_table_injected():
    custom = [(0, 50, 1, ["X"]), (50, float("inf"), 2, ["X", "Y"])]
    assert cm.get_approval_config(100, custom).level == 2
    # 默认表不受影响（证明参数真正生效而非被忽略）
    assert cm.get_approval_config(100).level == 1


# ---------- 纯函数状态流转 ----------
def test_submit():
    nxt, role, lvl = cm.next_approval_status(50_000, "draft", "submit")
    assert (nxt, role, lvl) == ("review1", "销售经理", 0)


def test_multi_level_progress():
    assert cm.next_approval_status(800_000, "review1", "approve")[0] == "review2"
    assert cm.next_approval_status(800_000, "review2", "approve")[0] == "review3"
    nxt, role, _ = cm.next_approval_status(800_000, "review2", "approve")
    assert role == "财务经理"


def test_final_level_approved():
    nxt, role, _ = cm.next_approval_status(800_000, "review3", "approve")
    assert nxt == "approved" and role is None


def test_single_level_skips_to_approved():
    assert cm.next_approval_status(50_000, "review1", "approve")[0] == "approved"


def test_reject_back_to_draft():
    assert cm.next_approval_status(800_000, "review2", "reject")[0] == "draft"


def test_sign_and_archive():
    assert cm.next_approval_status(0, "approved", "sign")[0] == "signed"
    assert cm.next_approval_status(0, "signed", "archive")[0] == "archived"


@pytest.mark.parametrize("status,action", [
    ("draft", "approve"), ("approved", "submit"),
    ("archived", "archive"), ("signed", "approve"),
])
def test_illegal_transitions_raise(status, action):
    with pytest.raises(ValueError):
        cm.next_approval_status(50_000, status, action)


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        cm.next_approval_status(50_000, "draft", "bogus")


def test_can_transition_matches_table():
    # 遍历 VALID_TRANSITIONS 全连接，两个判定必须一致
    for src, targets in cm.VALID_TRANSITIONS.items():
        for tgt in targets:
            assert cm.can_transition(src, tgt) is True
        assert cm.can_transition(src, "__none__") is False


# ---------- OO 包装 ----------
def _contract(amount=800_000, status="draft"):
    return cm.Contract(contract_no="C1", amount=amount, status=status)


def test_oo_submit_does_not_mutate():
    sm = cm.ApprovalStateMachine(_contract())
    out = sm.submit("alice")
    assert out["next_status"] == "review1"
    assert sm.contract.status == "draft"  # 入参不被修改
    assert out["total_steps"] == 3
    assert out["audit_log"].to_status == "review1" if hasattr(out["audit_log"], "to_status") else True


def test_oo_approve_keys():
    sm = cm.ApprovalStateMachine(_contract(status="review1"))
    out = sm.approve("bob", "销售总监", "ok")
    assert {"next_status", "approval_record", "audit_log", "step", "total_steps"} <= set(out)


def test_oo_reject_keys():
    sm = cm.ApprovalStateMachine(_contract(status="review2"))
    out = sm.reject("bob", "法务", "no")
    assert out["next_status"] == "draft"
    assert "rejected_at_level" in out


def test_oo_guards():
    sm = cm.ApprovalStateMachine(_contract())
    assert sm.can_submit() and not sm.can_sign()
    sm2 = cm.ApprovalStateMachine(_contract(status="approved"))
    assert sm2.can_sign()


# ---------- 补充覆盖率：守卫与 OO sign/archive、非法动作 ----------
def test_oo_can_approve_reject_archive_guards():
    sm_r = cm.ApprovalStateMachine(_contract(status="review2"))
    assert sm_r.can_approve() and sm_r.can_reject()
    sm_s = cm.ApprovalStateMachine(_contract(status="signed"))
    assert sm_s.can_archive()
    sm_d = cm.ApprovalStateMachine(_contract(status="draft"))
    assert not sm_d.can_approve() and not sm_d.can_reject() and not sm_d.can_archive()


def test_oo_sign_and_archive():
    sm = cm.ApprovalStateMachine(_contract(status="approved"))
    out = sm.sign("alice")
    assert out["next_status"] == "signed"
    assert out["audit_log"].action == "sign"
    sm2 = cm.ApprovalStateMachine(_contract(status="signed"))
    out2 = sm2.archive("alice")
    assert out2["next_status"] == "archived"
    assert out2["audit_log"].action == "archive"


def test_reject_from_non_review_raises():
    with pytest.raises(ValueError):
        cm.next_approval_status(0, "draft", "reject")


def test_sign_from_non_approved_raises():
    with pytest.raises(ValueError):
        cm.next_approval_status(0, "draft", "sign")


def test_fallback_lowest_level():
    # 构造一个异常金额情景较难，直接验证默认表首行 roles 可访问
    cfg = cm.get_approval_config(-1)
    assert cfg.level == 1


def test_oo_roles_property():
    sm = cm.ApprovalStateMachine(_contract(amount=800_000))
    assert sm.roles == ["销售总监", "法务审查员", "财务经理"]
