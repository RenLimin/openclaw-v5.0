"""
L1 运行时抽象层 — 统一数据模型

所有适配器返回的数据结构都必须使用这里定义的 dataclass，
确保 L2-L4 层面对数据格式的一致性，与具体运行时无关。

设计原则：
- 字段最小化，仅覆盖 L1 契约需要的信息
- 统一错误码（ErrorCode 枚举）
- 所有结果对象含 success / error 字段，方便上层统一判断
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 统一错误码
# ---------------------------------------------------------------------------

class ErrorCode(str, Enum):
    """L1 层统一错误码。

    格式: ERR_<类别>_<具体错误>
    所有适配器必须使用这些错误码，禁止自定义返回码。
    """
    # 通用
    OK = "OK"
    UNKNOWN = "ERR_UNKNOWN"
    NOT_IMPLEMENTED = "ERR_NOT_IMPLEMENTED"
    INVALID_PARAM = "ERR_INVALID_PARAM"
    TIMEOUT = "ERR_TIMEOUT"

    # 运行时
    RUNTIME_UNAVAILABLE = "ERR_RUNTIME_UNAVAILABLE"
    RUNTIME_ERROR = "ERR_RUNTIME_ERROR"

    # 工具
    TOOL_NOT_FOUND = "ERR_TOOL_NOT_FOUND"
    TOOL_EXECUTION_FAILED = "ERR_TOOL_EXECUTION_FAILED"

    # 记忆
    MEMORY_KEY_NOT_FOUND = "ERR_MEMORY_KEY_NOT_FOUND"
    MEMORY_READ_FAILED = "ERR_MEMORY_READ_FAILED"
    MEMORY_WRITE_FAILED = "ERR_MEMORY_WRITE_FAILED"

    # 通道
    CHANNEL_NOT_FOUND = "ERR_CHANNEL_NOT_FOUND"
    CHANNEL_SEND_FAILED = "ERR_CHANNEL_SEND_FAILED"
    CHANNEL_RECEIVE_FAILED = "ERR_CHANNEL_RECEIVE_FAILED"

    # 沙箱
    SANDBOX_UNAVAILABLE = "ERR_SANDBOX_UNAVAILABLE"
    SANDBOX_EXEC_FAILED = "ERR_SANDBOX_EXEC_FAILED"
    SANDBOX_FILE_NOT_FOUND = "ERR_SANDBOX_FILE_NOT_FOUND"

    # 凭据
    CREDENTIAL_NOT_FOUND = "ERR_CREDENTIAL_NOT_FOUND"
    CREDENTIAL_ACCESS_DENIED = "ERR_CREDENTIAL_ACCESS_DENIED"

    # 配置
    CONFIG_KEY_NOT_FOUND = "ERR_CONFIG_KEY_NOT_FOUND"
    CONFIG_SET_FAILED = "ERR_CONFIG_SET_FAILED"
    CONFIG_VALIDATION_FAILED = "ERR_CONFIG_VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------

@dataclass
class HealthStatus:
    """运行时健康检查结果。

    Attributes:
        status: 健康状态 — "ok" / "degraded" / "down"
        message: 人类可读的状态描述
        details: 运行时特有的详细信息（可选）
    """
    status: str  # ok / degraded / down
    message: str
    details: Optional[Dict[str, Any]] = None

    def is_ok(self) -> bool:
        return self.status == "ok"

    def is_degraded(self) -> bool:
        return self.status == "degraded"

    def is_down(self) -> bool:
        return self.status == "down"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 工具调用
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """工具调用结果。

    Attributes:
        success: 是否成功
        output: 工具输出（成功时填充）
        error: 错误描述（失败时填充）
        error_code: 统一错误码（失败时填充）
    """
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_code: ErrorCode = ErrorCode.OK

    @classmethod
    def ok(cls, output: Any = None) -> "ToolResult":
        """构造成功结果。"""
        return cls(success=True, output=output)

    @classmethod
    def fail(
        cls,
        error: str,
        error_code: ErrorCode = ErrorCode.TOOL_EXECUTION_FAILED,
    ) -> "ToolResult":
        """构造失败结果。"""
        return cls(success=False, error=error, error_code=error_code)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["error_code"] = self.error_code.value
        return d


# ---------------------------------------------------------------------------
# 沙箱执行
# ---------------------------------------------------------------------------

@dataclass
class ExecResult:
    """沙箱命令执行结果。

    Attributes:
        success: 是否成功（exit code == 0）
        exit_code: 进程退出码
        stdout: 标准输出
        stderr: 标准错误
        error: 错误描述（非执行类错误，如沙箱不可用）
        error_code: 统一错误码
    """
    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    error_code: ErrorCode = ErrorCode.OK

    @classmethod
    def ok(cls, exit_code: int = 0, stdout: str = "", stderr: str = "") -> "ExecResult":
        return cls(
            success=(exit_code == 0),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    @classmethod
    def fail(
        cls,
        error: str,
        error_code: ErrorCode = ErrorCode.SANDBOX_EXEC_FAILED,
        exit_code: int = -1,
    ) -> "ExecResult":
        return cls(
            success=False,
            exit_code=exit_code,
            error=error,
            error_code=error_code,
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["error_code"] = self.error_code.value
        return d


# ---------------------------------------------------------------------------
# 通道消息
# ---------------------------------------------------------------------------

@dataclass
class SendResult:
    """消息发送结果。

    Attributes:
        success: 是否发送成功
        message_id: 消息 ID（成功时填充）
        error: 错误描述
        error_code: 统一错误码
    """
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    error_code: ErrorCode = ErrorCode.OK

    @classmethod
    def ok(cls, message_id: str) -> "SendResult":
        return cls(success=True, message_id=message_id)

    @classmethod
    def fail(
        cls,
        error: str,
        error_code: ErrorCode = ErrorCode.CHANNEL_SEND_FAILED,
    ) -> "SendResult":
        return cls(success=False, error=error, error_code=error_code)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["error_code"] = self.error_code.value
        return d


@dataclass
class Message:
    """通道消息。

    Attributes:
        id: 消息 ID
        channel: 来源通道名
        sender: 发送者标识
        content: 消息内容（文本）
        timestamp: 时间戳（ISO 格式字符串）
        metadata: 附加元数据（通道特有）
    """
    id: str
    channel: str
    sender: str
    content: str
    timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Conversation:
    """会话摘要。

    Attributes:
        id: 会话 ID
        channel: 所属通道
        title: 会话标题/主题
        participants: 参与者列表
        last_message_at: 最后消息时间
        unread_count: 未读消息数
    """
    id: str
    channel: str
    title: str = ""
    participants: List[str] = field(default_factory=list)
    last_message_at: Optional[str] = None
    unread_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 记忆
# ---------------------------------------------------------------------------

@dataclass
class MemoryItem:
    """记忆条目。

    Attributes:
        key: 记忆键
        value: 记忆值（文本形式）
        score: 匹配分数（搜索结果时有效，0-1）
        metadata: 附加元数据
    """
    key: str
    value: str
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
