"""WritebackConnector 抽象 + SagaContext + NullConnector（详设 §3.5）。

P3 只要求最小可用契约：
- WritebackConnector.apply(ctx) 写回源系统；
- compensate(ctx) 反向补偿（连接器不支持反向操作时抛 CompensationUnavailable）；
- NullConnector 无外部写回，apply 仅记录步骤，compensate 为空操作。

SagaContext 跟踪已成功步骤，供 commit 失败时补偿编排使用。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class CompensationUnavailable(Exception):
    """连接器不支持反向补偿（如 OA 审批已发起无法撤回）。

    ProposalService 捕获后置 status='failed'，并生成人工对账工单记录
    （result='compensated' + 说明），不静默。
    """


@dataclass
class SagaContext:
    """Saga 执行上下文：记录已成功步骤与各步输出。

    payloads: 编排器在 apply 前写入的步骤输入（连接器可读）；
    results: 连接器通过 mark_success 写入的输出。
    """

    steps: List[str] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    payloads: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, name: str) -> None:
        if name not in self.steps:
            self.steps.append(name)

    def mark_success(self, name: str, result: Any = None) -> None:
        self.add_step(name)
        self.results[name] = result
        self.errors.pop(name, None)

    def mark_failed(self, name: str, error: str) -> None:
        self.add_step(name)
        self.errors[name] = error


class WritebackConnector(ABC):
    """源系统写回连接器抽象。"""

    name: str = "abstract"

    @abstractmethod
    def apply(self, ctx: SagaContext) -> None:
        """写回源系统；失败抛异常，commit 事务整体 ROLLBACK。"""

    @abstractmethod
    def compensate(self, ctx: SagaContext) -> None:
        """反向补偿；不支持时抛 CompensationUnavailable。"""


class NullConnector(WritebackConnector):
    """无外部写回的默认连接器：apply 仅标记步骤成功。

    首个实例（无源系统或仅库内变更）用它即可闭环；commit 的 DB 变更
    与决策记录仍在 ProposalService 的本地事务内完成。
    """

    name = "null"

    def apply(self, ctx: SagaContext) -> None:
        ctx.mark_success(self.name, {"written_back": False})

    def compensate(self, ctx: SagaContext) -> None:
        # 无外部副作用，补偿为空操作（幂等）。
        ctx.mark_success(f"{self.name}.compensate", {"compensated": False})
