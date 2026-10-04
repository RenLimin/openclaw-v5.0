"""
ChannelInterface — 通道抽象接口

定义运行时必须提供的消息通道能力，包括：
- 发送消息
- 接收消息
- 会话列举

L2-L4 只依赖此接口，不直接调用具体运行时的通道 API。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .models import Conversation, Message, SendResult


class ChannelInterface(ABC):
    """消息通道抽象接口。

    所有运行时适配器的通道子系统必须实现本接口。
    接口设计为最小能力集：发送、接收、会话列举。
    """

    name: str
    """通道名称，全局唯一标识。"""

    @abstractmethod
    def send(self, target: str, message: str) -> SendResult:
        """向目标发送文本消息。

        Args:
            target: 目标标识（如用户 ID、群聊 ID、会话 ID）
            message: 消息内容（纯文本）

        Returns:
            SendResult — 发送结果，含 success / message_id / error。
        """
        ...

    @abstractmethod
    def receive(self, timeout: float = 0.0) -> Optional[Message]:
        """接收一条消息。

        Args:
            timeout: 超时时间（秒）。0 表示非阻塞，无消息立即返回 None。

        Returns:
            Message 对象，超时或无消息时返回 None。
        """
        ...

    @abstractmethod
    def list_conversations(self, limit: int = 50) -> List[Conversation]:
        """列举会话列表。

        Args:
            limit: 最大返回会话数

        Returns:
            会话摘要列表，通常按最后活跃时间排序。
        """
        ...
