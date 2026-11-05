"""Operational ontology layer (阶段 4, DESIGN-DETAIL-operational-ontology-v1.0).

P1: authoritative identity (IdentityService).
P2: kinetic layer + registry (ActionRegistry, AssemblyGate).
P3: proposal gate + decision objects (ProposalService, DecisionService,
     OutputGuard, writeback connectors).
"""
from .identity import IdentityService, is_operational_object_type
from .actions import (
    ActionRegistry,
    AssemblyGate,
    load_handler,
    parse_handler_ref,
)
from .decision import DecisionService
from .proposal import ProposalService
from .connectors import (
    WritebackConnector,
    NullConnector,
    SagaContext,
    CompensationUnavailable,
)

__all__ = [
    "IdentityService",
    "is_operational_object_type",
    "ActionRegistry",
    "AssemblyGate",
    "load_handler",
    "parse_handler_ref",
    "DecisionService",
    "ProposalService",
    "WritebackConnector",
    "NullConnector",
    "SagaContext",
    "CompensationUnavailable",
]
