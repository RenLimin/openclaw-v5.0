"""Channel Router — 路由抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from channel_adapter import ChannelAdapter
from models import InternalMessage, RouteTarget


class Router(ABC):
    """消息路由抽象基类。

    负责：
    - 入站消息路由：决定消息送到哪个 Agent / 处理单元
    - 出站消息路由：决定回复通过哪个通道适配器发出
    - 通道适配器注册与发现
    """

    @abstractmethod
    def route_inbound(self, message: InternalMessage) -> RouteTarget:
        """入站路由：决定消息应该被送到哪个目标。

        Args:
            message: 入站内部消息

        Returns:
            RouteTarget — 路由目标描述
        """
        ...

    @abstractmethod
    def route_outbound(
        self,
        message: InternalMessage,
        target: RouteTarget,
    ) -> ChannelAdapter:
        """出站路由：找到投递消息的通道适配器。

        Args:
            message: 出站消息
            target: 路由目标

        Returns:
            ChannelAdapter — 负责投递的适配器

        Raises:
            ValueError: 找不到对应通道适配器
        """
        ...

    @abstractmethod
    def register_adapter(self, name: str, adapter: ChannelAdapter) -> None:
        """注册一个通道适配器。"""
        ...

    @abstractmethod
    def unregister_adapter(self, name: str) -> None:
        """注销一个通道适配器。"""
        ...

    @abstractmethod
    def list_adapters(self) -> List[str]:
        """列出所有已注册的适配器名称。"""
        ...

    @abstractmethod
    def get_adapter(self, name: str) -> ChannelAdapter | None:
        """按名称获取适配器。"""
        ...

    @abstractmethod
    def health_check(self) -> Dict[str, str]:
        """所有已注册适配器的健康状态汇总。

        Returns:
            {adapter_name: status} — status: ok / degraded / down
        """
        ...
