"""Multi-step Saga orchestration (详设 §3.5, P4).

SagaOrchestrator 执行有序的写回步骤列表；任一步失败时，对已成功步骤
逆序补偿（newest first）。补偿语义：
- 某步连接器抛 CompensationUnavailable 时，该步记入 compensation_unavailable
  并置 reconciliation_required（需人工对账）；更早的已成功步骤仍继续尝试补偿，
  尽量多回滚。
- 永不静默：调用方收到结构化 SagaReport。
- 向后兼容：单连接器路径（ProposalService.commit 原逻辑）不受影响。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import CompensationUnavailable, SagaContext, WritebackConnector


class SagaExecutionError(Exception):
    """多步写回执行失败（已完成逆序补偿或标记对账）。"""

    def __init__(self, report: "SagaReport") -> None:
        self.report = report
        super().__init__(
            report.error or f"saga failed at step {report.failed_step}"
        )


@dataclass
class SagaStep:
    """一个写回步骤：连接器 + 步骤名 + 可选 payload。"""

    name: str
    connector: WritebackConnector
    payload: Optional[Dict[str, Any]] = None


@dataclass
class SagaReport:
    """Saga 执行的完整结果（结构化，供审计/决策记录）。"""

    ok: bool = False
    executed_steps: List[str] = field(default_factory=list)
    failed_step: Optional[str] = None
    compensated: List[str] = field(default_factory=list)
    compensation_unavailable: List[str] = field(default_factory=list)
    reconciliation_required: bool = False
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "executed_steps": self.executed_steps,
            "failed_step": self.failed_step,
            "compensated": self.compensated,
            "compensation_unavailable": self.compensation_unavailable,
            "reconciliation_required": self.reconciliation_required,
            "error": self.error,
        }


class SagaOrchestrator:
    """按序执行写回步骤；失败时逆序补偿已成功步骤。"""

    def __init__(
        self,
        steps: List[SagaStep],
        context: Optional[SagaContext] = None,
    ) -> None:
        if not steps:
            raise ValueError("saga steps must not be empty")
        self.steps = steps
        self.context = context or SagaContext()

    def run(self) -> SagaReport:
        report = SagaReport(ok=False)
        succeeded: List[str] = []

        # 正向：按序 apply
        for step in self.steps:
            report.executed_steps.append(step.name)
            if step.payload is not None:
                self.context.payloads[step.name] = step.payload
            try:
                step.connector.apply(self.context)
                succeeded.append(step.name)
            except Exception as exc:
                report.failed_step = step.name
                report.error = str(exc)
                break

        if report.failed_step is None:
            report.ok = True
            return report

        # 反向：对已成功步骤逆序补偿（最新先补偿）
        for name in reversed(succeeded):
            step = next(s for s in self.steps if s.name == name)
            try:
                step.connector.compensate(self.context)
                report.compensated.append(name)
            except CompensationUnavailable:
                report.compensation_unavailable.append(name)
                report.reconciliation_required = True
                # 继续尝试更早步骤，尽量多回滚
            except Exception as exc:
                report.compensation_unavailable.append(name)
                report.reconciliation_required = True
                report.error = (
                    f"{report.error}; compensate {name} failed: {exc}"
                )
        return report


__all__ = [
    "SagaExecutionError",
    "SagaOrchestrator",
    "SagaReport",
    "SagaStep",
]
