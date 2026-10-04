"""
RuntimeAdapter — 运行时主适配器抽象基类

这是 L1 层最核心的抽象，所有运行时（OpenClaw / Claude Code / CrewAI 等）
必须继承此类并实现所有抽象方法。

L2-L4 只依赖此接口，不直接调用任何具体运行时的 API。

能力维度对应架构文档 §3.2.1 L1 最小能力契约：
1. Agent Loop         → execute（保留接口，实际由运行时驱动）
2. 工具执行           → execute_tool
3. 记忆              → get_memory
4. 通道接入           → get_channel
5. 配置管理           → get_config / set_config
6. 凭据管理           → get_credentials
7. 沙箱隔离           → get_sandbox
8. 健康检查           → health_check
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .channel import ChannelInterface
from .credential import CredentialInterface
from .memory import MemoryInterface
from .models import HealthStatus, ToolResult
from .sandbox import SandboxInterface


class RuntimeAdapter(ABC):
    """运行时适配器抽象基类。

    定义所有 Agent 运行时必须满足的最小能力契约。
    每个具体运行时（OpenClaw、Claude Code、CrewAI 等）都应
    实现一个子类，将抽象方法翻译为该运行时的原生 API。

    Attributes:
        name: 运行时名称（如 "openclaw"、"claude-code"）
        version: 运行时版本号字符串
        capabilities: 能力描述字典，声明支持的子系统和特性
    """

    # 子类必须在 __init__ 或类变量中设置这些属性
    name: str
    version: str
    capabilities: Dict[str, Any]

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """运行时健康检查。

        Returns:
            HealthStatus — 整体健康状态（ok / degraded / down）。
        """
        ...

    # ------------------------------------------------------------------
    # 配置管理
    # ------------------------------------------------------------------

    @abstractmethod
    def get_config(self, key: str) -> Optional[Any]:
        """读取运行时配置。

        Args:
            key: 配置键（支持点号分隔的嵌套路径，如 "agents.default.model"）

        Returns:
            配置值，键不存在时返回 None。
        """
        ...

    @abstractmethod
    def set_config(self, key: str, value: Any) -> bool:
        """写入运行时配置。

        Args:
            key: 配置键
            value: 配置值

        Returns:
            写入成功返回 True，失败返回 False。

        注意：
            配置写入属于有副作用操作，建议调用方遵循变更治理流程
            （dry-run → 写入 → 校验 → 读回确认）。
        """
        ...

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    @abstractmethod
    def execute_tool(self, name: str, params: Dict[str, Any]) -> ToolResult:
        """调用运行时注册的工具。

        Args:
            name: 工具名称
            params: 工具参数字典

        Returns:
            ToolResult — 执行结果，含 success / output / error_code。
        """
        ...

    # ------------------------------------------------------------------
    # 子系统访问
    # ------------------------------------------------------------------

    @abstractmethod
    def get_memory(self, scope: str = "default") -> MemoryInterface:
        """获取记忆子系统接口。

        Args:
            scope: 记忆作用域（如 "default"、"session"、"global"）

        Returns:
            MemoryInterface 实现实例。
        """
        ...

    @abstractmethod
    def get_channel(self, name: str) -> ChannelInterface:
        """获取指定名称的消息通道。

        Args:
            name: 通道名称（如 "wecom"、"webchat"、"discord"）

        Returns:
            ChannelInterface 实现实例。

        Raises:
            ValueError: 通道不存在时抛出（区别于其他接口的 None 返回，
                        因为通道是显式注册的，不存在是明确错误）。
        """
        ...

    @abstractmethod
    def get_sandbox(self) -> SandboxInterface:
        """获取沙箱子系统接口。

        Returns:
            SandboxInterface 实现实例。
        """
        ...

    @abstractmethod
    def get_credentials(self) -> CredentialInterface:
        """获取凭据管理子系统接口。

        Returns:
            CredentialInterface 实现实例。
        """
        ...

    # ------------------------------------------------------------------
    # 能力声明
    # ------------------------------------------------------------------

    def supports(self, capability: str) -> bool:
        """检查运行时是否支持某项能力。

        默认实现检查 self.capabilities 字典。
        子类可重写以提供更细粒度的判断。

        Args:
            capability: 能力名称（如 "memory.search"、"sandbox.docker"）

        Returns:
            支持返回 True，否则返回 False。
        """
        caps = self.capabilities or {}
        parts = capability.split(".")
        current: Any = caps
        for part in parts:
            if isinstance(current, dict):
                if part not in current:
                    return False
                current = current[part]
            else:
                return False
        return bool(current)

    def list_capabilities(self) -> List[str]:
        """列出所有声明的能力（点号路径形式）。

        Returns:
            能力路径列表，如 ["memory.search", "sandbox.exec", ...]
        """
        caps = self.capabilities or {}

        def _flatten(d: Dict[str, Any], prefix: str = "") -> List[str]:
            result: List[str] = []
            for k, v in d.items():
                path = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
                if isinstance(v, dict) and v:
                    result.extend(_flatten(v, path))
                else:
                    result.append(path)
            return result

        return _flatten(caps)
