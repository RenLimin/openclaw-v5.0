"""
L1 运行时适配器包

提供运行时适配器的统一入口和注册机制。

使用方式：
    from L1_runtime.adapters import get_adapter
    adapter = get_adapter("openclaw")

当前已注册运行时：
- openclaw: OpenClaw 运行时（默认，已实现）
- claude-code: 预留（待实现）
- crewai: 预留（待实现）
"""

from .base import (
    ChannelInterface,
    Conversation,
    CredentialInterface,
    ExecResult,
    ErrorCode,
    HealthStatus,
    MemoryInterface,
    MemoryItem,
    Message,
    RuntimeAdapter,
    SandboxInterface,
    SendResult,
    ToolResult,
)
from .registry import (
    RuntimeRegistry,
    get_adapter,
    get_adapter_class,
    is_registered,
    list_registered,
    register_adapter,
)

__all__ = [
    # 核心 ABC
    "RuntimeAdapter",
    "MemoryInterface",
    "ChannelInterface",
    "SandboxInterface",
    "CredentialInterface",
    # 数据模型
    "HealthStatus",
    "ToolResult",
    "ExecResult",
    "SendResult",
    "MemoryItem",
    "Message",
    "Conversation",
    "ErrorCode",
    # 注册/工厂
    "RuntimeRegistry",
    "register_adapter",
    "get_adapter",
    "get_adapter_class",
    "is_registered",
    "list_registered",
]

# ---------------------------------------------------------------------------
# 自动注册内建适配器
# ---------------------------------------------------------------------------

# OpenClaw（已实现，默认运行时）
try:
    from .openclaw.openclaw import OpenClawRuntimeAdapter
    register_adapter("openclaw", OpenClawRuntimeAdapter)
except ImportError:
    # 如果导入失败（比如缺依赖），静默跳过
    pass
