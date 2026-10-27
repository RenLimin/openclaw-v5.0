"""AC-8 纯函数幂等：同入参连跑 3 次一致，入参不被修改。"""
import contract_management as cm


def test_scan_idempotent():
    text = "甲方：甲公司\n乙方：乙公司\n盖章\n"
    outs = [cm.scan_text_dict(text)["findings"] for _ in range(3)]
    assert outs[0] == outs[1] == outs[2]


def test_state_machine_idempotent():
    outs = [
        cm.next_approval_status(800_000, "review2", "approve")
        for _ in range(3)
    ]
    assert outs[0] == outs[1] == outs[2]


def test_input_contract_not_mutated():
    c = cm.Contract(contract_no="C", amount=800_000, status="draft")
    sm = cm.ApprovalStateMachine(c)
    for _ in range(3):
        sm.submit("u")
    assert c.status == "draft"
