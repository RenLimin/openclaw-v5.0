"""Agent Registry — 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentStatus(str, Enum):
    """Agent 状态。"""
    REGISTERED = "registered"
    AVAILABLE = "available"
    BUSY = "busy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class AgentSpec:
    """Agent 注册规格 — 静态元数据。"""
    agent_id: str
    name: str
    description: str
    version: str = "0.1.0"
    runtime: str = "openclaw"
    entrypoint: str = ""
    capabilities: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    model: Optional[str] = None
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    author: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def has_capability(self, cap: str) -> bool:
        return cap in self.capabilities

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "runtime": self.runtime,
            "entrypoint": self.entrypoint,
            "capabilities": self.capabilities,
            "tags": self.tags,
            "model": self.model,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "author": self.author,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class AgentHandle:
    """已实例化的 Agent 句柄 — 运行时状态。"""
    instance_id: str
    agent_id: str
    status: AgentStatus = AgentStatus.AVAILABLE
    started_at: datetime = field(default_factory=datetime.now)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.status == AgentStatus.AVAILABLE
