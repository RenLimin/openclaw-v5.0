"""Writeback connectors (详设 §3.5).

P3 首个实例：NullConnector（无源系统写回，本地库内事务即可闭环）。
P4 扩展：SagaOrchestrator 多步有序写回 + 逆序补偿。
"""
from .base import (
    WritebackConnector,
    NullConnector,
    SagaContext,
    CompensationUnavailable,
)
from .saga import (
    SagaExecutionError,
    SagaOrchestrator,
    SagaReport,
    SagaStep,
)

__all__ = [
    "WritebackConnector",
    "NullConnector",
    "SagaContext",
    "CompensationUnavailable",
    "SagaExecutionError",
    "SagaOrchestrator",
    "SagaReport",
    "SagaStep",
]
