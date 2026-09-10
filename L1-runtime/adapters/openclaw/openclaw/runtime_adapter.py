"""
OpenClaw 运行时适配器 — RuntimeAdapter ABC 实现

将 OpenClaw 运行时适配为 L1 RuntimeAdapter 抽象基类。
使用组合模式：内部持有 OpenClawAdapter 实例，将 ABC 方法翻译为
OpenClawAdapter 的对应方法。

设计原则：
1. 不修改现有 OpenClawAdapter，保持向后兼容
2. 所有抽象方法必须实现，不支持的能力 raise NotImplementedError
3. 子系统接口（Memory/Channel/Sandbox/Credential）使用内嵌类实现
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from adapters.base import (
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

from .adapter import OpenClawAdapter


# ===========================================================================
# OpenClaw MemoryInterface 实现
# ===========================================================================

class OpenClawMemory(MemoryInterface):
    """OpenClaw 记忆系统适配。

    内部使用 OpenClawAdapter 的 memory_* 系列方法。
    """

    def __init__(self, adapter: OpenClawAdapter, scope: str = "default") -> None:
        self._adapter = adapter
        self._scope = scope

    def search(self, query: str, limit: int = 5) -> List[MemoryItem]:
        """语义搜索记忆。"""
        raw_results = self._adapter.memory_search(query, max_results=limit)
        items: List[MemoryItem] = []
        for r in raw_results:
            # OpenClaw memory_search 返回的格式可能不同，这里做兼容映射
            key = r.get("key", r.get("path", ""))
            value = r.get("value", r.get("content", ""))
            score = float(r.get("score", r.get("relevance", 0.0)))
            metadata = {k: v for k, v in r.items() if k not in {"key", "value", "score", "path", "content", "relevance"}}
            items.append(MemoryItem(key=key, value=value, score=score, metadata=metadata))
        return items

    def get(self, key: str) -> Optional[str]:
        """读取记忆值。"""
        result = self._adapter.memory_read(key)
        if result is None:
            return None
        return str(result)

    def put(self, key: str, value: str) -> bool:
        """写入记忆。"""
        return self._adapter.memory_write(key, value)

    def delete(self, key: str) -> bool:
        """删除记忆 — OpenClaw 当前原生不支持显式删除，返回 False。"""
        # OpenClaw 记忆系统目前没有 delete 原语
        raise NotImplementedError("OpenClaw 运行时暂不支持记忆删除操作")

    def list(self, prefix: str = "") -> List[str]:
        """列举记忆键 — OpenClaw 当前不支持前缀列举，返回空列表。"""
        # 可以通过 memory_search 模拟，但语义不同，这里明确不支持
        raise NotImplementedError("OpenClaw 运行时暂不支持记忆前缀列举")


# ===========================================================================
# OpenClaw ChannelInterface 实现
# ===========================================================================

class OpenClawChannel(ChannelInterface):
    """OpenClaw 消息通道适配。

    内部使用 OpenClawAdapter 的 send_message 等方法。
    """

    def __init__(self, adapter: OpenClawAdapter, name: str) -> None:
        self._adapter = adapter
        self.name = name

    def send(self, target: str, message: str) -> SendResult:
        """发送消息。"""
        # OpenClawAdapter.send_message 只接受 channel + msg，target 被编码在消息中或由通道决定
        # 这里按 channel 维度适配，target 作为会话标识
        try:
            success = self._adapter.send_message(self.name, message)
            if success:
                return SendResult.ok(message_id="unknown")
            return SendResult.fail(
                error="消息发送失败",
                error_code=ErrorCode.CHANNEL_SEND_FAILED,
            )
        except Exception as e:
            return SendResult.fail(
                error=str(e),
                error_code=ErrorCode.CHANNEL_SEND_FAILED,
            )

    def receive(self, timeout: float = 0.0) -> Optional[Message]:
        """接收消息 — 当前通过网关推送模式，主动接收暂不支持。"""
        raise NotImplementedError("OpenClaw 运行时使用推送模式，不支持主动拉取消息")

    def list_conversations(self, limit: int = 50) -> List[Conversation]:
        """列举会话 — 当前无统一会话列表 API。"""
        raise NotImplementedError("OpenClaw 运行时暂不支持会话列表查询")


# ===========================================================================
# OpenClaw SandboxInterface 实现
# ===========================================================================

class OpenClawSandbox(SandboxInterface):
    """OpenClaw 沙箱系统适配。

    内部使用 OpenClawAdapter 的 sandbox_execute 方法。
    """

    def __init__(self, adapter: OpenClawAdapter) -> None:
        self._adapter = adapter

    def exec(self, command: str, timeout: float = 30.0) -> ExecResult:
        """在沙箱中执行命令。"""
        result = self._adapter.sandbox_execute(command, opts={"timeout": timeout})
        if result.success:
            output = result.output or {}
            if isinstance(output, dict):
                return ExecResult.ok(
                    exit_code=int(output.get("exit_code", 0)),
                    stdout=str(output.get("stdout", "")),
                    stderr=str(output.get("stderr", "")),
                )
            return ExecResult.ok(stdout=str(output))
        return ExecResult.fail(
            error=result.error or "沙箱执行失败",
            error_code=ErrorCode.SANDBOX_EXEC_FAILED,
        )

    def read_file(self, path: str) -> Optional[str]:
        """读取沙箱文件 — 间接通过 exec cat 实现。"""
        result = self.exec(f"cat {path}")
        if result.success:
            return result.stdout
        return None

    def write_file(self, path: str, content: str) -> bool:
        """写入沙箱文件 — 间接通过 exec 实现。"""
        import shlex
        result = self.exec(f"mkdir -p $(dirname {path}) && printf %s {shlex.quote(content)} > {path}")
        return result.success

    def list_dir(self, path: str = ".") -> List[str]:
        """列举沙箱目录 — 间接通过 exec ls 实现。"""
        result = self.exec(f"ls -1 {path} 2>/dev/null || echo -n ''")
        if result.success and result.stdout.strip():
            return [line for line in result.stdout.strip().split("\n") if line]
        return []


# ===========================================================================
# OpenClaw CredentialInterface 实现
# ===========================================================================

class OpenClawCredentials(CredentialInterface):
    """OpenClaw 凭据系统适配。

    内部使用 OpenClawAdapter 的 credential_* 方法。
    """

    def __init__(self, adapter: OpenClawAdapter) -> None:
        self._adapter = adapter

    def get(self, name: str) -> Optional[str]:
        """获取凭据值。"""
        return self._adapter.credential_get(name)

    def list(self) -> List[str]:
        """列举凭据名称 — OpenClaw 不支持明文列举（安全设计）。"""
        raise NotImplementedError("OpenClaw 运行时不支持凭据列举（安全设计）")

    def has(self, name: str) -> bool:
        """检查凭据是否存在。"""
        try:
            value = self._adapter.credential_get(name)
            return value is not None
        except Exception:
            return False


# ===========================================================================
# OpenClaw RuntimeAdapter 主实现
# ===========================================================================

class OpenClawRuntimeAdapter(RuntimeAdapter):
    """OpenClaw 运行时适配器 — RuntimeAdapter ABC 的完整实现。

    使用组合模式封装 OpenClawAdapter，将其方法映射到 RuntimeAdapter 接口。
    不支持的能力通过 raise NotImplementedError 明确声明。
    """

    name = "openclaw"

    def __init__(self) -> None:
        self._adapter = OpenClawAdapter()
        self.version = self._adapter.version
        self.capabilities: Dict[str, Any] = {
            "tool": {
                "execute": True,
                "register": True,
            },
            "memory": {
                "get": True,
                "put": True,
                "search": True,
                "delete": False,   # 不支持
                "list": False,     # 不支持
            },
            "channel": {
                "send": True,
                "receive": False,  # 推送模式
                "list_conversations": False,
            },
            "sandbox": {
                "exec": True,
                "read_file": True,
                "write_file": True,
                "list_dir": True,
            },
            "credential": {
                "get": True,
                "has": True,
                "list": False,     # 安全设计，不列举
            },
            "config": {
                "get": True,
                "set": True,
                "validate": True,
            },
            "schedule": {
                "create": True,
                "cancel": True,
                "list": True,
            },
            "session": {
                "create": True,
                "send": True,
                "history": True,
            },
            "context": {
                "status": True,
                "compact": True,
            },
        }
        # 缓存子系统实例
        self._memory: Dict[str, OpenClawMemory] = {}
        self._channels: Dict[str, OpenClawChannel] = {}
        self._sandbox: Optional[OpenClawSandbox] = None
        self._credentials: Optional[OpenClawCredentials] = None

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    def health_check(self) -> HealthStatus:
        """OpenClaw 健康检查。"""
        raw = self._adapter.health()
        return HealthStatus(
            status=raw.status,
            message=raw.message,
            details=raw.details,
        )

    # ------------------------------------------------------------------
    # 配置管理
    # ------------------------------------------------------------------

    def get_config(self, key: str) -> Optional[Any]:
        """读取配置。"""
        return self._adapter.config_get(key)

    def set_config(self, key: str, value: Any) -> bool:
        """写入配置（带四步保护：dry-run → 写入 → 校验 → 读回）。"""
        return self._adapter.config_set(key, value)

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    def execute_tool(self, name: str, params: Dict[str, Any]) -> ToolResult:
        """调用工具。"""
        raw = self._adapter.call_tool(name, params)
        if raw.success:
            return ToolResult.ok(output=raw.output)
        return ToolResult.fail(
            error=raw.error or "工具执行失败",
            error_code=ErrorCode.TOOL_EXECUTION_FAILED,
        )

    # ------------------------------------------------------------------
    # 子系统访问
    # ------------------------------------------------------------------

    def get_memory(self, scope: str = "default") -> OpenClawMemory:
        """获取记忆子系统。"""
        if scope not in self._memory:
            self._memory[scope] = OpenClawMemory(self._adapter, scope)
        return self._memory[scope]

    def get_channel(self, name: str) -> OpenClawChannel:
        """获取指定通道。"""
        if name not in self._channels:
            # 这里不做通道是否存在的预检查（实际发送时会失败）
            # 因为 OpenClaw 的通道列表需要通过配置查询，成本较高
            self._channels[name] = OpenClawChannel(self._adapter, name)
        return self._channels[name]

    def get_sandbox(self) -> OpenClawSandbox:
        """获取沙箱子系统。"""
        if self._sandbox is None:
            self._sandbox = OpenClawSandbox(self._adapter)
        return self._sandbox

    def get_credentials(self) -> OpenClawCredentials:
        """获取凭据子系统。"""
        if self._credentials is None:
            self._credentials = OpenClawCredentials(self._adapter)
        return self._credentials
