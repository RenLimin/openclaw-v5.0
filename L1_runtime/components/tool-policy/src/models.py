"""Tool Policy — 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class PolicyEffect(str, Enum):
    """策略效果。"""
    ALLOW = "allow"
    DENY = "deny"


class DecisionResult(str, Enum):
    """策略评估结果。"""
    ALLOW = "allow"
    DENY = "deny"
    NEED_APPROVAL = "need_approval"
    RATE_LIMITED = "rate_limited"


@dataclass
class ToolPolicy:
    """一条工具策略。"""
    policy_id: str
    effect: PolicyEffect
    tools: List[str] = field(default_factory=lambda: ["*"])  # 支持通配符 *
    scope: str = "global"            # global / layer / component / agent / user
    subject: str = "*"               # 主体（agent_id / user_id / role / *）
    priority: int = 0                # 优先级，数字大先评估
    conditions: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches_tool(self, tool_name: str) -> bool:
        """检查策略是否匹配指定工具名（支持 * 通配符）。"""
        for pattern in self.tools:
            if pattern == "*" or pattern == tool_name:
                return True
            if pattern.endswith("*") and tool_name.startswith(pattern[:-1]):
                return True
        return False

    def matches_subject(self, subject: str) -> bool:
        return self.subject == "*" or self.subject == subject


@dataclass
class ToolAccessRequest:
    """工具访问请求。"""
    tool_name: str
    caller_type: str              # agent / user / system
    caller_id: str
    scope: str = "global"
    parameters: Dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class PolicyDecision:
    """策略评估决策。"""
    result: DecisionResult
    policy_id: str | None = None          # 命中的策略 ID
    reason: str = ""
    retry_after_seconds: int | None = None  # 限流器专用
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.result == DecisionResult.ALLOW
