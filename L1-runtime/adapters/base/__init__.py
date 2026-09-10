"""
L1 运行时抽象基类包
定义所有运行时适配器必须实现的最小能力契约。
"""
from .models import (
    HealthStatus,
    ToolResult,
    ExecResult,
    SendResult,
    MemoryItem,
    Message,
    Conversation,
    ErrorCode,
)
from .runtime import RuntimeAdapter
from .memory import MemoryInterface
from .channel import ChannelInterface
from .sandbox import SandboxInterface
from .credential import CredentialInterface

__all__ = [
    # 数据模型
    "HealthStatus",
    "ToolResult",
    "ExecResult",
    "SendResult",
    "MemoryItem",
    "Message",
    "Conversation",
    "ErrorCode",
    # 抽象基类
    "RuntimeAdapter",
    "MemoryInterface",
    "ChannelInterface",
    "SandboxInterface",
    "CredentialInterface",
]
