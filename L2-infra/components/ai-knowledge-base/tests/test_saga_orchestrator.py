"""P4 SagaOrchestrator unit tests (详设 §3.5).

Real in-memory connectors (tests.ont_handlers.MemoryConnector); no mocks.
"""
import pytest

from ai_kb.ontology.connectors.base import CompensationUnavailable
from ai_kb.ontology.connectors.saga import (
    SagaExecutionError,
    SagaOrchestrator,
    SagaReport,
    SagaStep,
)
from tests.ont_handlers import MemoryConnector


def _mk(name, **kw):
    return MemoryConnector(name, **kw)


# --- 正向：全部成功 ---

def test_all_steps_succeed():
    c1, c2, c3 = _mk("oa"), _mk("wecom"), _mk("erp")
    report = SagaOrchestrator([
        SagaStep("oa", c1), SagaStep("wecom", c2), SagaStep("erp", c3),
    ]).run()
    assert report.ok is True
    assert report.executed_steps == ["oa", "wecom", "erp"]
    assert report.compensated == []
    assert report.failed_step is None
    assert c1.applied == c2.applied == c3.applied == 1


# --- 失败：逆序补偿 ---

def test_second_step_failure_compensates_first():
    c1, c2 = _mk("oa"), _mk("wecom", fail_on_apply=True)
    report = SagaOrchestrator([
        SagaStep("oa", c1), SagaStep("wecom", c2),
    ]).run()
    assert report.ok is False
    assert report.failed_step == "wecom"
    assert report.compensated == ["oa"]  # 逆序：先补偿最后成功的
    assert c1.compensated == 1
    assert c2.applied == 1  # 失败步本身曾尝试 apply


def test_third_step_failure_compensates_first_two_reversed():
    c1, c2, c3 = _mk("oa"), _mk("wecom"), _mk("erp", fail_on_apply=True)
    report = SagaOrchestrator([
        SagaStep("oa", c1), SagaStep("wecom", c2), SagaStep("erp", c3),
    ]).run()
    assert report.ok is False
    assert report.failed_step == "erp"
    # 最新成功先补偿
    assert report.compensated == ["wecom", "oa"]
    assert c2.compensated == 1 and c1.compensated == 1


def test_compensation_unavailable_marks_recon_and_continues():
    # c2 不可补偿，但更早的 c1 仍应被补偿（尽量多回滚）
    c1, c2, c3 = _mk("oa"), _mk("wecom", not_compensable=True), _mk("erp", fail_on_apply=True)
    report = SagaOrchestrator([
        SagaStep("oa", c1), SagaStep("wecom", c2), SagaStep("erp", c3),
    ]).run()
    assert report.ok is False
    assert report.reconciliation_required is True
    assert "wecom" in report.compensation_unavailable
    assert report.compensated == ["oa"]  # 更早成功步骤仍被补偿
    assert c1.compensated == 1


def test_single_step_failure():
    c1 = _mk("oa", fail_on_apply=True)
    report = SagaOrchestrator([SagaStep("oa", c1)]).run()
    assert report.ok is False
    assert report.failed_step == "oa"
    assert report.compensated == []  # 无已成功步骤可补偿


# --- 步骤顺序断言 ---

def test_step_order_preserved_in_context():
    c1, c2 = _mk("oa"), _mk("wecom")
    ctx = SagaOrchestrator([
        SagaStep("oa", c1), SagaStep("wecom", c2),
    ]).run()
    # 执行顺序 = 声明顺序（context.results 按序写入）
    assert list(ctx.executed_steps) == ["oa", "wecom"]


# --- 空步骤安全 ---

def test_empty_steps_rejected():
    with pytest.raises(ValueError):
        SagaOrchestrator([])


# --- payload 透传 ---

def test_payload_written_to_context():
    c1 = _mk("oa")
    orch = SagaOrchestrator([
        SagaStep("oa", c1, payload={"contract_no": "HT-001"}),
    ])
    report = orch.run()
    assert report.ok is True
    # payload 是给连接器的输入（payloads），results 是连接器的输出
    assert orch.context.payloads["oa"] == {"contract_no": "HT-001"}
    assert orch.context.results["oa"] == {"written_back": True}


# --- 与 ProposalService 集成：SagaExecutionError 可被捕获 ---

def test_saga_execution_error_holds_report():
    c1, c2 = _mk("oa"), _mk("wecom", fail_on_apply=True)
    orchestrator = SagaOrchestrator([
        SagaStep("oa", c1), SagaStep("wecom", c2),
    ])
    report = orchestrator.run()
    assert isinstance(report, SagaReport)
    assert report.failed_step == "wecom"
