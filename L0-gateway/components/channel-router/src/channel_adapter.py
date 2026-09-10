"""Channel Adapter — 通道适配器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from models import InternalMessage, SendResult


class ChannelAdapter(ABC):
    """通道适配器抽象基类。

    每个外部通道（WeCom / WebChat / Discord / Slack 等）对应一个实现。
    负责：
    - 将通道原生消息转换为 InternalMessage（to_internal）
    - 将 InternalMessage 转换为通道原生格式（from_internal）
    - 接收消息（receive）
    - 发送消息（send）
    - 健康检查（health_check）
    """

    name: str = "base"

    @abstractmethod
    def receive(self, timeout: float | None = None) -> InternalMessage | None:
        """从通道接收一条消息。

        Args:
            timeout: 超时秒数。None 表示阻塞直到有消息。

        Returns:
            InternalMessage — 有消息时返回；超时返回 None
        """
        ...

    @abstractmethod
    def send(self, target: str, message: InternalMessage) -> SendResult:
        """向目标发送消息。

        Args:
            target: 目标标识（用户 ID / 群 ID / 频道名等）
            message: 内部消息对象

        Returns:
            SendResult — 发送结果
        """
        ...

    @abstractmethod
    def to_internal(self, raw: Any) -> InternalMessage:
        """将通道原生消息转换为统一内部消息模型。

        Args:
            raw: 通道原生消息对象

        Returns:
            InternalMessage — 统一格式的内部消息
        """
        ...

    @abstractmethod
    def from_internal(self, msg: InternalMessage) -> Any:
        """将内部消息转换为通道原生格式。

        Args:
            msg: 内部消息

        Returns:
            通道原生消息格式对象
        """
        ...

    @abstractmethod
    def health_check(self) -> Dict[str, str]:
        """通道健康检查。

        Returns:
            {"status": "ok|degraded|down", "message": "..."}
        """
        ...
